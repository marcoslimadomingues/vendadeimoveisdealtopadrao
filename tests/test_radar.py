"""Radar de lançamentos: edições semanais no próprio domínio, cada fato com fonte publicada.

Regras do usuário: o radar é a versão pública da pesquisa semanal. Estratégia interna (concorrentes,
palavras-chave, proposta comercial) e nomes de imobiliárias concorrentes ficam fora; incorporadora citada
em notícia pública pode aparecer, com a fonte.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from seo.content import DATA_DIR  # noqa: E402

INTERNO = ("Alexandre Muniz", "concorrente", "palavra-chave", "palavras-chave", "SEO", "GEO", "AEO",
           "pacote", "Marcos", "claude.ai")


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def montar(tmp_path: Path, editar=None):
    dados = tmp_path / "data"
    shutil.copytree(DATA_DIR, dados)
    if editar:
        editar(dados)
    app = create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def editar_radar(fn):
    def editar(dados: Path):
        arq = dados / "radar.json"
        radar = json.loads(arq.read_text(encoding="utf-8"))
        fn(radar)
        arq.write_text(json.dumps(radar, ensure_ascii=False), encoding="utf-8")
    return editar


def test_menu_sitemap_e_llms_listam_o_radar(tmp_path):
    client, repo = montar(tmp_path)
    e = repo.radar_edicoes()[0]
    home = client.get("/").get_data(as_text=True)
    menu = home.split('class="menu"')[1].split("</ul>")[0]
    assert '<a href="/radar/"' in menu and "Radar de lançamentos" in menu
    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/radar/</loc>" in sitemap and f"{e['path']}</loc>" in sitemap
    assert "/radar/" in client.get("/llms.txt").get_data(as_text=True)


def test_edicao_cita_fonte_de_cada_fato_e_nao_vaza_estrategia_interna(tmp_path):
    client, repo = montar(tmp_path)
    for e in repo.radar_edicoes():
        r = client.get(e["path"])
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        corpo = html.split('<main id="conteudo"')[1].split("</main>")[0]
        for f in e["fontes_lista"]:
            assert f'href="{f["url"]}"' in corpo
        for termo in INTERNO:
            assert termo not in corpo, termo
        artigo = next(n for n in grafo(html) if n["@type"] == "NewsArticle")
        assert artigo["datePublished"] == e["publicado"]
        assert {c["url"] for c in artigo["citation"]} == {f["url"] for f in e["fontes_lista"]}
        assert artigo["author"] == artigo["publisher"]  # autoria da empresa, sem pessoa


def test_indice_aponta_a_edicao_mais_recente(tmp_path):
    def nova(radar):
        e = json.loads(json.dumps(radar[0]))
        e["slug"] = e["publicado"] = "2099-01-01"
        e["titulo"] = "Edição de teste"
        radar.append(e)
    client, repo = montar(tmp_path, editar_radar(nova))
    anterior = repo.radar_edicoes()[1]["path"]
    html = client.get("/radar/").get_data(as_text=True)
    assert html.index("/radar/2099-01-01/") < html.index(anterior)
    assert 'href="/radar/2099-01-01/"' in client.get(anterior).get_data(as_text=True)


def test_item_com_varias_fontes_cita_todas(tmp_path):
    client, repo = montar(tmp_path)
    for e in repo.radar_edicoes():
        corpo = client.get(e["path"]).get_data(as_text=True).split('<main id="conteudo"')[1]
        for item in [*e["lancamentos"], *e["mercado"]]:
            for k in item["fontes_item"]:
                assert f'[{e["fonte_n"][k]}]' in corpo and f'href="{e["fontes"][k]["url"]}"' in corpo


@pytest.mark.parametrize("quebrar, erro", [
    (lambda r: r[0]["mercado"][0].update(fonte="inexistente"), "não cadastrada"),
    (lambda r: r[0]["fontes"]["dn-2026-09-16"].update(url="http://x.com"), "url https"),
    (lambda r: r[0]["lancamentos"][0].update(bairro="praia_iracema"), "bairro 'praia_iracema' inexistente"),
    (lambda r: r[0].update(slug="primeira"), "slug deve ser a data"),
    (lambda r: r[0]["fontes"].update(sobra={"veiculo": "X", "publicado": "2026-01-01", "url": "https://x.com"}),
     "não citada"),
])
def test_dado_sem_fonte_quebra_o_build(tmp_path, quebrar, erro):
    with pytest.raises(ValueError, match=erro):
        montar(tmp_path, editar_radar(quebrar))


def test_sem_radar_o_menu_some_e_a_rota_e_404(tmp_path):
    client, repo = montar(tmp_path, lambda d: (d / "radar.json").unlink())
    assert client.get("/radar/").status_code == 404
    assert 'href="/radar/"' not in client.get("/").get_data(as_text=True)
    assert all(not p.startswith("/radar/") for p, _ in repo.paginas_indexaveis())
