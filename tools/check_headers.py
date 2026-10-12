"""Diagnóstico HTTP, CDN e indexabilidade (rodar contra o domínio público, atrás da CDN).

Verifica, para cada URL do sitemap:
  1. status HTTP 200 e ausência de redirecionamentos inesperados;
  2. "noindex" em X-Robots-Tag ou <meta name="robots"> (conflito injetado por CDN/plugin);
  3. canonical apontando para a própria URL;
  4. JSON-LD presente e parseável no HTML bruto (sem JavaScript);
  5. mesma resposta para navegador e para bots de IA (bloqueio/challenge de CDN, cloaking);
  6. cabeçalhos de cache da CDN (cf-cache-status, age) para detectar cache corrompido.
E também:
  7. soft 404: URL aleatória e imóvel vendido devem responder 404 real;
  8. robots.txt servido pela CDN sem Disallow para agentes de IA
     (ex.: "Managed robots.txt" / "Block AI bots" do Cloudflare).

Uso:
  python tools/check_headers.py https://www.seudominio.com.br
  python tools/check_headers.py https://www.seudominio.com.br --origem https://origem.seudominio.com.br
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
import urllib.error
import urllib.request
from xml.etree import ElementTree

UA_NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
UA_BOTS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}
AI_TOKENS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User",
             "PerplexityBot", "Google-Extended", "Bytespider", "Applebot-Extended", "CCBot"]


class SemRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(SemRedirect)


def buscar(url: str, ua: str = UA_NAVEGADOR) -> tuple[int, dict, str]:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,*/*"})
    try:
        with OPENER.open(req, timeout=20) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode("utf-8", "replace")


def meta_robots(html: str) -> str:
    m = re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']+)', html, re.I)
    return m.group(1) if m else ""


def canonical(html: str) -> str:
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', html, re.I)
    return m.group(1) if m else ""


def jsonld_ok(html: str) -> tuple[bool, int]:
    blocos = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    if not blocos:
        return False, 0
    try:
        grafo = json.loads(blocos[0]).get("@graph", [])
        return True, len(grafo)
    except json.JSONDecodeError:
        return False, 0


def corpo_hash(html: str) -> str:
    principal = html.split("<main", 1)[-1].split("</main>", 1)[0]
    # o Cloudflare gera um token novo a cada requisição ao ofuscar e-mails: não é camuflagem
    principal = re.sub(r"email-protection#[0-9a-f]+", "email-protection", principal)
    principal = re.sub(r'data-cfemail="[0-9a-f]+"', "", principal)
    return hashlib.sha256(principal.encode()).hexdigest()[:12]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", help="URL pública (atrás da CDN)")
    parser.add_argument("--origem", help="URL da origem, sem CDN, para comparar respostas")
    parser.add_argument("--imovel-vendido", default="/imoveis/cobertura-meireles-410m2/")
    parser.add_argument("--limite", type=int, default=0, help="máximo de URLs do sitemap (0 = todas)")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    problemas: list[str] = []

    def falha(msg: str) -> None:
        problemas.append(msg)
        print(f"  ✗ {msg}")

    # robots.txt
    print("robots.txt")
    raiz = "/".join(base.split("/", 3)[:3])  # robots.txt vale só na raiz do domínio
    status, _, robots = buscar(raiz + "/robots.txt")
    if status != 200:
        falha(f"robots.txt respondeu {status}")
    grupos = re.split(r"\n\s*\n", robots)
    for grupo in grupos:
        agentes = re.findall(r"(?im)^user-agent:\s*(\S+)", grupo)
        bloqueia_tudo = re.search(r"(?im)^disallow:\s*/\s*$", grupo)
        bloqueados = [a for a in agentes if a in AI_TOKENS or a == "*"]
        if bloqueia_tudo and bloqueados:
            falha(f"robots.txt bloqueia {', '.join(bloqueados)} (verifique 'Managed robots.txt' da CDN)")
    for recurso in ("/static/", ".css"):
        if re.search(rf"(?im)^disallow:.*{re.escape(recurso)}", robots):
            falha(f"robots.txt bloqueia recursos de renderização ({recurso})")

    # soft 404
    print("soft 404")
    for caminho in (f"/{uuid.uuid4().hex}/", args.imovel_vendido):
        status, _, _ = buscar(base + caminho)
        if status != 404:
            falha(f"{caminho} respondeu {status} (esperado 404 real)")

    # sitemap
    status, _, xml = buscar(base + "/sitemap.xml")
    if status != 200:
        falha(f"sitemap.xml respondeu {status}")
        return 1
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in ElementTree.fromstring(xml).findall("s:url/s:loc", ns)]
    if args.limite:
        urls = urls[: args.limite]

    for url in urls:
        path = url[len(base):] if url.startswith(base) else "/" + url.split("/", 3)[-1]
        print(path)
        status, h, html = buscar(base + path)
        if status != 200:
            falha(f"{path}: HTTP {status}{' → ' + h.get('location', '') if 300 <= status < 400 else ''}")
            continue
        if "noindex" in h.get("x-robots-tag", "").lower():
            falha(f"{path}: X-Robots-Tag com noindex ({h['x-robots-tag']})")
        if "noindex" in meta_robots(html).lower():
            falha(f"{path}: <meta robots> com noindex")
        if canonical(html).rstrip("/") != url.rstrip("/"):
            falha(f"{path}: canonical '{canonical(html)}' difere de '{url}'")
        if "__cf_email__" in html or "cdn-cgi/scripts" in html:
            falha(f"{path}: a CDN ofuscou e-mail e injetou script (bloqueado pela CSP). Desative "
                  f"'Email Address Obfuscation' no Cloudflare ou envolva o e-mail em <!--email_off-->")
        ok, nos = jsonld_ok(html)
        if not ok:
            falha(f"{path}: JSON-LD ausente ou inválido no HTML bruto")
        cache = h.get("cf-cache-status") or h.get("x-cache") or "-"
        print(f"  status 200 · JSON-LD {nos} nós · cache CDN: {cache} · age: {h.get('age', '-')}")

        referencia = corpo_hash(html)
        for nome, ua in UA_BOTS.items():
            s_bot, h_bot, html_bot = buscar(base + path, ua)
            if s_bot != 200:
                falha(f"{path}: {nome} recebeu HTTP {s_bot} (bloqueio/challenge da CDN?)")
            elif corpo_hash(html_bot) != referencia:
                falha(f"{path}: conteúdo servido a {nome} difere do navegador")
            elif "noindex" in h_bot.get("x-robots-tag", "").lower():
                falha(f"{path}: {nome} recebeu X-Robots-Tag noindex")

        if args.origem:
            s_o, _, html_o = buscar(args.origem.rstrip("/") + path)
            if s_o != 200 or corpo_hash(html_o) != referencia:
                falha(f"{path}: resposta da CDN difere da origem (cache desatualizado ou corrompido?)")

    print(f"\n{len(urls)} URLs verificadas · {len(problemas)} problema(s)")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
