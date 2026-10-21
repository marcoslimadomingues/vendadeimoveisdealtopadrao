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

from flask import Flask, Response, abort, render_template, request, send_from_directory

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


# Em <meta http-equiv>, o navegador ignora frame-ancestors; o resto da política vale igual.
CSP_META = "; ".join(d for d in CSP.split("; ") if not d.startswith("frame-ancestors"))


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
                "meta_robots": diretiva_robots, "meta_csp": CSP_META}

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
        descricao = (f"Casas, coberturas e apartamentos acima de {s['limiar_texto']} {cid['em']}, com preço por m² "
                     "do Sinduscon-CE por bairro, ITBI calculado e ficha técnica de cada imóvel.")
        return pagina("home.html", path="/", titulo=titulo, descricao=descricao,
                      jsonld=graph.home("/", titulo, descricao),
                      imoveis=repo.ativos(), artigos=repo.artigos_recentes(),
                      bairros=repo.bairros_por_m2(), faq=repo.faq_institucional())

    @app.get("/imoveis/")
    def imoveis():
        path, crumbs = "/imoveis/", [("Início", "/"), ("Imóveis à venda", "/imoveis/")]
        lista = repo.ativos()
        titulo = titulos[path]
        descricao = (f"Catálogo de casas, coberturas e apartamentos acima de {s['limiar_texto']} {cid['em']}, "
                     "com preço, preço por m², condomínio, IPTU e dados técnicos documentados.")
        return pagina("imoveis.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.colecao(path, titulo, descricao, crumbs,
                                           [(i["titulo"], i["path"]) for i in lista]),
                      imoveis=lista, bairros=repo.bairros_por_m2(), encerrados=repo.encerrados())

    @app.get("/imoveis/<slug>/")
    def imovel(slug: str):
        i = repo.imovel(slug)
        if i is None:
            abort(404)
        if slug in repo.redirecionados():
            # GitHub Pages não faz 301: meta refresh imediato + canonical para o bairro (o Google trata
            # o refresh instantâneo como redirecionamento). Fica fora do sitemap e do llms.txt.
            b = repo.redirecionados()[slug]
            return render_template("redirect.html", destino=base + b["path"], destino_path=b["path"], bairro=b,
                                   titulo=f"Imóvel indisponível: imóveis de alto padrão {b['em']}",
                                   canonical=base + b["path"])
        if i["status"] != "ativo" and not i.get("encerrado"):
            # Vendido com ficha completa segue no ar (200, marcado como vendido). Vendido só com registro
            # mínimo ou removido: HTTP 404 real (nunca soft 404), com alternativas úteis.
            return pagina("404.html", path=request.path, titulo="Imóvel vendido", descricao="",
                          jsonld=None, status=404, vendido=i,
                          alternativas=repo.ativos(i["bairro"]) or repo.ativos()[:3])
        b = repo.bairros[i["bairro"]]
        crumbs = [("Início", "/"), ("Imóveis à venda", "/imoveis/"), (b["nome"], b["path"]), (i["titulo"], i["path"])]
        return pagina("imovel.html", path=i["path"], titulo=titulos[i["path"]],
                      descricao=(i.get("resumo_encerrado") or i["resumo"])[:300], crumbs=crumbs,
                      jsonld=graph.imovel(i, crumbs),
                      imovel=i, bairro=b, artigos=repo.artigos_sobre_imovel(slug))

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
        descricao = ("Preço do m² por bairro, ITBI, ITCD e holding familiar, e critérios técnicos de acústica, "
                     "maresia, blindagem e gerador para compradores de imóveis de luxo.")
        return pagina("guias.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.colecao(path, titulo, descricao, crumbs,
                                           [(a["titulo"], a["path"]) for a in lista]),
                      artigos=lista)

    @app.get("/guias/<slug>/")
    def artigo(slug: str):
        a = repo.artigos.get(slug)
        if a is None or a.get("url_sob_pilar"):  # satélite sob o pilar tem uma única URL
            abort(404)
        return render_artigo(a)

    @app.get("/<pilar_slug>/<slug>/")
    def satelite(pilar_slug: str, slug: str):
        a = repo.artigos.get(slug)
        if a is None or not a.get("url_sob_pilar") or a["pilar"] != pilar_slug:
            abort(404)
        return render_artigo(a)

    def render_artigo(a: dict):
        pl = repo.pilares.get(a.get("pilar", ""))
        if a.get("url_sob_pilar"):
            crumbs = [("Início", "/"), (pl["nome"], pl["path"]), (a["titulo"], a["path"])]
        else:
            crumbs = [("Início", "/"), ("Guias e análises", "/guias/"), (a["titulo"], a["path"])]
        return pagina("artigo.html", path=a["path"], titulo=titulos[a["path"]], descricao=a["descricao"],
                      crumbs=crumbs, jsonld=graph.artigo(a, crumbs), artigo=a, pilar=pl,
                      guia_pilar=repo.artigos.get(a.get("guia_pilar", "")),
                      satelites=repo.satelites_do_guia(a["slug"]),
                      relacionados=[repo.imoveis[s] for s in a.get("imoveis_relacionados", [])])

    # ------------------------------------------------------ Radar de lançamentos
    @app.get("/radar/")
    def radar():
        edicoes = repo.radar_edicoes()
        if not edicoes:
            abort(404)
        path, crumbs = "/radar/", [("Início", "/"), ("Radar de lançamentos", "/radar/")]
        titulo = titulos[path]
        descricao = (f"Edição semanal com lançamentos de alto padrão {cid['em']} e região, preço do m² do "
                     "Sinduscon-CE e movimentos do mercado, cada fato com fonte e data.")
        return pagina("radar.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.colecao(path, titulo, descricao, crumbs,
                                           [(titulos[e["path"]], e["path"]) for e in edicoes]),
                      edicoes=edicoes)

    @app.get("/radar/<slug>/")
    def radar_edicao(slug: str):
        e = repo.radar.get(slug)
        if e is None:
            abort(404)
        data_br = "/".join(reversed(e["publicado"].split("-")))
        crumbs = [("Início", "/"), ("Radar de lançamentos", "/radar/"), (f"Edição de {data_br}", e["path"])]
        edicoes = repo.radar_edicoes()
        n = edicoes.index(e)
        return pagina("radar_edicao.html", path=e["path"], titulo=titulos[e["path"]], descricao=e["resumo"],
                      crumbs=crumbs, jsonld=graph.radar(e, crumbs, titulos[e["path"]]), edicao=e,
                      anterior=edicoes[n + 1] if n + 1 < len(edicoes) else None,
                      seguinte=edicoes[n - 1] if n > 0 else None)

    @app.get("/sobre/")
    def sobre():
        path, crumbs = "/sobre/", [("Início", "/"), ("Sobre", "/sobre/")]
        titulo = titulos[path]
        descricao = repo.site["contexto_fonte"][0] + " " + repo.site["contexto_fonte"][1]
        return pagina("sobre.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.sobre(path, titulo, descricao, crumbs), bairros=repo.bairros_por_m2())

    @app.get("/contato/")
    def contato():
        path, crumbs = "/contato/", [("Início", "/"), ("Contato", "/contato/")]
        titulo, e = titulos[path], s["endereco"]
        descricao = (f"WhatsApp {s['telefone']}, e-mail e endereço da {s['nome']}: {e['rua']}, {e['bairro']}, "
                     f"{e['cidade']} ({e['uf']}). {s['horario_texto']}.")
        return pagina("contato.html", path=path, titulo=titulo, descricao=descricao, crumbs=crumbs,
                      jsonld=graph.contato(path, titulo, descricao, crumbs), imoveis=repo.ativos())

    # ------------------------------------------------------- Pilar de mercado
    @app.get("/<slug>/")
    def pilar(slug: str):
        p = repo.pilares.get(slug)
        if p is None:
            abort(404)
        crumbs = [("Início", "/"), (p["nome"], p["path"])]
        return pagina("pilar.html", path=p["path"], titulo=titulos[p["path"]], descricao=p["descricao"],
                      crumbs=crumbs, jsonld=graph.pilar(p, crumbs, p["titulo_h1"]), pilar=p,
                      bairros=[repo.bairros[s] for s in p["bairros"]],
                      guias=[repo.artigos[s] for s in p["guias"]])

    # ------------------------------------------------------ Arquivos técnicos
    @app.get("/robots.txt")
    def robots():
        return Response(render_template("robots.txt"), mimetype="text/plain")

    @app.get("/llms.txt")
    def llms():
        """Resumo em texto para agentes de IA (convenção llmstxt.org): quem somos, fatos e páginas-chave."""
        return Response(render_template("llms.txt", paginas=repo.paginas_indexaveis(), pilares=repo.pilares.values(),
                                        bairros=repo.bairros_por_m2(), imoveis=repo.ativos(),
                                        encerrados=repo.encerrados(),
                                        artigos=repo.artigos_recentes(), faq=repo.faq_institucional()),
                        mimetype="text/plain")

    # raiz/: arquivos de verificação de buscadores (ex.: BingSiteAuth.xml), servidos como estão
    for arq in sorted((ROOT / "raiz").glob("*")):
        app.add_url_rule(f"/{arq.name}", f"raiz_{arq.stem}",
                         lambda nome=arq.name: send_from_directory(ROOT / "raiz", nome))

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
