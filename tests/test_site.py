"""Testes de contrato: SSR sem JS, status HTTP, JSON-LD, robots, conteúdo visível e bot logs."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from seo.bots import identify  # noqa: E402
from seo.formatting import brl  # noqa: E402
from seo.jsonld import AMENIDADES_OBRIGATORIAS  # noqa: E402

AI_BOTS = ["GPTBot", "OAI-SearchBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "Bytespider"]


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    log = tmp_path_factory.mktemp("logs") / "bots.jsonl"
    app = create_app(bot_log=log)
    return app.test_client(), app.config["REPO"], log


def paginas(repo):
    return [p for p, _ in repo.paginas_indexaveis()]


def grafo(html: str) -> list[dict]:
    blocos = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert len(blocos) == 1, "cada página deve ter exatamente um bloco JSON-LD no <head>"
    head = html.split("</head>")[0]
    assert blocos[0] in head, "JSON-LD deve estar no <head>"
    return json.loads(blocos[0])["@graph"]


def por_tipo(nodes: list[dict], tipo: str) -> list[dict]:
    return [n for n in nodes if tipo == n["@type"] or (isinstance(n["@type"], list) and tipo in n["@type"])]


# ------------------------------------------------------------ HTTP / SSR
def test_todas_as_paginas_indexaveis_respondem_200_sem_noindex(ctx):
    client, repo, _ = ctx
    for path in paginas(repo):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "noindex" not in r.headers.get("X-Robots-Tag", ""), path
        html = r.get_data(as_text=True)
        assert 'content="noindex' not in html, path
        assert f'<link rel="canonical" href="{client.application.config["BASE_URL"]}{path}">' in html, path


@pytest.mark.parametrize("path", ["/nao-existe/", "/imoveis/nao-existe/", "/guias/x/", "/bairros/x/",
                                  "/especialistas/x/", "/imoveis/cobertura-meireles-410m2/"])
def test_404_real_sem_soft_404(ctx, path):
    client, _, _ = ctx
    r = client.get(path)
    assert r.status_code == 404
    assert "X-Robots-Tag" not in r.headers or "index, follow" not in r.headers["X-Robots-Tag"]
    assert '<meta name="robots" content="noindex">' in r.get_data(as_text=True)


def test_imovel_vendido_informa_venda_com_status_404(ctx):
    client, _, _ = ctx
    r = client.get("/imoveis/cobertura-meireles-410m2/")
    assert r.status_code == 404
    assert "não está mais disponível" in r.get_data(as_text=True)


def test_sem_javascript_e_sem_conteudo_oculto(ctx):
    client, repo, _ = ctx
    for path in paginas(repo):
        html = client.get(path).get_data(as_text=True)
        scripts = re.findall(r"<script\b[^>]*>", html)
        assert scripts == ['<script type="application/ld+json">'], path
        for proibido in ("<details", "hidden", 'role="tab"', "aria-expanded", "display:none", "<select"):
            assert proibido not in html, f"{path}: {proibido}"


def test_cabecalhos_de_cache_e_seguranca(ctx):
    client, _, _ = ctx
    r = client.get("/")
    assert "s-maxage=600" in r.headers["Cache-Control"]
    assert "script-src 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Content-Language"] == "pt-BR"
    assert "max-age=60" in client.get("/x/").headers["Cache-Control"]


# ---------------------------------------------------------- conteúdo core
def test_ficha_do_imovel_exibe_todos_os_dados_criticos_no_html(ctx):
    client, repo, _ = ctx
    for i in repo.ativos():
        html = client.get(i["path"]).get_data(as_text=True)
        main = html.split('<main id="conteudo"')[1]
        for valor in (brl(i["preco"]), brl(i["preco_m2"]), brl(i["iptu_anual"]), f"Rw {i['tecnico']['rw_db']} dB",
                      f"Nível {i['tecnico']['blindagem_nivel']}", *AMENIDADES_OBRIGATORIAS):
            assert valor in main, f"{i['slug']}: {valor}"
        condominio = brl(i["condominio_mensal"]) if i["condominio_mensal"] else "Não se aplica"
        assert condominio in main
        assert "<table>" in main and "<thead>" in main and "<tbody>" in main
        assert "youtube-nocookie.com/embed/" in main


def test_resumo_do_imovel_coerente_com_preco_m2_calculado(ctx):
    _, repo, _ = ctx
    for i in repo.ativos():
        assert brl(i["preco_m2"]) in i["resumo"], i["slug"]
        assert brl(i["preco"]).replace("R$ ", "") in i["resumo"], i["slug"]


def test_links_internos_resolvem(ctx):
    client, repo, _ = ctx
    vistos = set()
    for path in paginas(repo):
        html = client.get(path).get_data(as_text=True)
        vistos.update(re.findall(r'href="(/[^"#?]*)', html))
    quebrados = [h for h in sorted(vistos) if client.get(h).status_code != 200]
    assert not quebrados, quebrados


def test_outdoor_transfere_autoridade_para_core(ctx):
    client, repo, _ = ctx
    for a in repo.artigos.values():
        html = client.get(a["path"]).get_data(as_text=True)
        corpo = html.split('id="resumo-executivo"')[1].split('id="perguntas"')[0]
        paragrafos = re.findall(r"<p>(.*?)</p>", corpo, re.S)
        contextuais = {h for p in paragrafos for h in re.findall(r'href="(/(?:imoveis|bairros)/[^"]+)"', p)}
        assert contextuais, f"{a['slug']}: sem links contextuais para a Seção Core"


# ---------------------------------------------------------------- JSON-LD
def test_jsonld_imovel(ctx):
    client, repo, _ = ctx
    for i in repo.ativos():
        nodes = grafo(client.get(i["path"]).get_data(as_text=True))
        listing = por_tipo(nodes, "RealEstateListing")[0]
        oferta = por_tipo(nodes, "Offer")[0]
        casa = por_tipo(nodes, i["schema_type"])[0]
        assert oferta["price"] == i["preco"] and oferta["priceCurrency"] == "BRL"
        assert casa["floorSize"]["unitCode"] == "MTK" and casa["floorSize"]["value"] == i["area_privativa"]
        nomes = {a["name"] for a in casa["amenityFeature"]}
        assert set(AMENIDADES_OBRIGATORIAS) <= nomes
        assert all(a["@type"] == "LocationFeatureSpecification" for a in casa["amenityFeature"])
        assert listing["offers"]["@id"] == oferta["@id"] and oferta["itemOffered"]["@id"] == casa["@id"]
        assert casa["containedInPlace"]["@id"] in {n["@id"] for n in por_tipo(nodes, "Place")}
        assert por_tipo(nodes, "VideoObject") and por_tipo(nodes, "BreadcrumbList")


def test_jsonld_artigo_conectado_a_organizacao_e_pessoa(ctx):
    client, repo, _ = ctx
    for a in repo.artigos.values():
        nodes = grafo(client.get(a["path"]).get_data(as_text=True))
        artigo = por_tipo(nodes, "Article")[0]
        org = por_tipo(nodes, "RealEstateAgent")[0]
        pessoa = por_tipo(nodes, "Person")[0]
        assert artigo["publisher"]["@id"] == org["@id"]
        assert artigo["author"]["@id"] == pessoa["@id"]
        assert pessoa["worksFor"]["@id"] == org["@id"]
        assert any("linkedin.com" in s for s in pessoa["sameAs"])


def test_jsonld_referencias_internas_resolvem(ctx):
    client, repo, _ = ctx
    for path in paginas(repo):
        nodes = grafo(client.get(path).get_data(as_text=True))
        ids: set[str] = set()

        def definidos(obj):  # nós com @id + propriedades, em qualquer nível
            if isinstance(obj, dict):
                if "@id" in obj and len(obj) > 1:
                    ids.add(obj["@id"])
                for v in obj.values():
                    definidos(v)
            elif isinstance(obj, list):
                for v in obj:
                    definidos(v)

        definidos(nodes)
        refs = set(re.findall(r'\{"@id": "([^"]+)"\}', json.dumps(nodes, ensure_ascii=False)))
        pendentes = {r for r in refs if r not in ids and "/especialistas/" not in r
                     and not r.endswith("#webpage")}
        assert not pendentes, f"{path}: {pendentes}"


# ------------------------------------------------------- robots / sitemap
def test_robots_libera_bots_de_ia_e_recursos(ctx):
    client, _, _ = ctx
    robots = client.get("/robots.txt").get_data(as_text=True)
    for bot in AI_BOTS:
        assert f"User-agent: {bot}" in robots
    assert "Disallow" not in robots
    assert "Sitemap: " in robots


def test_sitemap_lista_somente_urls_200(ctx):
    client, repo, _ = ctx
    xml = client.get("/sitemap.xml").get_data(as_text=True)
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    assert len(locs) == len(paginas(repo))
    assert not any("cobertura-meireles-410m2" in loc for loc in locs)


# ------------------------------------------------------------- bot logs
def test_bot_access_log(ctx):
    client, _, log = ctx
    client.get("/imoveis/", headers={"User-Agent": "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"})
    client.get("/guias/", headers={"User-Agent": "Mozilla/5.0 (compatible; ClaudeBot/1.0)"})
    client.get("/", headers={"User-Agent": "Mozilla/5.0 Chrome/140"})
    entradas = [json.loads(linha) for linha in log.read_text(encoding="utf-8").splitlines()]
    assert {(e["bot"], e["path"]) for e in entradas} >= {("GPTBot", "/imoveis/"), ("ClaudeBot", "/guias/")}
    assert all(e["ia"] for e in entradas if e["operador"] in ("OpenAI", "Anthropic"))
    assert not any(e["path"] == "/" and e["bot"] is None for e in entradas)


@pytest.mark.parametrize("ua,esperado", [
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0)", "OAI-SearchBot"),
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "Googlebot"),
    ("Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36 (compatible; Bytespider)", "Bytespider"),
    ("Mozilla/5.0 (Windows NT 10.0) Chrome/140 Safari/537.36", None),
])
def test_identificacao_de_bots(ua, esperado):
    resultado = identify(ua)
    assert (resultado[0] if resultado else None) == esperado


# ------------------------------------------------------------ subpasta
def test_publicacao_em_subpasta_prefixa_links(tmp_path, monkeypatch):
    monkeypatch.setenv("SITE_URL", "https://exemplo.com.br/altopadrao")
    client = create_app(bot_log=tmp_path / "b.jsonl").test_client()
    html = client.get("/imoveis/cobertura-duplex-mucuripe-480m2/").get_data(as_text=True)
    raiz = re.findall(r'(?:href|src)="(/[^"]*)"', html)
    assert raiz and all(u.startswith("/altopadrao/") for u in raiz), [u for u in raiz if not u.startswith("/altopadrao/")]
    assert '<link rel="canonical" href="https://exemplo.com.br/altopadrao/imoveis/cobertura-duplex-mucuripe-480m2/">' in html
    assert '"url": "https://exemplo.com.br/altopadrao/imoveis/cobertura-duplex-mucuripe-480m2/"' in html
    assert client.get("/nao-existe/").status_code == 404
