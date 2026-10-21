"""Cluster 1 (Milha de ouro): satélites sob o pilar, números só dos indicadores e links nos dois sentidos."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from seo.content import TOKEN  # noqa: E402

PILAR = "/milha-de-ouro-fortaleza/"
SAT_M2 = "/milha-de-ouro-fortaleza/preco-m2-beira-mar/"
SAT_INV = "/guias/meireles-ou-mucuripe-investir/"
DOMINIO = "https://vendadeimoveisdealtopadrao.com.br"


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("l") / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def titulo(html: str) -> str:
    return re.search(r"<title>(.*?)</title>", html)[1]


def descricao(html: str) -> str:
    return re.search(r'<meta name="description" content="(.*?)">', html)[1]


@pytest.mark.parametrize("path", [SAT_M2, SAT_INV])
def test_padroes_tecnicos_do_satelite(ctx, path):
    client, _ = ctx
    r = client.get(path)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 30 <= len(titulo(html)) <= 60 and titulo(html).endswith("| Alto Padrão Imóveis"), titulo(html)
    assert 70 <= len(descricao(html)) <= 160, len(descricao(html))
    assert f'<link rel="canonical" href="{DOMINIO}{path}">' in html
    assert len(re.findall(r"<h1\b", html)) == 1
    assert '<meta property="og:title"' in html
    resumo = re.search(r'<p class="lead">(.*?)</p>', html, re.S)[1]
    assert 40 <= len(re.sub(r"<[^>]+>", "", resumo).split()) <= 60, "resposta direta de 40 a 60 palavras"
    nos = grafo(html)
    assert any(n["@type"] == "Article" for n in nos)
    perguntas = [n for n in nos if n["@type"] == "Question"]
    assert perguntas and all(q["name"] in html for q in perguntas), "FAQPage só com perguntas visíveis"
    assert "{" not in html.split("</head>")[1].split("<footer")[0], "token sem expandir"


def test_url_unica_do_satelite_sob_o_pilar(ctx):
    client, _ = ctx
    assert client.get("/guias/preco-m2-beira-mar/").status_code == 404
    assert client.get("/outro-pilar/preco-m2-beira-mar/").status_code == 404
    assert client.get("/milha-de-ouro-fortaleza/meireles-ou-mucuripe-investir/").status_code == 404


def test_pilar_linka_todos_os_satelites_e_eles_linkam_o_pilar(ctx):
    client, repo = ctx
    pilar = client.get(PILAR).get_data(as_text=True)
    cards = pilar.split('id="guias-relacionados"')[1]
    for sat in (SAT_M2, SAT_INV):
        assert f'href="{sat}"' in cards, f"{sat} fora dos guias relacionados do pilar"
        assert f'href="{sat}"' in pilar.split('id="preco-m2"')[1].split("<table>")[0], "link contextual no pilar"
        html = client.get(sat).get_data(as_text=True)
        assert f'href="{PILAR}"' in html
        assert "Parte do pilar" in html
    assert set(repo.pilares["milha-de-ouro-fortaleza"]["guias"]) >= {"preco-m2-beira-mar", "meireles-ou-mucuripe-investir"}


def test_satelites_no_sitemap_e_no_llms(ctx):
    client, _ = ctx
    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    llms = client.get("/llms.txt").get_data(as_text=True)
    for sat in (SAT_M2, SAT_INV):
        assert f"{DOMINIO}{sat}</loc>" in sitemap
        assert f"]({DOMINIO}{sat})" in llms


def test_numeros_batem_com_os_indicadores_do_pilar(ctx):
    client, repo = ctx
    ind = repo.pilares["milha-de-ouro-fortaleza"]["indic"]
    html = client.get(SAT_M2).get_data(as_text=True)
    assert "R$ 23.892" in html and "R$ 20.391" in html and "R$ 20.529" in html and "R$ 12.350" in html
    assert f"R$ {ind['beira_mar']['valor'] * 300:,.0f}".replace(",", ".") in html  # 300 m² × m²
    assert "julho de 2026" in html and "agosto de 2026" in html
    inv = client.get(SAT_INV).get_data(as_text=True)
    assert "R$ 138" in inv and "0,7%" in inv  # 20.529 - 20.391 e 20.529/20.391 - 1


def test_token_invalido_falha_o_build(tmp_path):
    import shutil
    dados = tmp_path / "data"
    shutil.copytree(ROOT / "data", dados)
    arq = dados / "artigos.json"
    artigos = json.loads(arq.read_text(encoding="utf-8"))
    for a in artigos:
        if a["slug"] == "preco-m2-beira-mar":
            a["resumo"] += " {m2:inexistente}"
    arq.write_text(json.dumps(artigos, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="indicador inexistente"):
        create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")


def test_imoveis_da_regiao_aparecem_nos_satelites(ctx):
    client, repo = ctx
    esperados = [i["path"] for i in repo.ativos() if i["bairro"] in ("meireles", "mucuripe")]
    assert esperados
    for sat in (SAT_M2, SAT_INV):
        html = client.get(sat).get_data(as_text=True)
        for path in esperados:
            assert f'href="{path}"' in html, (sat, path)


def test_json_ld_da_organizacao_sem_thing_e_com_tipo_unico(ctx):
    client, _ = ctx
    nos = grafo(client.get("/").get_data(as_text=True))
    tipos = [n["@type"] for n in nos]
    assert "Thing" not in tipos and "Organization" not in tipos
    org = next(n for n in nos if n["@id"].endswith("#organizacao"))
    assert org["@type"] == "RealEstateAgent"
    ids = {n["@id"] for n in nos}
    about = next(n for n in nos if n["@id"].endswith("#website"))["about"]["@id"]
    assert about in ids, "about aponta para um nó existente (Service)"


def test_checklist_sem_marcador_preencher():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "pre_publicacao.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert "✓ Marcadores [PREENCHER: ...] em guias e páginas" in r.stdout
    assert TOKEN.pattern  # tokens não vazam para o checklist
