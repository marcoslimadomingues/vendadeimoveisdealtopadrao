"""Pilar "Milha de ouro": toda cifra tem fonte e data; números do texto batem com os indicadores."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from seo.formatting import brl  # noqa: E402

PATH = "/milha-de-ouro-fortaleza/"


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("logs") / "b.jsonl")
    repo = app.config["REPO"]
    return app.test_client(), repo, repo.pilares["milha-de-ouro-fortaleza"]


def grafo(html: str) -> list[dict]:
    bloco = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    return json.loads(bloco)["@graph"]


def tipos(nodes, tipo):
    return [n for n in nodes if n["@type"] == tipo or (isinstance(n["@type"], list) and tipo in n["@type"])]


def test_pilar_no_ar_no_sitemap_e_nos_links(ctx):
    client, repo, _ = ctx
    r = client.get(PATH)
    assert r.status_code == 200 and "noindex" not in r.headers.get("X-Robots-Tag", "")
    assert PATH in [p for p, _ in repo.paginas_indexaveis()]
    assert f"<loc>http://localhost{PATH}</loc>" in client.get("/sitemap.xml").get_data(as_text=True).replace(
        client.application.config["BASE_URL"], "http://localhost")
    for origem in ("/", "/bairros/meireles/", "/bairros/mucuripe/",
                   "/imoveis/cobertura-duplex-mucuripe-480m2/", "/imoveis/apartamento-meireles-beira-mar-320m2/"):
        assert f'href="{PATH}"' in client.get(origem).get_data(as_text=True), origem


def test_toda_cifra_tem_fonte_data_e_url(ctx):
    _, _, p = ctx
    for i in p["indicadores"]:
        assert i["fonte"] in p["fontes"] and i["fonte_info"]["url"].startswith("https://"), i["id"]
        assert i["referencia"] and i["origem"], i["id"]
    html_fontes = {f["url"] for f in p["fontes"].values()}
    assert len(html_fontes) == 2


def test_tabela_exibe_valor_fonte_e_data_de_cada_indicador(ctx):
    client, _, p = ctx
    html = client.get(PATH).get_data(as_text=True)
    tabela = html.split('id="preco-m2"')[1].split("</table>")[0]
    for i in p["indicadores"]:
        assert brl(i["valor"]) in tabela, i["id"]
        assert i["fonte_info"]["url"] in tabela, i["id"]
        assert i["ref_txt"] in tabela, i["id"]
    assert "perto de R$ 25.000" in tabela, "valor aproximado da coluna deve ser marcado como aproximado"
    assert "não aparece no levantamento de agosto de 2026" in tabela


def test_numeros_derivados_batem_com_os_indicadores(ctx):
    client, _, p = ctx
    ind = p["indic"]
    assert p["derivados"]["meireles_vs_cidade"] == pytest.approx((ind["meireles"]["valor"] / ind["fortaleza"]["valor"] - 1) * 100)
    html = client.get(PATH).get_data(as_text=True)
    assert f"{p['derivados']['meireles_vs_cidade']:.1f}".replace(".", ",") + "%" in html
    # o texto nunca cita um valor de m² que não esteja na tabela de indicadores
    permitidos = {brl(i["valor"]) for i in p["indicadores"]} | {brl(ind["meireles"]["valor_anterior"]), "R$ 25.000"}
    texto = re.sub(r"<[^>]+>", " ", html.split('id="resumo-executivo"')[1].split('id="sumario"')[0])
    for valor in re.findall(r"R\$ \d{1,3}(?:\.\d{3})+", texto):  # só cifras com separador de milhar
        assert valor in permitidos, valor


def test_geografia_vem_do_openstreetmap_e_e_consistente(ctx):
    client, _, p = ctx
    g = p["geo"]
    assert g["fonte"] == "OpenStreetMap" and 2 < g["extensao_km"] < 6
    assert [pt["km"] for pt in g["pontos"]] == sorted(pt["km"] for pt in g["pontos"])
    assert all(0 <= pt["km"] <= g["extensao_km"] + 0.2 for pt in g["pontos"])
    assert len({r["nome"] for r in g["transversais"]}) == len(g["transversais"])
    html = client.get(PATH).get_data(as_text=True)
    assert "colaboradores do OpenStreetMap" in html
    assert (ROOT / "static" / "img" / "mapa-milha-de-ouro.svg").is_file()
    assert re.search(r'<img[^>]*src="[^"]*mapa-milha-de-ouro\.svg[^"]*"[^>]*alt="Mapa esquemático', html)


def test_jsonld_do_pilar(ctx):
    client, _, p = ctx
    nodes = grafo(client.get(PATH).get_data(as_text=True))
    assert tipos(nodes, "Article") and tipos(nodes, "Place") and tipos(nodes, "Dataset")
    pagina = tipos(nodes, "FAQPage")[0]
    assert pagina["reviewedBy"]["@id"].endswith("/especialistas/marina-albuquerque/#pessoa")
    assert len(tipos(nodes, "Question")) == len(p["faq"]) == 8
    fontes = tipos(nodes, "NewsArticle")
    assert {f["publisher"]["name"] for f in fontes} == {"Diário do Nordeste", "O Povo"}
    dataset = tipos(nodes, "Dataset")[0]
    assert len(dataset["variableMeasured"]) == len(p["indicadores"])
    assert all(v["unitText"] == "BRL/m²" for v in dataset["variableMeasured"])
    lugar = [n for n in tipos(nodes, "Place") if n["@id"].endswith(f"{PATH}#lugar")][0]
    assert lugar["geo"]["latitude"] == p["geo"]["centro_aprox"]["lat"]


def test_dado_nao_verificado_nao_aparece(ctx):
    """Preço/entrega/metragem de prédios reais não vêm de fonte verificada: não podem aparecer."""
    client, _, _ = ctx
    html = client.get(PATH).get_data(as_text=True)
    secao = html.split('id="empreendimentos"')[1].split("</section>")[0]
    assert "Wave Beira-Mar" in secao and "Dasart" in secao
    assert not re.search(r"R\$ [\d.]+", secao)
    assert not re.search(r"\d+ ?m²", secao)
