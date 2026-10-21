"""Vídeos, respostas rápidas (fan-out), PageRank interno e relatório de logs."""
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
def test_videos_da_ficha_no_html_e_no_json_ld(ctx):
    client, repo = ctx
    com_video = [i for i in repo.ativos() if i["videos"]]
    assert com_video
    for i in com_video:
        html = client.get(i["path"]).get_data(as_text=True)
        assert html.count("youtube-nocookie.com/embed/") == len(i["videos"]), i["slug"]
        videos = tipos(grafo(html), "VideoObject")
        assert len(videos) == len(i["videos"]) and all("actor" not in v for v in videos)
        assert not tipos(grafo(html), "Person")


def test_guias_sem_video_provisorio(ctx):
    """Vídeo só com gravação real: nenhum guia publica ID provisório."""
    _, repo = ctx
    assert not any("SUBSTITUA" in v["youtube_id"] for a in repo.artigos.values() for v in a["videos"])


def test_paginas_de_especialistas_nao_existem(ctx):
    client, repo = ctx
    assert client.get("/especialistas/").status_code == 404
    assert not any("/especialistas/" in p for p, _ in repo.paginas_indexaveis())
    assert 'href="/especialistas/' not in client.get("/").get_data(as_text=True)


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
        # alíquotas da Sefin-Fortaleza: 4% geral e 2% pago antes da escritura (data/site.json)
        assert brl(round(i["preco"] * 0.04)) in html and brl(round(i["preco"] * 0.02)) in html, "ITBI calculado"
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
