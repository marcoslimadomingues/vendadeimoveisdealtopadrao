"""Títulos das páginas (fonte única) e atributo title em links e imagens.

- `titulos_paginas`: o <title> de cada URL indexável. As rotas do app usam este mesmo dicionário,
  então o title de um link interno é sempre o título real da página de destino.
- `aplicar_titulos`: pós-processa o HTML renderizado e adiciona title a todo <a> e <img> que
  ainda não tenha, inclusive nos links escritos dentro dos textos dos guias (data/artigos.json).
"""
from __future__ import annotations

import html as html_lib
import re

from .content import Repo

LINK = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<texto>.*?)</a>", re.S)
IMG = re.compile(r"<img\b(?P<attrs>[^>]*?)\s*/?>")
HREF = re.compile(r'\bhref="(?P<v>[^"]*)"')
ALT = re.compile(r'\balt="(?P<v>[^"]*)"')
ANCORAS = {"#conteudo": "Pular para o conteúdo principal"}


def titulos_paginas(repo: Repo) -> dict[str, str]:
    s, cid = repo.site, repo.site["cidade"]
    t = {
        "/": f"{s['entidade_central']['nome']} | {s['nome']}",
        "/imoveis/": f"Imóveis de altíssimo padrão à venda {cid['em']} ({len(repo.ativos())} ofertas)",
        "/guias/": f"Guias e análises do mercado de imóveis de alto padrão {cid['em']}",
        "/especialistas/": f"Especialistas da {s['nome']}: consultores, arquiteta e advogada",
        "/sobre/": f"Sobre a {s['nome']}: imóveis de altíssimo padrão {cid['em']} desde {s['fundacao']}",
        "/contato/": f"Contato e endereço da {s['nome']}: WhatsApp, e-mail e {s['endereco']['bairro']}, {cid['nome']}",
    }
    t.update({i["path"]: f"{i['titulo']} — {i['codigo']}" for i in repo.ativos()})
    t.update({b["path"]: f"Imóveis de alto padrão {b['em']}: preço por m², valorização e liquidez"
              for b in repo.bairros.values()})
    t.update({a["path"]: a["titulo"] for a in repo.artigos.values()})
    t.update({p["path"]: f"{p['nome']} — {p['cargo']}" for p in repo.pessoas.values()})
    t.update({p["path"]: f"{p['titulo_h1']}: m², ruas e mapa ({p['geo']['extensao_km']:.1f} km)".replace(".", ",")
              for p in repo.pilares.values()})
    return t


def _texto(fragmento: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", fragmento)).split())


def _titulo_link(href: str, texto: str, titulos: dict[str, str], site: dict) -> str:
    if href.startswith("#"):
        return ANCORAS.get(href, f"Ir para a seção: {texto}")
    if href.startswith("mailto:"):
        return f"Enviar e-mail para a {site['nome']}"  # sem o endereço: proxies reescrevem e-mails até em atributos
    if href.startswith("tel:"):
        return f"Ligar para a {site['nome']}: {site['telefone']}"
    if "wa.me/" in href:
        return f"Conversar com a {site['nome']} pelo WhatsApp"
    if "youtube.com/watch" in href:
        return f"{texto} (abre o vídeo no YouTube)"
    if "linkedin.com" in href:
        return texto
    if href.startswith("/"):
        caminho, _, ancora = href.partition("#")
        titulo = titulos.get(caminho, texto)
        return f"{titulo} — vídeos" if ancora == "videos" else titulo
    return texto


def aplicar_titulos(html: str, titulos: dict[str, str], site: dict) -> str:
    def link(m: re.Match) -> str:
        attrs = m["attrs"]
        href = HREF.search(attrs)
        if " title=" in attrs or not href:
            return m[0]
        titulo = _titulo_link(href["v"], _texto(m["texto"]), titulos, site)
        if not titulo:
            return m[0]
        return f'<a{attrs} title="{html_lib.escape(titulo, quote=True)}">{m["texto"]}</a>'

    def img(m: re.Match) -> str:
        attrs = m["attrs"]
        alt = ALT.search(attrs)
        if " title=" in attrs or not alt or not alt["v"]:
            return m[0]
        return f'<img{attrs} title="{alt["v"]}">'

    return IMG.sub(img, LINK.sub(link, html))


# ----------------------------------------------------------------- tabelas no celular
TABELA = re.compile(r"<table\b(?P<attrs>[^>]*)>(?P<corpo>.*?)</table>", re.S)
CABECALHO = re.compile(r"<thead>(?P<th>.*?)</thead>", re.S)
LINHA = re.compile(r"<tr\b[^>]*>.*?</tr>", re.S)
CELULA = re.compile(r"<(?P<tag>td|th)\b(?P<attrs>[^>]*)>(?P<txt>.*?)</(?P=tag)>", re.S)


def rotular_tabelas(html: str) -> str:
    """Tabelas com 3+ colunas viram cartões em tela pequena (CSS `table.empilhar`).

    Cada <td> recebe data-label com o texto do cabeçalho da sua coluna; a célula <th scope="row">
    vira o título do cartão. Em telas largas nada muda: continua uma tabela HTML nativa.
    """
    def tabela(m: re.Match) -> str:
        corpo = m["corpo"]
        cab = CABECALHO.search(corpo)
        if not cab:
            return m[0]
        rotulos = [_texto(x) for x in re.findall(r"<th\b[^>]*>(.*?)</th>", cab["th"], re.S)]
        if len(rotulos) < 3:
            return m[0]

        def linha(lm: re.Match) -> str:
            col = 0

            def celula(cm: re.Match) -> str:
                nonlocal col
                attrs = cm["attrs"]
                if "colspan" in attrs:  # linha de grupo (ficha técnica): não vira cartão
                    col += int(re.search(r'colspan="(\d+)"', attrs)[1])
                    return cm[0]
                rotulo = rotulos[col] if col < len(rotulos) else ""
                col += 1
                if cm["tag"] == "th" and 'scope="row"' in attrs:
                    return cm[0]  # título do cartão
                longo = ' class="longo"' if len(_texto(cm["txt"])) > 26 else ""
                return f'<{cm["tag"]}{attrs}{longo} data-label="{html_lib.escape(rotulo, quote=True)}">{cm["txt"]}</{cm["tag"]}>'

            return CELULA.sub(celula, lm[0])

        depois = corpo[cab.end():]
        novo = corpo[:cab.end()] + LINHA.sub(linha, depois)
        attrs = m["attrs"] if "class=" in m["attrs"] else f' class="empilhar"{m["attrs"]}'
        return f"<table{attrs}>{novo}</table>"

    return TABELA.sub(tabela, html)
