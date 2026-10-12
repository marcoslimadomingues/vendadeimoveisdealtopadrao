"""Layout para celular: tabelas em cartões, barra de contato, mapa em metades, viewport."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

CSS = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("logs") / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def tabelas(html: str) -> list[str]:
    return re.findall(r"<table\b[^>]*>.*?</table>", html, re.S)


def colunas(tabela: str) -> int:
    cab = re.search(r"<thead>(.*?)</thead>", tabela, re.S)
    return len(re.findall(r"<th\b", cab.group(1))) if cab else 0


def test_viewport_e_media_queries_de_celular(ctx):
    client, _ = ctx
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in client.get("/").get_data(as_text=True)
    assert "@media (max-width: 40rem)" in CSS and "@media (max-width: 48rem)" in CSS
    assert "table.empilhar" in CSS and ".barra-contato" in CSS


def test_tabelas_com_3_ou_mais_colunas_viram_cartoes(ctx):
    client, repo = ctx
    paginas = [p for p, _ in repo.paginas_indexaveis()]
    vistas = 0
    for path in paginas:
        for tb in tabelas(client.get(path).get_data(as_text=True)):
            n = colunas(tb)
            tem_classe = 'class="empilhar"' in tb.split(">", 1)[0]
            if n >= 3:
                vistas += 1
                assert tem_classe, (path, n)
                corpo = tb.split("</thead>", 1)[1]
                celulas = re.findall(r"<td\b[^>]*>", corpo)
                assert celulas and all("data-label=" in c for c in celulas), path
            else:
                assert not tem_classe, (path, n)
    assert vistas >= 10


def test_rotulos_vem_do_cabecalho_da_coluna(ctx):
    client, _ = ctx
    html = client.get("/milha-de-ouro-fortaleza/").get_data(as_text=True)
    marcos = [t for t in tabelas(html) if "Marcos de referência" in t][0]
    assert 'data-label="Posição na faixa"' in marcos and 'data-label="Distância da Beira Mar"' in marcos
    assert re.search(r'<th scope="row">1\. Praia do Meireles</th>', marcos), "título do cartão = th da linha"
    preco = [t for t in tabelas(html) if "fonte e data de referência" in t][0]
    assert 'class="longo" data-label="Observação"' in preco, "texto longo ocupa a linha inteira do cartão"


def test_barra_de_contato_fixa(ctx):
    client, repo = ctx
    home = client.get("/").get_data(as_text=True)
    assert 'class="barra-contato"' in home
    assert re.search(r'href="https://wa\.me/\d+\?text=[^"]+"', home)
    assert f'href="tel:{repo.site["telefone_link"]}"' in home
    ficha = client.get("/imoveis/cobertura-duplex-mucuripe-480m2/").get_data(as_text=True)
    barra = ficha.split('class="barra-contato"')[1].split("</nav>")[0]
    assert "AP-2031" in re.sub(r"%20", " ", barra), "mensagem do WhatsApp deve citar o código do imóvel"


def test_mapa_em_metades_no_celular(ctx):
    client, _ = ctx
    html = client.get("/milha-de-ouro-fortaleza/").get_data(as_text=True)
    imgs = re.findall(r'<img[^>]*mapa-milha-de-ouro\.svg[^>]*>', html)
    assert len(imgs) == 3  # inteira (desktop) + duas metades (celular)
    assert 'class="mapa__parte mapa__parte--oeste"' in html and 'class="mapa__parte mapa__parte--leste"' in html
    for alt in re.findall(r'<img[^>]*mapa-milha-de-ouro\.svg[^>]*alt="([^"]+)"', html):
        assert len(alt) > 30
    assert ".mapa .mapa__inteiro { display: none; }" in CSS


def test_nenhum_conteudo_depende_de_rolagem_lateral_do_documento(ctx):
    """Sem larguras fixas em px no HTML que estourem 390 px (imagens/iframes têm width responsivo via CSS)."""
    client, repo = ctx
    assert "max-width: 100%" in CSS
    for path in [p for p, _ in repo.paginas_indexaveis()]:
        html = client.get(path).get_data(as_text=True)
        assert not re.search(r'style="[^"]*width:\s*\d{3,}px', html), path
