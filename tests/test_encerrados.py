"""Ciclo de vida do imóvel sem exclusividade: ativo -> não disponível (200) ou redirecionado ao bairro."""
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
from seo.content import DATA_DIR, Repo  # noqa: E402
from seo.formatting import brl  # noqa: E402

SLUG = "apartamento-aldeota-260m2"
PATH = f"/imoveis/{SLUG}/"


def desvincular_guias(dados: Path) -> None:
    """Guia que cita imóvel redirecionado quebra o build de propósito; aqui os desvinculamos."""
    arq = dados / "artigos.json"
    artigos = json.loads(arq.read_text(encoding="utf-8"))
    for a in artigos:
        a["imoveis_relacionados"] = []
    arq.write_text(json.dumps(artigos, ensure_ascii=False), encoding="utf-8")


def montar(tmp_path: Path, status: str = "vendido", minimo: bool = False, **campos):
    """Cópia dos dados com um imóvel ativo encerrado (`minimo`: só código, título, bairro e data)."""
    dados = tmp_path / "data"
    shutil.copytree(DATA_DIR, dados)
    arq = dados / "imoveis.json"
    imoveis = json.loads(arq.read_text(encoding="utf-8"))
    base = {"data_venda": "2026-10-01"} if status == "vendido" else {"data_saida": "2026-10-01"}
    for n, i in enumerate(imoveis):
        if i["slug"] == SLUG:
            preco = i["preco"]
            if minimo:
                i = {k: i[k] for k in ("slug", "codigo", "titulo", "bairro")}
            i.update({"status": status, **base, **campos})
            imoveis[n] = i
    arq.write_text(json.dumps(imoveis, ensure_ascii=False), encoding="utf-8")
    if campos.get("redirecionar_para_bairro"):
        desvincular_guias(dados)
    app = create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")
    return app.test_client(), app.config["REPO"], preco


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def corpo_ficha(html: str) -> str:
    return html.split('<article class="ficha"')[1].split("</article>")[0]


# ---------------------------------------------------------------- página no ar
@pytest.mark.parametrize("status", ["vendido", "indisponivel"])
def test_encerrado_continua_200_e_diz_nao_esta_mais_disponivel(tmp_path, status):
    client, repo, _ = montar(tmp_path, status, dias_no_mercado=41)
    r = client.get(PATH)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert f'<link rel="canonical" href="https://vendadeimoveisdealtopadrao.com.br{PATH}">' in html
    assert "Não está mais disponível desde <time" in html and "1 de outubro de 2026" in html
    assert "(indisponível)" in html and "41 dias" in html
    # sem exclusividade: nunca afirma venda intermediada por nós
    texto = corpo_ficha(html)
    for proibido in ("foi vendido", "Vendido em", "vendido por nós", "vendemos"):
        assert proibido not in texto, proibido
    assert PATH in [p for p, _ in repo.paginas_indexaveis()]
    assert f"{PATH}</loc>\n    <lastmod>2026-10-01</lastmod>" in client.get("/sitemap.xml").get_data(as_text=True)
    assert SLUG not in [i["slug"] for i in repo.ativos()] and SLUG in [i["slug"] for i in repo.encerrados()]


def test_json_ld_offer_soldout_e_outofstock(tmp_path):
    for status, esperado in (("vendido", "https://schema.org/SoldOut"), ("indisponivel", "https://schema.org/OutOfStock")):
        sub = tmp_path / status
        sub.mkdir()
        client, _, preco = montar(sub, status, dias_no_mercado=41)
        nos = grafo(client.get(PATH).get_data(as_text=True))
        oferta = next(n for n in nos if n["@type"] == "Offer")
        assert oferta["availability"] == esperado
        assert "price" not in oferta, "preço anunciado não é republicado depois que o imóvel sai"
        pagina = next(n for n in nos if n["@id"].endswith("#webpage"))
        assert pagina["offers"]["@id"] == oferta["@id"] and pagina["dateModified"] == "2026-10-01"
        imovel = next(n for n in nos if n["@id"].endswith("#imovel"))
        props = {p["name"]: p["value"] for p in imovel["additionalProperty"]}
        assert props["Situação"] == "Não está mais disponível" and props["Indisponível desde"] == "2026-10-01"
        assert "Preço por m²" not in props and "Valor da venda" not in props


def test_sem_preco_anunciado_nem_custos_na_ficha(tmp_path):
    client, _, preco = montar(tmp_path, dias_no_mercado=41, preco_venda=3_200_000)
    html = client.get(PATH).get_data(as_text=True)
    corpo = corpo_ficha(html)
    assert brl(preco) not in corpo and brl(3_200_000) not in corpo
    for ausente in ("Preço de venda", "Preço por m²", "Custos mensais", "ITBI", "Agendar visita"):
        assert ausente not in corpo, ausente


def test_valor_da_venda_so_com_autorizacao_e_so_em_vendido(tmp_path):
    client, _, preco = montar(tmp_path, preco_venda=3_200_000, preco_venda_autorizado=True)
    html = client.get(PATH).get_data(as_text=True)
    assert "Valor da venda" in html and brl(3_200_000) in html and "95,5%" in html
    imovel = next(n for n in grafo(html) if n["@id"].endswith("#imovel"))
    assert {p["name"]: p["value"] for p in imovel["additionalProperty"]}["Valor da venda"] == 3_200_000
    # indisponivel não tem venda: preco_venda é erro de cadastro
    with pytest.raises(ValueError, match="preco_venda não se aplica"):
        montar(tmp_path / "x", "indisponivel", preco_venda=1)


