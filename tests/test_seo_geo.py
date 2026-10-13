"""Dados reais da empresa, contato, redes sociais, llms.txt e FAQ da home (SEO, GEO, AEO, SXO)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from seo.jsonld import horario_estruturado  # noqa: E402

EMAIL = "contato@vendadeimoveisdealtopadrao.com.br"
WHATSAPP = "5585988631025"
CNPJ = "42.451.913/0001-74"
CRECI = "CRECI-CE J-4858"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("SITE_NOINDEX", raising=False)
    monkeypatch.delenv("SITE_URL", raising=False)
    return create_app(bot_log=tmp_path / "b.jsonl").test_client()


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def organizacao(html: str) -> dict:
    return next(n for n in grafo(html) if n["@id"].endswith("#organizacao"))


def test_dados_da_empresa_no_json_ld(client):
    org = organizacao(client.get("/").get_data(as_text=True))
    assert org["taxID"] == CNPJ and org["telephone"] == "+55 85 98863-1025" and org["email"] == EMAIL
    assert org["address"]["streetAddress"] == "Avenida Beira Mar, 1497"
    assert org["address"]["addressLocality"] == "Fortaleza" and org["address"]["addressRegion"] == "CE"
    assert org["hasCredential"]["name"] == CRECI
    assert {i["value"] for i in org["identifier"]} == {CNPJ, CRECI}
    assert org["contactPoint"][0]["email"] == EMAIL
    assert org["openingHoursSpecification"][0]["dayOfWeek"][0] == "Monday"
    assert org["openingHoursSpecification"][0]["dayOfWeek"][-1] == "Friday"
    assert "sameAs" not in org, "sem perfil real, não publicar sameAs de exemplo"


def test_nenhum_dado_provisorio_da_empresa_em_nenhuma_pagina(client):
    for path in ("/", "/sobre/", "/contato/", "/imoveis/", "/milha-de-ouro-fortaleza/"):
        html = client.get(path).get_data(as_text=True)
        for ruim in ("00.000.000/0001-00", "J-0000", "0000-0000", "altopadrao.example", "Beira Mar, 0000"):
            assert ruim not in html, (path, ruim)


def test_whatsapp_e_email_nos_links(client):
    html = client.get("/").get_data(as_text=True)
    assert f"https://wa.me/{WHATSAPP}?text=" in html
    assert 'href="tel:+5585988631025"' in html
    assert f'href="mailto:{EMAIL}"' in html
    assert CNPJ in html and CRECI in html and "Avenida Beira Mar, 1497" in html


def test_pagina_contato(client):
    r = client.get("/contato/")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "<h1>Contato e endereço da Alto Padrão Imóveis em Fortaleza</h1>" in html
    assert '<link rel="canonical" href="https://vendadeimoveisdealtopadrao.com.br/contato/">' in html
    assert any(n["@type"] == "ContactPage" for n in grafo(html))
    assert "https://vendadeimoveisdealtopadrao.com.br/contato/" in client.get("/sitemap.xml").get_data(as_text=True)
    assert 'href="/contato/"' in client.get("/").get_data(as_text=True)


def test_og_image_em_png_e_etiquetas_sociais(client):
    for path in ("/", "/imoveis/cobertura-duplex-mucuripe-480m2/", "/milha-de-ouro-fortaleza/", "/sobre/"):
        html = client.get(path).get_data(as_text=True)
        assert re.search(r'<meta property="og:image" content="[^"]+\.(png|jpg|webp)">', html), path
        assert '<meta name="twitter:image" content="' in html and '<meta name="twitter:title"' in html
        assert 'hreflang="pt-BR"' in html and 'hreflang="x-default"' in html
    assert (ROOT / "static" / "img" / "og-marca.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_404_sem_hreflang_nem_canonical(client):
    html = client.get("/nao-existe/").get_data(as_text=True)
    assert "hreflang" not in html and "canonical" not in html


def test_home_com_faq_visivel_e_no_json_ld(client):
    html = client.get("/").get_data(as_text=True)
    nos = grafo(html)
    perguntas = [n for n in nos if n["@type"] == "Question"]
    pagina = next(n for n in nos if n["@id"].endswith("/#webpage"))
    assert "FAQPage" in pagina["@type"] and len(perguntas) >= 6
    assert len(pagina["hasPart"]) == len(perguntas)
    for q in perguntas:  # todo texto do JSON-LD também está visível na página
        assert q["name"] in html and q["acceptedAnswer"]["text"][:60] in html
    texto = " ".join(q["acceptedAnswer"]["text"] for q in perguntas)
    assert "Avenida Beira Mar, 1497" in texto and "4%" in texto and "2%" in texto and CNPJ in texto


def test_llms_txt(client):
    r = client.get("/llms.txt")
    txt = r.get_data(as_text=True)
    assert r.status_code == 200 and r.mimetype == "text/plain"
    assert txt.startswith("# Alto Padrão Imóveis")
    for esperado in (CNPJ, CRECI, EMAIL, "Avenida Beira Mar, 1497",
                     "https://vendadeimoveisdealtopadrao.com.br/milha-de-ouro-fortaleza/",
                     "https://vendadeimoveisdealtopadrao.com.br/contato/"):
        assert esperado in txt, esperado
    # cada link aponta para uma página que existe
    for path in re.findall(r"\]\(https://vendadeimoveisdealtopadrao\.com\.br(/[^)]*)\)", txt):
        assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("entrada,dias", [
    ("Mo-Fr 09:00-18:00", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]),
    ("Sa 08:00-12:00", ["Saturday"]),
])
def test_horario_estruturado(entrada, dias):
    spec = horario_estruturado(entrada)[0]
    assert spec["dayOfWeek"] == dias and spec["opens"] < spec["closes"]


def test_horario_invalido_falha_alto():
    with pytest.raises(ValueError):
        horario_estruturado("segunda a sexta")
