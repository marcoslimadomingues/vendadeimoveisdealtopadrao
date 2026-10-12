"""Servidor SSR em HTML5 puro — Alto Padrão Imóveis.

Todo o conteúdo crítico é renderizado no servidor (Jinja2) e entregue na
resposta inicial. O site não usa JavaScript no cliente.

Execução:  python app.py            (desenvolvimento, porta 8000)
Produção:  waitress-serve --port=8000 --call app:create_app
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, abort, render_template, request

from seo.bots import BotLogger, client_ip
from seo.content import Repo
from seo.formatting import register_filters
from seo.jsonld import Graph
from seo.titulos import aplicar_titulos, rotular_tabelas, titulos_paginas

ROOT = Path(__file__).resolve().parent
INDEXAVEL = "index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1"
NAO_INDEXAVEL = "noindex, nofollow"


def valor_robots() -> str:
    """Diretiva de indexação: SITE_NOINDEX=1 publica o site sem permitir indexação (conteúdo provisório)."""
    return NAO_INDEXAVEL if os.environ.get("SITE_NOINDEX") == "1" else INDEXAVEL
CSP = ("default-src 'self'; img-src 'self' https://i.ytimg.com data:; "
       "frame-src https://www.youtube-nocookie.com; style-src 'self'; script-src 'none'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")


def create_app(data_dir: str | Path | None = None, bot_log: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    repo = Repo(data_dir)
    base = os.environ.get("SITE_URL", repo.site["base_url"]).rstrip("/")
    diretiva_robots = valor_robots()
    # Site publicado em subpasta (ex.: https://dominio.com.br/altopadrao): links root-relative
    # do HTML recebem o prefixo. Rotas internas do Flask continuam sem prefixo.
    prefixo = urlparse(base).path.rstrip("/")
    graph = Graph(repo, base)
    s, cid = repo.site, repo.site["cidade"]
    titulos = titulos_paginas(repo)  # fonte única: <title> das páginas e title dos links
    bot_logger = BotLogger(bot_log or os.environ.get("BOT_LOG", ROOT / "logs" / "bot_access.jsonl"))
    register_filters(app)
    app.config.update(REPO=repo, BASE_URL=base, BOT_LOGGER=bot_logger)

    # Versão dos estáticos: muda quando CSS/mapa mudam, para o cache de 1 dia não segurar layout velho.
    h = hashlib.sha1()
    for arq in sorted((ROOT / "static").rglob("*")):
        if arq.is_file():
            h.update(arq.read_bytes())
    static_v = h.hexdigest()[:8]

    @app.context_processor
    def contexto_global():
        return {"site": repo.site, "repo": repo, "base": base, "ano": date.today().year, "static_v": static_v,
                "meta_robots": diretiva_robots}

    def pagina(template: str, *, path: str, titulo: str, descricao: str, jsonld: str | None,
               crumbs: list[tuple[str, str]] | None = None, status: int = 200, **ctx):
        html = render_template(template, titulo=titulo, descricao=descricao, path=path,
                               canonical=base + path, jsonld=jsonld, crumbs=crumbs,
                               status_404=(status == 404), **ctx)
        return html, status

    # ------------------------------------------------------------ Seção Core
    @app.get("/")
    def home():
        titulo = titulos["/"]
        descricao = (f"Casas, coberturas e apartamentos acima de {s['limiar_texto']} {cid['em']}, com preço por m², "
                     "liquidez por bairro e ficha técnica completa de acústica, maresia, blindagem e gerador.")
        return pagina("home.html", path="/", titulo=titulo, descricao=descricao,
                      jsonld=graph.home("/", titulo, descricao),
                      imoveis=repo.ativos(), artigos=repo.artigos_recentes(),
                      bairros=repo.bairros_por_liquidez(), pessoas=list(repo.pessoas.values()))

    @app.get("/imoveis/")
    def imoveis():
        path, crumbs = "/imoveis/", [("Início", "/"), ("Imóveis à venda", "/imoveis/")]
        lista = repo.ativos()
        titulo = titulos[path]
        descricao = (f"Catálogo de casas, coberturas e apartamentos acima de {s['limiar_texto']} {cid['em']}, "
                     "com preço, preço por m², condomínio, IPTU e especificação técnica.")
        return pagina("imoveis.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.colecao(path, titulo, descricao, crumbs,
                                           [(i["titulo"], i["path"]) for i in lista]),
                      imoveis=lista, bairros=repo.bairros_por_liquidez())

    @app.get("/imoveis/<slug>/")
    def imovel(slug: str):
        i = repo.imovel(slug)
        if i is None:
            abort(404)
        if i["status"] != "ativo":
            # Imóvel vendido/removido: HTTP 404 real (nunca soft 404), com alternativas úteis.
            return pagina("404.html", path=request.path, titulo="Imóvel vendido", descricao="",
                          jsonld=None, status=404, vendido=i,
                          alternativas=repo.ativos(i["bairro"]) or repo.ativos()[:3])
        b = repo.bairros[i["bairro"]]
        crumbs = [("Início", "/"), ("Imóveis à venda", "/imoveis/"), (b["nome"], b["path"]), (i["titulo"], i["path"])]
        return pagina("imovel.html", path=i["path"], titulo=titulos[i["path"]],
                      descricao=i["resumo"][:300], crumbs=crumbs, jsonld=graph.imovel(i, crumbs),
                      imovel=i, bairro=b, consultor=repo.pessoas[i["consultor"]],
                      artigos=repo.artigos_sobre_imovel(slug))

    @app.get("/bairros/<slug>/")
    def bairro(slug: str):
        b = repo.bairros.get(slug)
        if b is None:
            abort(404)
        crumbs = [("Início", "/"), ("Imóveis à venda", "/imoveis/"), (b["nome"], b["path"])]
        titulo = titulos[b["path"]]
        return pagina("bairro.html", path=b["path"], titulo=titulo, descricao=b["resumo"][:300],
                      crumbs=crumbs, jsonld=graph.bairro(b, crumbs, titulo), bairro=b,
                      imoveis=repo.ativos(slug), artigos=repo.artigos_sobre_bairro(slug))

    # --------------------------------------------------------- Seção Outdoor
    @app.get("/guias/")
    def guias():
        path, crumbs = "/guias/", [("Início", "/"), ("Guias e análises", "/guias/")]
        lista = repo.artigos_recentes()
        titulo = titulos[path]
        descricao = ("Análises de liquidez por bairro, tributação por holding familiar e critérios técnicos "
                     "de acústica, blindagem e gerador para compradores de imóveis de luxo.")
        return pagina("guias.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.colecao(path, titulo, descricao, crumbs,
                                           [(a["titulo"], a["path"]) for a in lista]),
                      artigos=lista)

    @app.get("/guias/<slug>/")
    def artigo(slug: str):
        a = repo.artigos.get(slug)
        if a is None:
            abort(404)
        crumbs = [("Início", "/"), ("Guias e análises", "/guias/"), (a["titulo"], a["path"])]
        return pagina("artigo.html", path=a["path"], titulo=titulos[a["path"]], descricao=a["descricao"],
                      crumbs=crumbs, jsonld=graph.artigo(a, crumbs), artigo=a,
                      autor=repo.pessoas[a["autor"]],
                      relacionados=[repo.imoveis[s] for s in a.get("imoveis_relacionados", [])])

    # ------------------------------------------------------ E-E-A-T / Pessoas
    @app.get("/especialistas/")
    def especialistas():
        path, crumbs = "/especialistas/", [("Início", "/"), ("Especialistas", "/especialistas/")]
        lista = list(repo.pessoas.values())
        titulo = titulos[path]
        descricao = "Consultores imobiliários, arquiteta e advogada tributarista responsáveis pelas ofertas e análises."
        return pagina("especialistas.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.colecao(path, titulo, descricao, crumbs,
                                           [(p["nome"], p["path"]) for p in lista]),
                      pessoas=lista)

    @app.get("/especialistas/<slug>/")
    def especialista(slug: str):
        p = repo.pessoas.get(slug)
        if p is None:
            abort(404)
        crumbs = [("Início", "/"), ("Especialistas", "/especialistas/"), (p["nome"], p["path"])]
        return pagina("especialista.html", path=p["path"], titulo=titulos[p["path"]],
                      descricao=p["resumo"], crumbs=crumbs, jsonld=graph.perfil(p, crumbs), pessoa=p,
                      imoveis=repo.imoveis_por_consultor(slug), artigos=repo.artigos_por_autor(slug))

    @app.get("/sobre/")
    def sobre():
        path, crumbs = "/sobre/", [("Início", "/"), ("Sobre", "/sobre/")]
        titulo = titulos[path]
        descricao = repo.site["contexto_fonte"][0] + " " + repo.site["contexto_fonte"][1]
        return pagina("sobre.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.sobre(path, titulo, descricao, crumbs), pessoas=list(repo.pessoas.values()))

    # ------------------------------------------------------- Pilar de mercado
    @app.get("/<slug>/")
    def pilar(slug: str):
        p = repo.pilares.get(slug)
        if p is None:
            abort(404)
        crumbs = [("Início", "/"), (p["nome"], p["path"])]
        return pagina("pilar.html", path=p["path"], titulo=titulos[p["path"]], descricao=p["descricao"],
                      crumbs=crumbs, jsonld=graph.pilar(p, crumbs, p["titulo_h1"]), pilar=p,
                      autor=repo.pessoas[p["autor"]], revisor=repo.pessoas[p["revisor"]],
                      bairros=[repo.bairros[s] for s in p["bairros"]],
                      guias=[repo.artigos[s] for s in p["guias"]])

    # ------------------------------------------------------ Arquivos técnicos
    @app.get("/robots.txt")
    def robots():
        return Response(render_template("robots.txt"), mimetype="text/plain")

    @app.get("/sitemap.xml")
    def sitemap():
        return Response(render_template("sitemap.xml", paginas=repo.paginas_indexaveis()),
                        mimetype="application/xml")

    # ------------------------------------------------------------- Erros HTTP
    @app.errorhandler(404)
    def nao_encontrado(_err):
        return pagina("404.html", path=request.path, titulo="Página não encontrada", descricao="",
                      jsonld=None, status=404, vendido=None, alternativas=repo.ativos()[:3])

    @app.errorhandler(500)
    def erro_interno(_err):
        return Response("Erro interno. Tente novamente em instantes.", status=500, mimetype="text/plain")

    # ----------------------------------------- Cabeçalhos HTTP + Bot Access Log
    @app.after_request
    def cabecalhos(resp: Response) -> Response:
        if resp.mimetype == "text/html" and not resp.direct_passthrough:
            # title em links/imagens (antes do prefixo: o mapa de títulos usa rotas sem subpasta)
            html = rotular_tabelas(aplicar_titulos(resp.get_data(as_text=True), titulos, s))
            if prefixo:
                html = re.sub(r'(href|src)="/(?!/)', rf'\g<1>="{prefixo}/', html)
            resp.set_data(html)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if resp.mimetype == "text/html":
            resp.headers["Content-Language"] = "pt-BR"
            resp.headers["Content-Security-Policy"] = CSP
        if resp.status_code == 200 and resp.mimetype == "text/html":
            # Declaração explícita de indexação. O servidor NUNCA emite noindex em página 200.
            resp.headers["X-Robots-Tag"] = diretiva_robots
        if resp.status_code >= 500:
            resp.headers["Cache-Control"] = "no-store"  # CDN não pode cachear erro de origem
        elif resp.status_code == 404:
            resp.headers["Cache-Control"] = "public, max-age=60, s-maxage=60"
        elif request.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "public, max-age=86400"
        else:
            # TTL curto na CDN: imóvel vendido vira 404 na borda em no máximo 10 minutos.
            resp.headers["Cache-Control"] = "public, max-age=300, s-maxage=600"

        bot_logger.log(method=request.method, path=request.path, status=resp.status_code,
                       user_agent=request.headers.get("User-Agent"),
                       ip=client_ip(request.headers, request.remote_addr),
                       size=resp.calculate_content_length())
        return resp

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), debug=False)
