"""Clusters 3 (tributação) e 4 (critérios técnicos): valores oficiais, cálculo conferido e padrões técnicos."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from seo.content import itcd_calcular  # noqa: E402
from seo.formatting import brl  # noqa: E402

DOMINIO = "https://vendadeimoveisdealtopadrao.com.br"
PILAR_TRIB = "/guias/holding-familiar-imoveis-alto-padrao/"
PILAR_TEC = "/guias/isolamento-acustico-blindagem-gerador-imoveis-luxo/"
TRIBUTACAO = ["/guias/itbi-fortaleza-imoveis-alto-padrao/", "/guias/itcd-ceara-imoveis/",
              "/guias/comprar-imovel-pessoa-fisica-ou-holding/"]
TECNICOS = ["/guias/protecao-contra-maresia-imoveis-fortaleza/", "/guias/isolamento-acustico-rw-imoveis-fortaleza/",
            "/guias/blindagem-abnt-nbr-15000-portaria-imoveis/", "/guias/gerador-100-carga-imoveis-alto-padrao/"]


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("l") / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def corpo(html: str) -> str:
    return html.split('<main id="conteudo"')[1].split("</main>")[0]


# ------------------------------------------------------------------ valores oficiais
def test_parametros_do_itbi_sao_os_da_sefin(ctx):
    _, repo = ctx
    itbi = repo.site["itbi"]
    assert (itbi["aliquota"], itbi["aliquota_antecipada"], itbi["sfh_aliquota"]) == (0.04, 0.02, 0.005)
    assert itbi["sfh_teto"] == 390672.24 and itbi["sfh_ano"] == 2026
    assert "ibs.sefin.fortaleza.ce.gov.br" in itbi["fonte_url"]


def test_parametros_do_itcd_sao_os_da_lei_e_da_instrucao_normativa(ctx):
    _, repo = ctx
    c = repo.site["itcd"]
    assert c["ufirce"] == 6.29872 and c["ufirce_ano"] == 2026 and c["isencao_ufirces"] == 7000
    assert c["causa_mortis"] == [[10000, 0.02], [20000, 0.04], [40000, 0.06], [None, 0.08]]
    assert c["doacao"] == [[25000, 0.02], [150000, 0.04], [250000, 0.06], [None, 0.08]]


def itcd_por_integral(faixas, ufirces):
    """Cálculo independente: soma de fatias, com um laço simples."""
    total, inicio = 0.0, 0.0
    for limite, aliq in faixas:
        fim = ufirces if limite is None else min(limite, ufirces)
        if fim > inicio:
            total += (fim - inicio) * aliq
        if limite is None or ufirces <= limite:
            break
        inicio = limite
    return total


@pytest.mark.parametrize("valor", [100_000, 300_000, 3_000_000, 5_000_000, 10_000_000, 25_000_000])
def test_itcd_confere_com_calculo_independente(ctx, valor):
    _, repo = ctx
    c = repo.site["itcd"]
    u = valor / c["ufirce"]
    esperado_h = itcd_por_integral(c["causa_mortis"], max(0.0, u - 7000)) * c["ufirce"]
    esperado_d = itcd_por_integral(c["doacao"], u) * c["ufirce"]
    esperado_n = itcd_por_integral(c["doacao"], u * 2 / 3) * c["ufirce"]
    assert itcd_calcular(repo.site, valor, "causa_mortis")["imposto"] == pytest.approx(esperado_h)
    assert itcd_calcular(repo.site, valor, "doacao")["imposto"] == pytest.approx(esperado_d)
    assert itcd_calcular(repo.site, valor, "doacao", nua_propriedade=True)["imposto"] == pytest.approx(esperado_n)


def test_itcd_herdeiro_ate_a_isencao_nao_paga(ctx):
    _, repo = ctx
    assert itcd_calcular(repo.site, 7000 * 6.29872, "causa_mortis")["imposto"] == 0
    assert itcd_calcular(repo.site, 6.29872 * 10_000, "doacao")["imposto"] == pytest.approx(10_000 * 6.29872 * 0.02)


def test_tabelas_do_guia_batem_com_o_calculo(ctx):
    client, repo = ctx
    html = client.get("/guias/itcd-ceara-imoveis/").get_data(as_text=True)
    for v in repo.VALORES_EXEMPLO:
        assert brl(itcd_calcular(repo.site, v, "causa_mortis")["imposto"]) in html
        assert brl(itcd_calcular(repo.site, v, "doacao")["imposto"]) in html
        assert brl(itcd_calcular(repo.site, v, "doacao", nua_propriedade=True)["imposto"]) in html
    itbi = client.get("/guias/itbi-fortaleza-imoveis-alto-padrao/").get_data(as_text=True)
    for v, geral, antec in ((3_000_000, 120_000, 60_000), (5_000_000, 200_000, 100_000), (15_000_000, 600_000, 300_000)):
        assert brl(v) in itbi and brl(geral) in itbi and brl(antec) in itbi


# ------------------------------------------------------------------ nada de dado antigo no site
def test_nenhuma_pagina_repete_o_itbi_de_3_por_cento(ctx):
    client, repo = ctx
    paginas = [p for p, _ in repo.paginas_indexaveis()] + ["/llms.txt"]
    for path in paginas:
        txt = re.sub(r"<[^>]+>", " ", client.get(path).get_data(as_text=True))
        assert not re.search(r"ITBI[^.]{0,120}\b3 ?%", txt), path
        assert "R$ 174 mil" not in txt and "0,5% sobre o valor financiado e 2% sobre o restante" not in txt, path


def test_pilar_holding_corrigido(ctx):
    client, _ = ctx
    html = client.get(PILAR_TRIB).get_data(as_text=True)
    for esperado in ("alíquota geral de 4%", "R$ 390.672,24", "Tema 1.348", "R$ 251.949", "Tema 1.113"):
        assert esperado in html, esperado


# ------------------------------------------------------------------ padrões técnicos de cada guia
@pytest.mark.parametrize("path", TRIBUTACAO + TECNICOS)
def test_padroes_tecnicos(ctx, path):
    client, repo = ctx
    r = client.get(path)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    titulo = re.search(r"<title>(.*?)</title>", html)[1]
    desc = re.search(r'<meta name="description" content="(.*?)">', html)[1]
    assert 30 <= len(titulo) <= 60 and titulo.endswith("| Alto Padrão Imóveis"), (titulo, len(titulo))
    assert 70 <= len(desc) <= 160, (len(desc), desc)
    assert f'<link rel="canonical" href="{DOMINIO}{path}">' in html and len(re.findall(r"<h1\b", html)) == 1
    resumo = re.sub(r"<[^>]+>", "", re.search(r'<p class="lead">(.*?)</p>', html, re.S)[1])
    assert 40 <= len(resumo.split()) <= 60, len(resumo.split())
    assert "{" not in corpo(html), "token sem expandir"
    perguntas = [n for n in grafo(html) if n["@type"] == "Question"]
    assert perguntas and all(q["name"] in html for q in perguntas)
    assert 'href="/bairros/' in corpo(html), "link contextual para a Seção Core"
    assert f"{DOMINIO}{path}</loc>" in client.get("/sitemap.xml").get_data(as_text=True)
    assert f"]({DOMINIO}{path})" in client.get("/llms.txt").get_data(as_text=True)


@pytest.mark.parametrize("pilar,satelites", [(PILAR_TRIB, TRIBUTACAO), (PILAR_TEC, TECNICOS)])
def test_pilar_liga_a_todos_os_satelites_e_eles_ligam_ao_pilar(ctx, pilar, satelites):
    client, _ = ctx
    html_pilar = client.get(pilar).get_data(as_text=True)
    aprofunde = html_pilar.split('id="aprofunde"')[1]
    for sat in satelites:
        assert f'href="{sat}"' in aprofunde, f"{sat} fora do bloco 'Aprofunde este guia'"
        html = client.get(sat).get_data(as_text=True)
        assert f'href="{pilar}"' in html and "Parte do guia" in html


# ------------------------------------------------------------------ conteúdo verificado
def test_guia_itbi_traz_valores_e_teses(ctx):
    client, _ = ctx
    txt = corpo(client.get(TRIBUTACAO[0]).get_data(as_text=True))
    for esperado in ("4%", "2%", "0,5%", "R$ 390.672,24", "Tema 1.113", "Tema 1.124", "REsp 1.937.821/SP",
                     "3 parcelas", "ibs.sefin.fortaleza.ce.gov.br"):
        assert esperado in txt, esperado


def test_guia_itcd_traz_ufirce_isencao_prazos_e_multas(ctx):
    client, _ = ctx
    txt = corpo(client.get(TRIBUTACAO[1]).get_data(as_text=True))
    for esperado in ("R$ 6,29872", "Instrução Normativa SEFAZ-CE nº 152/2025", "R$ 251.949", "R$ 1.574.680",
                     "R$ 44.091", "2/3", "60 dias", "30 dias", "10%", "20%", "Lei estadual 15.812/2015"):
        assert esperado in txt, esperado


def test_guia_pf_ou_holding_nao_inventa_numero_da_holding(ctx):
    client, _ = ctx
    txt = corpo(client.get(TRIBUTACAO[2]).get_data(as_text=True))
    assert txt.count("[PREENCHER") >= 2, "carga da holding fica como lacuna marcada, sem número inventado"
    assert "Tema 796" in txt and "Tema 1.348" in txt and "Lei 9.249/1995" in txt


@pytest.mark.parametrize("path,termos", [
    (TECNICOS[0], ("ISO 9223", "C1", "CX", "ABNT NBR 12609", "316", "molibdênio")),
    (TECNICOS[1], ("ABNT NBR 15575-4", "ISO 10140-2", "ISO 16283-3", "EN ISO 717-1", "D2m,nT,w", "20 dB", "25 dB", "30 dB")),
    (TECNICOS[2], ("ABNT NBR 15000", "III-A", ".44 Magnum", "9 mm", "edição de 2005")),
    (TECNICOS[3], ("100% da carga", "kVA", "autonomia", "ABNT NBR 5410", "NBR 14039", "ART")),
])
def test_guias_tecnicos_citam_as_normas(ctx, path, termos):
    client, _ = ctx
    txt = corpo(client.get(path).get_data(as_text=True))
    for termo in termos:
        assert termo in txt, (path, termo)


def test_lacunas_dos_guias_tecnicos_estao_marcadas(ctx):
    client, _ = ctx
    for path in TECNICOS:
        assert "[PREENCHER" in client.get(path).get_data(as_text=True), path
