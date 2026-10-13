"""Cluster 2 (liquidez por bairro): só indicadores do Sinduscon-CE, com fonte e mês; sem métrica interna sem fonte."""
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

GUIA = "/guias/preco-m2-por-bairro-fortaleza/"
PILAR_GUIA = "/guias/liquidez-imoveis-alto-padrao-por-bairro-fortaleza/"
BAIRROS = ("meireles", "mucuripe", "aldeota", "coco", "guararapes")
DOMINIO = "https://vendadeimoveisdealtopadrao.com.br"


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("l") / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def corpo(html: str) -> str:
    return html.split('<main id="conteudo"')[1].split("</main>")[0]


def test_dados_do_sinduscon_conferem_com_a_reportagem(ctx):
    _, repo = ctx
    sd = repo.sinduscon
    esperado = {"praia_iracema": 21698, "mucuripe": 20529, "meireles": 20391, "aldeota": 16660,
                "dionisio_torres": 14811, "fatima": 14386, "edson_queiroz": 13904, "coco": 13449,
                "guararapes": 13346, "jose_bonifacio": 13042}
    assert {b["id"]: b["m2"] for b in sd["bairros"]} == esperado
    assert sd["fortaleza"]["m2"] == 12350 and sd["referencia"] == "2026-08"
    assert sd["fonte"]["url"].startswith("https://www.opovo.com.br/") and sd["fonte"]["publicado"] == "2026-09-30"
    posicoes = [b["id"] for b in sd["ranking"]]
    assert posicoes == list(esperado), "ranking ordenado pelo m²"
    assert round(sd["por_id"]["praia_iracema"]["var_mes_pct"], 2) == 53.94  # citado na reportagem
    assert round(sd["por_id"]["meireles"]["var_mes_pct"], 2) == 1.53
    assert round(sd["por_id"]["aldeota"]["var_mes_pct"], 2) == -0.48


@pytest.mark.parametrize("slug", BAIRROS)
def test_pagina_do_bairro_so_com_indicador_publico(ctx, slug):
    client, repo = ctx
    b = repo.bairros[slug]
    html = client.get(f"/bairros/{slug}/").get_data(as_text=True)
    texto = corpo(html)
    assert f"R$ {b['sinduscon']['m2']:,.0f}".replace(",", ".") in texto
    assert 'href="https://www.opovo.com.br/' in texto and "Sinduscon-CE" in texto
    assert f'href="{GUIA}"' in texto and f'href="{PILAR_GUIA}"' in texto
    # o bloco do bairro (antes dos cards de guias, que descrevem outro guia) não tem métrica interna
    bloco = html.split('id="analises"')[0]
    for interno in ("valorizou", "Valorização em 12 meses", "Tempo médio de venda", "Desconto médio de negociação",
                    "entre julho de 2025 e junho de 2026"):
        assert interno not in bloco, f"{slug}: métrica interna sem fonte pública ({interno})"
    assert re.search(r"<title>Preço do m² (no|na) .+ em 2026 \| Alto Padrão Imóveis</title>", html)
    dataset = next(n for n in grafo(html) if n["@type"] == "Dataset")
    assert dataset["isBasedOn"]["publisher"]["name"] == "O Povo" and dataset["temporalCoverage"] == "2026-08"
    valores = {v["name"]: v["value"] for v in dataset["variableMeasured"]}
    assert valores["Preço médio do m² (agosto de 2026)"] == b["sinduscon"]["m2"]


def test_meta_description_do_bairro_e_resposta_direta(ctx):
    client, repo = ctx
    for slug in BAIRROS:
        html = client.get(f"/bairros/{slug}/").get_data(as_text=True)
        desc = re.search(r'<meta name="description" content="(.*?)">', html)[1]
        assert "Sinduscon-CE" in desc and "agosto de 2026" in desc and desc.startswith(("No ", "Na "))
        palavras = re.sub(r"<[^>]+>", "", repo.bairros[slug]["resumo"]).split()
        assert 35 <= len(palavras) <= 60, (slug, len(palavras))


