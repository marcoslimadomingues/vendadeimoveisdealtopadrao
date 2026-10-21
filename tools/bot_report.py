"""Relatório de Bot Access Logs: varredura por agente, por URL e por seção, com diagnóstico
de links internos (PageRank interno) para páginas pouco visitadas por agentes de IA.

O volume de acessos de cada agente é o proxy de "consideração" da página pelos modelos.
Quando fichas de imóveis (Seção Core) ou guias (Seção Outdoor) têm pouca varredura, o
relatório mostra quantos links contextuais apontam para elas, a profundidade de clique
a partir da home e quais páginas muito varridas ainda não linkam para elas.

Fontes aceitas:
  - JSONL gerado pelo app Flask (logs/bot_access.jsonl)                  --jsonl
  - access log no formato "combined" (Apache/LiteSpeed/Nginx/cPanel)      --combined

Uso:
  python tools/bot_report.py --combined logs/servidor/altopadrao.log --prefixo /altopadrao
  python tools/bot_report.py --jsonl logs/bot_access.jsonl --dias 30 --csv relatorio.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seo.bots import AI_OPERATORS, identify  # noqa: E402

COMBINED = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<metodo>\S+) (?P<path>\S+)[^"]*" '
    r'(?P<status>\d{3}) (?P<bytes>\S+) "[^"]*" "(?P<ua>[^"]*)"'
)
SECOES = (("/milha-de-ouro-", "Pilar · milha de ouro"), ("/imoveis/", "Core · fichas de imóveis"), ("/bairros/", "Core · bairros"),
          ("/guias/", "Outdoor · guias"), ("/sobre/", "E-E-A-T · sobre"))


# ------------------------------------------------------------------ leitura
def ler_jsonl(caminho: Path):
    with caminho.open(encoding="utf-8") as fh:
        for linha in fh:
            if linha.strip():
                e = json.loads(linha)
                e["ts"] = datetime.fromisoformat(e["ts"])
                yield e


def ler_combined(caminho: Path, prefixo: str = ""):
    with caminho.open(encoding="utf-8", errors="replace") as fh:
        for linha in fh:
            m = COMBINED.match(linha)
            if not m:
                continue
            bot = identify(m["ua"])
            if bot is None:
                continue
            path = m["path"].split("?")[0]
            if prefixo:
                if not (path == prefixo or path.startswith(prefixo + "/")):
                    continue
                path = path[len(prefixo):] or "/"
            assinatura, operador, finalidade = bot
            yield {
                "ts": datetime.strptime(m["ts"], "%d/%b/%Y:%H:%M:%S %z"),
                "bot": assinatura, "operador": operador, "finalidade": finalidade,
                "ia": operador in AI_OPERATORS, "path": path,
                "status": int(m["status"]), "ip": m["ip"], "ua": m["ua"],
            }


# --------------------------------------------------------- links internos
def mapa_links() -> tuple[dict[str, set[str]], dict[str, int]]:
    """(entradas contextuais por página, profundidade de clique a partir da home).

    Contextuais = links dentro de <main>, excluindo menu e rodapé (presentes em todas as páginas).
    """
    import os
    import tempfile

    os.environ.pop("SITE_URL", None)  # rotas sem prefixo de subpasta
    from app import create_app

    app = create_app(bot_log=Path(tempfile.gettempdir()) / "bot_report_mapa.jsonl")
    client, repo = app.test_client(), app.config["REPO"]
    paginas = [p for p, _ in repo.paginas_indexaveis()]
    entradas: dict[str, set[str]] = defaultdict(set)
    saidas: dict[str, set[str]] = {}
    for origem in paginas:
        html = client.get(origem).get_data(as_text=True)
        todos = set(re.findall(r'href="(/[^"#?]*)', html))
        saidas[origem] = {h for h in todos if h in paginas and h != origem}
        principal = html.split('<main id="conteudo"', 1)[-1].split("</main>", 1)[0]
        for destino in set(re.findall(r'href="(/[^"#?]*)', principal)):
            if destino != origem and destino in paginas:
                entradas[destino].add(origem)
    profundidade = {"/": 0}
    fila = deque(["/"])
    while fila:
        atual = fila.popleft()
        for prox in saidas.get(atual, ()):
            if prox not in profundidade:
                profundidade[prox] = profundidade[atual] + 1
                fila.append(prox)
    return {p: entradas.get(p, set()) for p in paginas}, profundidade


# ------------------------------------------------------------------ relatório
def gerar(eventos: list[dict], dias: int, fonte: str) -> tuple[str, dict]:
    linhas: list[str] = []
    out = linhas.append
    por_bot = Counter(e["bot"] for e in eventos)
    matriz: dict[str, Counter] = defaultdict(Counter)
    ultimo: dict[str, datetime] = {}
    erros = Counter()
    for e in eventos:
        matriz[e["path"]][e["bot"]] += 1
        ultimo[e["path"]] = max(ultimo.get(e["path"], e["ts"]), e["ts"])
        if e["status"] >= 400:
            erros[(e["path"], e["status"])] += 1
    ia_por_url = {p: sum(n for b, n in c.items() if identify(b)[1] in AI_OPERATORS) for p, c in matriz.items()}

    out(f"# Bot Access Log — últimos {dias} dias")
    out(f"Fonte: {fonte} · {len(eventos)} requisições de bots · gerado em {datetime.now():%Y-%m-%d %H:%M}\n")

    out("## Requisições por agente")
    for bot, n in por_bot.most_common():
        _, operador, finalidade = identify(bot)
        out(f"- {bot} ({operador}, {finalidade}): {n}")
    if not por_bot:
        out("- Nenhum acesso de bot no período.")

    entradas, profundidade = mapa_links()
    indexaveis = list(entradas)

    out("\n## Varredura de IA por seção")
    for prefixo, nome in SECOES:
        paginas = [p for p in indexaveis if p.startswith(prefixo) and p != prefixo]
        total = sum(ia_por_url.get(p, 0) for p in paginas)
        zeradas = sum(1 for p in paginas if ia_por_url.get(p, 0) == 0)
        out(f"- {nome}: {total} acessos de IA em {len(paginas)} páginas · {zeradas} sem nenhum acesso")

    out("\n## URLs mais varridas por agentes de IA")
    for path, n in sorted(ia_por_url.items(), key=lambda kv: kv[1], reverse=True)[:25]:
        agentes = ", ".join(f"{b}:{k}" for b, k in matriz[path].most_common(4))
        out(f"- {n:>4} · {path} · último: {ultimo[path]:%Y-%m-%d} · [{agentes}]")

    # Páginas Core/Outdoor com baixa varredura → diagnóstico de links internos
    alvo = [p for p in indexaveis if p.startswith(("/imoveis/", "/guias/")) and p not in ("/imoveis/", "/guias/")]
    valores = [ia_por_url.get(p, 0) for p in indexaveis]
    mediana = statistics.median(valores) if valores else 0
    limite = max(1, mediana * 0.5)
    fracas = sorted((p for p in alvo if ia_por_url.get(p, 0) < limite), key=lambda p: ia_por_url.get(p, 0))
    mais_varridas = [p for p, _ in sorted(ia_por_url.items(), key=lambda kv: kv[1], reverse=True) if p in entradas]

    out(f"\n## Fichas e guias com baixa varredura de IA (abaixo de {limite:g} acessos; mediana do site: {mediana:g})")
    if not fracas:
        out("- Nenhuma. O fluxo de links internos está distribuindo a descoberta.")
    for p in fracas:
        fontes = entradas[p]
        sugeridas = [s for s in mais_varridas if s not in fontes and s != p][:3]
        out(f"- {p} · IA: {ia_por_url.get(p, 0)} · links contextuais de entrada: {len(fontes)} · "
            f"profundidade a partir da home: {profundidade.get(p, '∞')} clique(s)")
        if len(fontes) < 3:
            out("  - Ação: menos de 3 links contextuais. Inclua links dentro de parágrafos (não só em cards).")
        if profundidade.get(p, 99) > 2:
            out("  - Ação: mais de 2 cliques da home. Leve a página para a home, o catálogo ou o rodapé.")
        if sugeridas:
            out(f"  - Linkar a partir de (páginas mais varridas que ainda não apontam para ela): {', '.join(sugeridas)}")

    sem_ia = sorted(p for p in indexaveis if ia_por_url.get(p, 0) == 0)
    out(f"\n## URLs do sitemap sem nenhum acesso de IA ({len(sem_ia)})")
    for p in sem_ia:
        out(f"- {p}")

    if erros:
        out("\n## Erros servidos a bots (confira 404 legítimo × link quebrado)")
        for (path, status), n in erros.most_common(20):
            out(f"- {status} · {n}x · {path}")
    return "\n".join(linhas) + "\n", {"matriz": matriz, "ia_por_url": ia_por_url, "bots": sorted(por_bot)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    fonte = parser.add_mutually_exclusive_group()
    fonte.add_argument("--jsonl", default=str(ROOT / "logs" / "bot_access.jsonl"))
    fonte.add_argument("--combined", help="access log no formato combined")
    parser.add_argument("--prefixo", default="", help="subpasta publicada, ex.: /altopadrao")
    parser.add_argument("--dias", type=int, default=30, help="janela de análise (padrão: 30)")
    parser.add_argument("--csv", help="exporta matriz URL × agente em CSV")
    parser.add_argument("--saida", help="grava o relatório em Markdown neste arquivo")
    args = parser.parse_args()

    caminho = Path(args.combined or args.jsonl)
    if not caminho.exists():
        raise SystemExit(f"Arquivo de log não encontrado: {caminho}")
    eventos = ler_combined(caminho, args.prefixo.rstrip("/")) if args.combined else ler_jsonl(caminho)
    desde = datetime.now(timezone.utc) - timedelta(days=args.dias)
    eventos = [e for e in eventos if e["ts"] >= desde and not e["path"].startswith("/static/")]

    texto, dados = gerar(eventos, args.dias, str(caminho))
    print(texto)
    if args.saida:
        Path(args.saida).write_text(texto, encoding="utf-8")
        print(f"Relatório gravado: {args.saida}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["url", "total_ia", *dados["bots"]])
            for path in sorted(dados["matriz"], key=lambda p: dados["ia_por_url"][p], reverse=True):
                w.writerow([path, dados["ia_por_url"][path], *(dados["matriz"][path][b] for b in dados["bots"])])
        print(f"CSV exportado: {args.csv}")


if __name__ == "__main__":
    main()
