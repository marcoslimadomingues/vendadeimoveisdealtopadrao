"""Todo link e toda imagem têm title; links internos usam o título real da página de destino."""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("logs") / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def paginas(repo):
    return [p for p, _ in repo.paginas_indexaveis()] + ["/imoveis/cobertura-meireles-410m2/", "/nao-existe/"]


def test_todo_link_e_imagem_tem_title(ctx):
    client, repo = ctx
    for path in paginas(repo):
        pagina = client.get(path).get_data(as_text=True)
        corpo = pagina.split("<body>", 1)[1]
        links = re.findall(r"<a\b[^>]*>", corpo)
        imagens = re.findall(r"<img\b[^>]*>", corpo)
        assert links and all(re.search(r'title="[^"]+"', a) for a in links), \
            (path, [a for a in links if "title=" not in a][:3])
        assert all(re.search(r'alt="[^"]+"', i) and re.search(r'title="[^"]+"', i) for i in imagens), path


def test_title_de_link_interno_e_o_titulo_da_pagina_destino(ctx):
    client, repo = ctx
    html_home = client.get("/").get_data(as_text=True)
    destinos = set(re.findall(r'<a\b[^>]*href="(/[^"#]*)"[^>]*title="([^"]+)"', html_home))
    assert destinos
    for href, title in destinos:
        alvo = client.get(href).get_data(as_text=True)
        titulo_real = html.unescape(re.search(r"<title>(.*?)</title>", alvo).group(1))
        assert html.unescape(title) == titulo_real, href


def test_links_especiais(ctx):
    client, _ = ctx
    pagina = client.get("/imoveis/cobertura-duplex-mucuripe-480m2/").get_data(as_text=True)
    assert 'href="#conteudo" title="Pular para o conteúdo principal"' in pagina
    assert re.search(r'href="mailto:[^"]+" title="Enviar e-mail para a Alto Padrão Imóveis', pagina)
    assert re.search(r'href="tel:[^"]+" title="Ligar para a Alto Padrão Imóveis', pagina)
    assert 'title="Conversar com a Alto Padrão Imóveis pelo WhatsApp"' in pagina
    assert 'alt="Logotipo da Alto Padrão Imóveis"' in pagina


def test_emails_protegidos_contra_ofuscacao_da_cdn(ctx):
    client, repo = ctx
    for path in ("/", "/imoveis/cobertura-duplex-mucuripe-480m2/"):
        pagina = client.get(path).get_data(as_text=True)
        for m in re.finditer(r"mailto:", pagina):
            antes = pagina[:m.start()].rfind("<!--email_off-->")
            depois = pagina[m.start():].find("<!--/email_off-->")
            assert antes != -1 and depois != -1, path
        assert not re.search(r"title=\"[^\"]*@", pagina), "e-mail não pode aparecer em atributo title"
