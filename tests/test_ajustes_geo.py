"""Vídeos com especialistas, respostas rápidas (fan-out), PageRank interno e relatório de logs."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from seo.formatting import brl  # noqa: E402

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("logs") / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def grafo(html: str) -> list[dict]:
    bloco = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    return json.loads(bloco)["@graph"]


def tipos(nodes, tipo):
    return [n for n in nodes if n["@type"] == tipo or (isinstance(n["@type"], list) and tipo in n["@type"])]


# ------------------------------------------------------------------- vídeos
def test_ficha_tem_tour_e_analise_tecnica_da_arquiteta(ctx):
    client, repo = ctx
    for i in repo.ativos():
        html = client.get(i["path"]).get_data(as_text=True)
        assert html.count("youtube-nocookie.com/embed/") >= 2, i["slug"]
        assert {v["apresentador"] for v in i["videos"]} >= {i["consultor"], "marina-albuquerque"}
        videos = tipos(grafo(html), "VideoObject")
        assert len(videos) == len(i["videos"])
        pessoas = {p["@id"] for p in tipos(grafo(html), "Person")}
        assert all(v["actor"]["@id"] in pessoas for v in videos), "apresentador precisa estar no grafo"


def test_guia_de_holding_tem_videos_da_advogada(ctx):
    client, repo = ctx
    a = repo.artigos["holding-familiar-imoveis-alto-padrao"]
    assert len(a["videos"]) >= 2 and all(v["apresentador"] == "carolina-ribeiro" for v in a["videos"])
    html = client.get(a["path"]).get_data(as_text=True)
    artigo = tipos(grafo(html), "Article")[0]
    assert len(artigo["video"]) == len(a["videos"])


def test_todos_os_guias_tem_video(ctx):
    _, repo = ctx
    assert all(a["videos"] for a in repo.artigos.values())


def test_perfil_lista_videos_apresentados(ctx):
    client, repo = ctx
    html = client.get("/especialistas/marina-albuquerque/").get_data(as_text=True)
    assert "Vídeos apresentados por Marina Albuquerque" in html
    pessoa = tipos(grafo(html), "Person")[0]
    assert len(pessoa["subjectOf"]) == len(repo.videos_por_pessoa("marina-albuquerque")) >= 6


# ------------------------------------------------------- respostas rápidas
@pytest.mark.parametrize("slug,termos", [
    ("holding-familiar-imoveis-alto-padrao", ["alíquota do ITBI", "alíquota do ITCD", "prazo para abrir inventário",
                                              "ganho de capital", "Quanto tempo leva cada etapa"]),
    ("isolamento-acustico-blindagem-gerador-imoveis-luxo", ["Como o índice Rw é medido", "C e Ctr", "ISO 16283-3", "aço inox 316", "ISO 9223"]),
])
def test_guias_respondem_subperguntas_tecnicas_e_juridicas(ctx, slug, termos):
    client, repo = ctx
    html = client.get(repo.artigos[slug]["path"]).get_data(as_text=True)
    assert '<div class="rapidas">' in html
    for termo in termos:
        assert termo in html, termo
    perguntas = tipos(grafo(html), "Question")
    assert len(perguntas) == len(repo.artigos[slug]["perguntas_todas"])


def test_ficha_responde_itbi_prazo_e_medicao(ctx):
    client, repo = ctx
    for i in repo.ativos():
        html = client.get(i["path"]).get_data(as_text=True)
        assert brl(round(i["preco"] * 0.03)) in html, "ITBI calculado"
        assert "10 dias úteis" in html and "ISO 10140-2" in html
        for grupo in ("Preço e custos", "Tributos e prazos da compra", "Medições técnicas"):
            assert f'<h3 class="faq__grupo">{grupo}</h3>' in html


# -------------------------------------------------------- PageRank interno
def test_fichas_se_linkam_e_catalogo_e_bairros_linkam_guias(ctx):
    client, repo = ctx
    guias = {a["path"] for a in repo.artigos.values()}
    for i in repo.ativos():
        main = client.get(i["path"]).get_data(as_text=True).split('<main id="conteudo"')[1]
        outras = {o["path"] for o in repo.ativos() if o["slug"] != i["slug"]}
        assert outras <= set(re.findall(r'href="([^"]+)"', main)), i["slug"]
    for path in ["/imoveis/", *(b["path"] for b in repo.bairros.values())]:
        main = client.get(path).get_data(as_text=True).split('<main id="conteudo"')[1]
        assert guias <= set(re.findall(r'href="([^"]+)"', main)), path


def test_relatorio_de_logs_com_prefixo(tmp_path):
    import bot_report

    ua = "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"
    from datetime import datetime
    ts = datetime.now().strftime("%d/%b/%Y:%H:%M:%S -0300")
    log = tmp_path / "access.log"
    log.write_text(
        f'1.1.1.1 - - [{ts}] "GET /altopadrao/imoveis/cobertura-duplex-mucuripe-480m2/ HTTP/2" 200 10 "-" "{ua}"\n'
        f'1.1.1.1 - - [{ts}] "GET /blog/ HTTP/2" 200 10 "-" "{ua}"\n', encoding="utf-8")
    eventos = list(bot_report.ler_combined(log, "/altopadrao"))
    assert [e["path"] for e in eventos] == ["/imoveis/cobertura-duplex-mucuripe-480m2/"]
    texto, dados = bot_report.gerar(eventos, 30, str(log))
    assert dados["ia_por_url"]["/imoveis/cobertura-duplex-mucuripe-480m2/"] == 1
    assert "## Fichas e guias com baixa varredura de IA" in texto
    assert "/guias/holding-familiar-imoveis-alto-padrao/" in texto.split("baixa varredura")[1]