def test_guia_do_ranking_padroes_tecnicos(ctx):
    client, repo = ctx
    html = client.get(GUIA).get_data(as_text=True)
    titulo = re.search(r"<title>(.*?)</title>", html)[1]
    desc = re.search(r'<meta name="description" content="(.*?)">', html)[1]
    assert 30 <= len(titulo) <= 60 and titulo.endswith("| Alto Padrão Imóveis")
    assert 70 <= len(desc) <= 160
    assert f'<link rel="canonical" href="{DOMINIO}{GUIA}">' in html and len(re.findall(r"<h1\b", html)) == 1
    resumo = re.search(r'<p class="lead">(.*?)</p>', html, re.S)[1]
    assert 40 <= len(resumo.split()) <= 60
    linhas = re.findall(r"<tr[^>]*>\s*<th scope=\"row\">(\d+)º</th>", html)
    assert linhas == [str(n) for n in range(1, 11)], "os 10 bairros, em ordem"
    assert "{" not in corpo(html), "token sem expandir"
    perguntas = [n for n in grafo(html) if n["@type"] == "Question"]
    assert perguntas and all(q["name"] in html for q in perguntas)
    assert "Parte do guia" in html and f'href="{PILAR_GUIA}"' in html


def test_guia_pilar_lista_o_satelite_e_sitemap_llms(ctx):
    client, repo = ctx
    pilar = client.get(PILAR_GUIA).get_data(as_text=True)
    assert "Aprofunde este guia" in pilar and f'href="{GUIA}"' in pilar.split("Aprofunde este guia")[1]
    assert [a["slug"] for a in repo.satelites_do_guia("liquidez-imoveis-alto-padrao-por-bairro-fortaleza")] == [
        "preco-m2-por-bairro-fortaleza"]
    assert f"{DOMINIO}{GUIA}</loc>" in client.get("/sitemap.xml").get_data(as_text=True)
    assert f"]({DOMINIO}{GUIA})" in client.get("/llms.txt").get_data(as_text=True)


def test_ficha_compara_com_o_m2_do_sinduscon_e_sem_prazo_interno(ctx):
    client, repo = ctx
    for i in repo.ativos():
        b = repo.bairros[i["bairro"]]
        assert i["dif_bairro_pct"] == round((i["preco_m2"] / b["sinduscon"]["m2"] - 1) * 100, 1)
        html = client.get(i["path"]).get_data(as_text=True)
        assert "Sinduscon-CE" in corpo(html)
        perguntas = [n["name"] for n in grafo(html) if n["@type"] == "Question"]
        assert not any("leva para vender" in q for q in perguntas), "prazo de venda interno saiu da ficha"
        ficha = html.split('<article class="ficha"')[1].split("</article>")[0]
        assert "Desconto médio de negociação" not in ficha and "Tempo médio de venda" not in ficha


def test_home_e_faq_institucional_usam_o_sinduscon(ctx):
    client, repo = ctx
    perguntas = {q["q"]: q["a"] for q in repo.faq_institucional()}
    assert "Qual bairro de Fortaleza tem o m² mais caro?" in perguntas
    assert "Praia de Iracema" in perguntas["Qual bairro de Fortaleza tem o m² mais caro?"]
    assert "Sinduscon-CE" in perguntas["Os preços por m² são de que fonte e período?"]


def test_token_de_bairro_inexistente_falha_o_build(tmp_path):
    dados = tmp_path / "data"
    shutil.copytree(ROOT / "data", dados)
    arq = dados / "artigos.json"
    artigos = json.loads(arq.read_text(encoding="utf-8"))
    for a in artigos:
        if a["slug"] == "preco-m2-por-bairro-fortaleza":
            a["resumo"] += " {sm2:bairro_que_nao_existe}"
    arq.write_text(json.dumps(artigos, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="bairro inexistente"):
        create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")


def test_sinduscon_sem_url_de_fonte_e_erro(tmp_path):
    dados = tmp_path / "data"
    shutil.copytree(ROOT / "data", dados)
    arq = dados / "sinduscon.json"
    sd = json.loads(arq.read_text(encoding="utf-8"))
    sd["fonte"]["url"] = ""
    arq.write_text(json.dumps(sd, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="fonte sem url"):
        create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")
