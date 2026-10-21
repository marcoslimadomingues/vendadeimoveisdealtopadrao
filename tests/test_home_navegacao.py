"""Navegação até o imóvel: imóveis com foto logo abaixo do título, menu fixo e botões "Ver imóveis disponíveis"."""
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
def home(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("l") / "b.jsonl")
    c = app.test_client()
    return c.get("/").get_data(as_text=True), app.config["REPO"]


def secoes(html: str) -> list[str]:
    """Ids das seções (aria-labelledby) e das seções de FAQ, na ordem do documento."""
    corpo = html.split('<main id="conteudo"')[1].split("</main>")[0]
    return re.findall(r'<section[^>]*aria-labelledby="([^"]+)"', corpo)


def test_imoveis_com_foto_logo_abaixo_do_titulo_antes_de_qualquer_texto(home):
    """Decisão do dono (2026-10-21): quem abre o site vê os imóveis, com foto, antes das informações."""
    html, repo = home
    corpo = html.split('<main id="conteudo"')[1].split("</main>")[0]
    ordem = secoes(html)
    assert ordem[0] == "titulo-pagina", ordem
    primeiro_cartao = corpo.index('class="card card--imovel"')
    assert primeiro_cartao < corpo.index('<p class="lead"'), "nenhum parágrafo antes da vitrine"
    assert primeiro_cartao < corpo.index('id="sobre-carteira"') < corpo.index('id="indicadores"')
    capa = repo.ativos()[0]["galeria"][0]["src"]
    assert re.search(rf'<img src="{re.escape(capa)}"[^>]*fetchpriority="high"', corpo), "a 1ª foto carrega primeiro"


def test_conteudo_da_home_nao_foi_removido(home):
    html, repo = home
    ordem = secoes(html)
    for esperado in ("titulo-pagina", "sobre-carteira", "indicadores", "guias", "autoridade", "perguntas-frequentes"):
        assert esperado in ordem, esperado
    for pl in repo.pilares.values():
        assert f"pilar-{pl.slug}" in ordem if hasattr(pl, "slug") else f"pilar-{pl['slug']}" in ordem
    for i in repo.ativos():
        assert f'href="{i["path"]}"' in html


def test_botao_ver_imoveis_disponiveis_em_pontos_da_pagina(home):
    html, _ = home
    corpo = html.split('<main id="conteudo"')[1].split("</main>")[0]
    botoes = [m.start() for m in re.finditer(r'<a class="botao" href="/imoveis/"[^>]*>Ver imóveis disponíveis</a>', corpo)]
    assert len(botoes) >= 3, "um fechando a vitrine, um no texto da carteira e um mais abaixo"
    assert botoes[0] < corpo.index('id="sobre-carteira"'), "o primeiro fecha a vitrine"
    assert corpo.index('id="sobre-carteira"') < botoes[1] < corpo.index('id="indicadores"')
    assert botoes[-1] > corpo.index('id="guias"') and botoes[-1] < corpo.index('id="autoridade"'), "o último fica mais abaixo"


def test_menu_imoveis_e_o_primeiro_item(home):
    html, _ = home
    menu = html.split('class="menu"')[1].split("</ul>")[0]
    assert re.search(r'<li><a href="/imoveis/"[^>]*>Imóveis</a></li>', menu.split("</li>")[0] + "</li>")


def test_cabecalho_fixo_na_rolagem():
    assert re.search(r"\.topo \{[^}]*position: sticky; top: 0;", CSS)
    # no celular a linha da marca sai e o menu fica; âncoras não ficam sob o cabeçalho
    blocos = CSS.split("@media (max-width: 40rem)")[1:]
    assert any(re.search(r"\.topo \{ top: -[\d.]+rem; \}", b) for b in blocos)
    assert "scroll-padding-top" in CSS


def test_nenhuma_pagina_nova():
    tracked = (ROOT / "templates").glob("*.html")
    nomes = {p.name for p in tracked}
    assert nomes == {"404.html", "_macros.html", "artigo.html", "bairro.html", "base.html", "contato.html",
                     "guias.html", "home.html", "imovel.html", "imoveis.html", "pilar.html", "radar.html",
                     "radar_edicao.html", "redirect.html", "sobre.html"}
