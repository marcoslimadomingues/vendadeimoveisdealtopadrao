"""Ficha vendida: continua no ar (200), sem oferta nem preço anunciado, e só mostra o valor da venda se autorizado."""
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
from seo.content import Repo  # noqa: E402
from seo.formatting import brl  # noqa: E402

SLUG = "apartamento-aldeota-260m2"
PATH = f"/imoveis/{SLUG}/"


def montar(tmp_path: Path, **campos) -> tuple:
    """Cópia dos dados com um imóvel ativo marcado como vendido."""
    dados = tmp_path / "data"
    shutil.copytree(ROOT / "data", dados)
    arq = dados / "imoveis.json"
    imoveis = json.loads(arq.read_text(encoding="utf-8"))
    for i in imoveis:
        if i["slug"] == SLUG:
            i.update({"status": "vendido", "data_venda": "2026-10-01", **campos})
            preco = i["preco"]
    arq.write_text(json.dumps(imoveis, ensure_ascii=False), encoding="utf-8")
    app = create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")
    return app.test_client(), app.config["REPO"], preco


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def test_vendido_continua_200_e_indexavel(tmp_path):
    client, repo, _ = montar(tmp_path, dias_no_mercado=41)
    r = client.get(PATH)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert r.headers["X-Robots-Tag"].startswith("index, follow") or "noindex" in r.headers["X-Robots-Tag"]
    assert f'<link rel="canonical" href="https://vendadeimoveisdealtopadrao.com.br{PATH}">' in html
    assert "Vendido em <time" in html and "1 de outubro de 2026" in html
    assert "<h1 id=\"titulo-imovel\">" in html and "(vendido)" in html
    assert "41 dias" in html
    assert PATH in [p for p, _ in repo.paginas_indexaveis()]
    xml = client.get("/sitemap.xml").get_data(as_text=True)
    assert f"{PATH}</loc>\n    <lastmod>2026-10-01</lastmod>" in xml
    assert SLUG not in [i["slug"] for i in repo.ativos()] and SLUG in [i["slug"] for i in repo.vendidos()]


def test_vendido_nao_mostra_preco_anunciado_nem_oferta(tmp_path):
    client, _, preco = montar(tmp_path, dias_no_mercado=41, preco_venda=3_200_000)
    html = client.get(PATH).get_data(as_text=True)
    # só a ficha: os cards de imóveis parecidos (ativos) abaixo dela mostram preço normalmente
    corpo = html.split('<article class="ficha"')[1].split("</article>")[0]
    assert brl(preco) not in corpo and brl(3_200_000) not in corpo
    for ausente in ("Preço de venda", "Preço por m²", "Custos mensais", "ITBI", "Agendar visita"):
        assert ausente not in corpo, ausente
    nos = grafo(html)
    tipos = {t for n in nos for t in ([n["@type"]] if isinstance(n["@type"], str) else n["@type"])}
    assert "Offer" not in tipos
    pagina = next(n for n in nos if n["@id"].endswith("#webpage"))
    assert "offers" not in pagina and pagina["dateModified"] == "2026-10-01"
    imovel = next(n for n in nos if n["@id"].endswith("#imovel"))
    props = {p["name"]: p["value"] for p in imovel["additionalProperty"]}
    assert props["Situação"] == "Vendido" and props["Data da venda"] == "2026-10-01"
    assert "Valor da venda" not in props and "Preço por m²" not in props
    assert "foi vendido em 1 de outubro de 2026" in imovel["description"]


def test_valor_da_venda_so_com_autorizacao(tmp_path):
    client, _, preco = montar(tmp_path, preco_venda=3_200_000, preco_venda_autorizado=True)
    html = client.get(PATH).get_data(as_text=True)
    assert "Valor da venda" in html and brl(3_200_000) in html
    assert "95,5%" in html  # 3.200.000 / 3.350.000
    imovel = next(n for n in grafo(html) if n["@id"].endswith("#imovel"))
    assert {"Valor da venda": 3_200_000}.items() <= {p["name"]: p["value"] for p in imovel["additionalProperty"]}.items()
    assert brl(preco) in html  # preço anunciado só aparece como base do percentual, dentro do FAQ


def test_autorizado_sem_valor_e_erro(tmp_path):
    with pytest.raises(ValueError, match="preco_venda_autorizado sem preco_venda"):
        montar(tmp_path, preco_venda_autorizado=True)


def test_faq_do_vendido(tmp_path):
    client, _, _ = montar(tmp_path)
    html = client.get(PATH).get_data(as_text=True)
    perguntas = [n for n in grafo(html) if n["@type"] == "Question"]
    nomes = " | ".join(q["name"] for q in perguntas)
    assert "ainda está disponível" in nomes and "Por quanto" in nomes
    assert "ITBI" not in nomes and "preço por metro quadrado" not in nomes.lower()
    assert any("O valor da venda não é divulgado." == q["acceptedAnswer"]["text"] for q in perguntas)
    for q in perguntas:
        assert q["name"] in html


def test_vendido_aparece_em_imoveis_sem_preco_e_leva_a_captacao(tmp_path):
    client, _, preco = montar(tmp_path, dias_no_mercado=41)
    lista = client.get("/imoveis/").get_data(as_text=True)
    secao = lista.split('id="vendidos"')[1].split("</section>")[0]
    assert f'href="{PATH}"' in secao and brl(preco) not in secao
    assert f'href="{PATH}"' not in lista.split('id="vendidos"')[0].split('id="catalogo"')[1].split("</section>")[0]
    ficha = client.get(PATH).get_data(as_text=True)
    assert "Tem um imóvel parecido para vender?" in ficha
    assert "Imóveis parecidos disponíveis agora" in ficha
    assert "wa.me/5585988631025?text=" in ficha and "avaliar+a+venda" in ficha.replace("%20", "+")


def test_llms_txt_lista_vendidos(tmp_path):
    client, _, _ = montar(tmp_path, dias_no_mercado=41)
    txt = client.get("/llms.txt").get_data(as_text=True)
    assert "## Vendidos recentemente" in txt and PATH in txt and "41 dias no mercado" in txt


def test_registro_minimo_de_vendido_continua_404():
    from app import create_app as criar
    r = criar().test_client().get("/imoveis/cobertura-meireles-410m2/")
    assert r.status_code == 404
    assert Repo().vendidos() == []