def test_autorizado_sem_valor_e_erro(tmp_path):
    with pytest.raises(ValueError, match="preco_venda_autorizado sem preco_venda"):
        montar(tmp_path, preco_venda_autorizado=True)


def test_encerrado_exige_a_data_do_status(tmp_path):
    with pytest.raises(ValueError, match="exige data_saida"):
        montar(tmp_path, "indisponivel", data_saida=None)


def test_faq_do_encerrado(tmp_path):
    client, _, _ = montar(tmp_path, "indisponivel")
    html = client.get(PATH).get_data(as_text=True)
    perguntas = [n for n in grafo(html) if n["@type"] == "Question"]
    nomes = " | ".join(q["name"] for q in perguntas)
    assert "ainda está disponível" in nomes and "ITBI" not in nomes
    assert "Por quanto" not in nomes, "indisponivel não fala em valor de venda"
    for q in perguntas:
        assert q["name"] in html
    vendido, _, _ = montar(tmp_path / "v", "vendido")
    assert any(q["acceptedAnswer"]["text"] == "O valor da venda não é divulgado."
               for q in grafo(vendido.get(PATH).get_data(as_text=True)) if q["@type"] == "Question")


def test_encerrado_em_listas_sem_preco_e_com_captacao(tmp_path):
    client, _, preco = montar(tmp_path, dias_no_mercado=41)
    lista = client.get("/imoveis/").get_data(as_text=True)
    secao = lista.split('id="encerrados"')[1].split("</section>")[0]
    assert f'href="{PATH}"' in secao and brl(preco) not in secao
    assert f'href="{PATH}"' not in lista.split('id="encerrados"')[0].split('id="catalogo"')[1].split("</section>")[0]
    ficha = client.get(PATH).get_data(as_text=True)
    assert "Tem um imóvel parecido para vender?" in ficha and "Imóveis parecidos disponíveis agora" in ficha
    assert "wa.me/5585988631025?text=" in ficha
    txt = client.get("/llms.txt").get_data(as_text=True)
    assert "## Imóveis que saíram da carteira" in txt and PATH in txt and "ficou 41 dias no mercado" in txt


def test_registro_minimo_continua_404():
    r = create_app().test_client().get("/imoveis/cobertura-meireles-410m2/")
    assert r.status_code == 404 and "não está mais disponível" in r.get_data(as_text=True)
    assert Repo().encerrados() == []


# ------------------------------------------------------------ redirecionamento
@pytest.mark.parametrize("minimo", [False, True])
def test_redirecionamento_para_o_bairro(tmp_path, minimo):
    client, repo, _ = montar(tmp_path, minimo=minimo, redirecionar_para_bairro=True)
    r = client.get(PATH)
    html = r.get_data(as_text=True)
    destino = "https://vendadeimoveisdealtopadrao.com.br/bairros/aldeota/"
    assert r.status_code == 200
    assert f'<meta http-equiv="refresh" content="0; url={destino}">' in html
    assert f'<link rel="canonical" href="{destino}">' in html
    assert 'href="/bairros/aldeota/"' in html, "link visível para quem não segue o refresh"
    # fora do sitemap, das listas e do llms.txt; ainda exportado como arquivo
    assert PATH not in [p for p, _ in repo.paginas_indexaveis()] and PATH in repo.paginas_redirecionadas()
    for url in ("/sitemap.xml", "/llms.txt", "/imoveis/", "/"):
        assert PATH not in client.get(url).get_data(as_text=True), url
    assert SLUG not in [i["slug"] for i in repo.ativos()] and repo.encerrados() == []


def test_redirecionar_exige_status_encerrado(tmp_path):
    with pytest.raises(ValueError, match="redirecionar_para_bairro só vale"):
        dados = tmp_path / "data"
        shutil.copytree(DATA_DIR, dados)
        arq = dados / "imoveis.json"
        imoveis = json.loads(arq.read_text(encoding="utf-8"))
        imoveis[0]["redirecionar_para_bairro"] = True
        arq.write_text(json.dumps(imoveis, ensure_ascii=False), encoding="utf-8")
        create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")


def test_exportacao_estatica_inclui_a_pagina_de_redirecionamento(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "tools"))
    monkeypatch.setenv("SITE_NOINDEX", "0")
    dados = tmp_path / "data"
    shutil.copytree(DATA_DIR, dados)
    arq = dados / "imoveis.json"
    imoveis = json.loads(arq.read_text(encoding="utf-8"))
    for i in imoveis:
        if i["slug"] == SLUG:
            i.update(status="indisponivel", data_saida="2026-10-01", redirecionar_para_bairro=True)
    arq.write_text(json.dumps(imoveis, ensure_ascii=False), encoding="utf-8")
    desvincular_guias(dados)
    from seo import content
    monkeypatch.setattr(content, "DATA_DIR", dados)
    from tools.export_static import exportar
    saida = tmp_path / "out"
    paginas = exportar(saida)
    assert PATH in paginas
    assert 'http-equiv="refresh"' in (saida / PATH.strip("/") / "index.html").read_text(encoding="utf-8")
