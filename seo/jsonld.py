"""Gerador de dados estruturados Schema.org (JSON-LD) com @graph único por página.

Cada página recebe, injetado estaticamente no <head> pelo servidor:
  - nós globais: Organization/RealEstateAgent, WebSite e a Entidade Central;
  - o nó da página (WebPage, RealEstateListing, CollectionPage, ProfilePage...);
  - BreadcrumbList e os nós específicos (Offer, SingleFamilyResidence/Apartment,
    Article, VideoObject, Dataset, Question...).
A autoria é sempre da organização (CNPJ e CRECI): o site não publica pessoas.
Os nós se referenciam por @id, formando um grafo de entidades conectado.
"""
from __future__ import annotations

import json
import re

from .content import Repo

SCHEMA = "https://schema.org"
LANG = "pt-BR"


DIAS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SIGLAS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


def horario_estruturado(horario: str) -> list[dict]:
    """'Mo-Fr 09:00-18:00' (formato de openingHours) -> OpeningHoursSpecification."""
    m = re.fullmatch(r"(Mo|Tu|We|Th|Fr|Sa|Su)(?:-(Mo|Tu|We|Th|Fr|Sa|Su))? (\d\d:\d\d)-(\d\d:\d\d)", horario)
    if not m:
        raise ValueError(f"horario fora do formato 'Mo-Fr 09:00-18:00': {horario!r}")
    ini, fim = SIGLAS.index(m[1]), SIGLAS.index(m[2] or m[1])
    return [{"@type": "OpeningHoursSpecification", "dayOfWeek": DIAS[ini:fim + 1],
             "opens": m[3], "closes": m[4]}]


class Graph:
    def __init__(self, repo: Repo, base: str):
        self.repo = repo
        self.site = repo.site
        self.base = base.rstrip("/")

    # ------------------------------------------------------------- utilidades
    def url(self, path: str) -> str:
        return self.base + path

    def ref(self, path: str, frag: str) -> dict:
        return {"@id": f"{self.base}{path}#{frag}"}

    @property
    def org(self) -> dict:
        return self.ref("/", "organizacao")

    @property
    def entidade(self) -> dict:
        return self.ref("/", "entidade-central")

    def render(self, *nodes: dict) -> str:
        grafo = [self._organizacao(), self._website(), self._entidade_central(), *nodes]
        texto = json.dumps({"@context": SCHEMA, "@graph": grafo}, ensure_ascii=False, indent=2)
        return texto.replace("</", "<\\/")  # impede fechamento prematuro do <script>

    def cidade(self) -> dict:
        c = self.site["cidade"]
        return {"@type": "City", "name": c["nome"], "sameAs": c["wikidata"],
                "containedInPlace": {"@type": "State", "name": c["estado"]}}

    # ---------------------------------------------------------- nós globais
    def _organizacao(self) -> dict:
        s, e = self.site, self.site["endereco"]
        return {
            "@type": "RealEstateAgent",
            **self.org,
            "name": s["nome"],
            "legalName": s["razao_social"],
            "description": s["descricao"],
            "url": self.url("/"),
            "logo": {"@type": "ImageObject", **self.ref("/", "logo"),
                     "url": self.url("/static/img/logo.svg"), "caption": s["nome"]},
            "image": self.ref("/", "logo"),
            **({"foundingDate": s["fundacao"]} if s.get("fundacao") else {}),
            "taxID": s["cnpj"],
            "vatID": s["cnpj"],
            "identifier": [
                {"@type": "PropertyValue", "propertyID": "CNPJ", "value": s["cnpj"]},
                {"@type": "PropertyValue", "propertyID": s["creci_orgao"], "value": s["creci"]},
            ],
            "telephone": s["telefone"],
            "email": s["email"],
            "contactPoint": [{
                "@type": "ContactPoint",
                "contactType": "customer service",
                "telephone": s["telefone"],
                "email": s["email"],
                "areaServed": "BR",
                "availableLanguage": ["pt-BR"],
            }],
            "address": {
                "@type": "PostalAddress",
                "streetAddress": e["rua"],
                "addressLocality": e["cidade"],
                "addressRegion": e["uf"],
                "postalCode": e["cep"],
                "addressCountry": e["pais"],
            },
            "geo": {"@type": "GeoCoordinates", "latitude": s["geo"]["lat"], "longitude": s["geo"]["lng"]},
            "hasMap": s["mapa_url"],
            "openingHours": s["horario"],
            "openingHoursSpecification": horario_estruturado(s["horario"]),
            "priceRange": s["faixa_preco"],
            "areaServed": self.cidade(),
            "knowsAbout": [s["entidade_central"]["nome"], *(b["nome"] for b in self.repo.bairros.values()),
                           "Holding familiar", "Isolamento acústico", "Blindagem arquitetônica"],
            "hasCredential": {
                "@type": "EducationalOccupationalCredential",
                "credentialCategory": "Registro profissional de imobiliária",
                "name": s["creci"],
                "recognizedBy": {"@type": "Organization", "name": s["creci_orgao"]},
            },
            **({"sameAs": s["sameAs"]} if s["sameAs"] else {}),
        }

    def _website(self) -> dict:
        return {
            "@type": "WebSite",
            **self.ref("/", "website"),
            "url": self.url("/"),
            "name": self.site["nome"],
            "description": self.site["descricao"],
            "inLanguage": LANG,
            "publisher": self.org,
            "about": self.entidade,
        }

    def _entidade_central(self) -> dict:
        ec = self.site["entidade_central"]
        return {"@type": "Service", **self.entidade, "name": ec["nome"], "description": ec["descricao"],
                "serviceType": "Intermediação de imóveis de alto padrão", "provider": self.org,
                "areaServed": self.cidade()}

    # ------------------------------------------------------ nós reutilizáveis
    def pagina(self, tipo, path: str, nome: str, descricao: str, crumbs=None, **extra) -> dict:
        node = {
            "@type": tipo,
            **self.ref(path, "webpage"),
            "url": self.url(path),
            "name": nome,
            "description": descricao,
            "inLanguage": LANG,
            "isPartOf": self.ref("/", "website"),
            "about": self.entidade,
            "publisher": self.org,
        }
        if crumbs:
            node["breadcrumb"] = self.ref(path, "breadcrumb")
        node.update(extra)
        return node

    def trilha(self, path: str, crumbs: list[tuple[str, str]]) -> dict:
        return {
            "@type": "BreadcrumbList",
            **self.ref(path, "breadcrumb"),
            "itemListElement": [
                {"@type": "ListItem", "position": n, "name": nome, "item": self.url(p)}
                for n, (nome, p) in enumerate(crumbs, start=1)
            ],
        }

    def lista(self, path: str, frag: str, nome: str, itens: list[tuple[str, str]]) -> dict:
        return {
            "@type": "ItemList",
            **self.ref(path, frag),
            "name": nome,
            "numberOfItems": len(itens),
            "itemListElement": [
                {"@type": "ListItem", "position": n, "url": self.url(p), "name": titulo}
                for n, (titulo, p) in enumerate(itens, start=1)
            ],
        }

    def lugar(self, b: dict) -> dict:
        return {
            "@type": "Place",
            **self.ref(b["path"], "lugar"),
            "name": f"{b['nome']}, {self.site['cidade']['nome']}",
            "description": b["perfil"],
            "containedInPlace": self.cidade(),
        }

    def video(self, path: str, v: dict, n: int = 1) -> dict:
        vid = v["youtube_id"]
        return {
            "@type": "VideoObject",
            **self.ref(path, f"video-{n}"),
            "name": v["titulo"],
            "description": v["descricao"],
            "genre": v.get("tipo"),
            "thumbnailUrl": [f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"],
            "uploadDate": v["data_upload"],
            "duration": v["duracao"],
            "embedUrl": f"https://www.youtube.com/embed/{vid}",
            "contentUrl": f"https://www.youtube.com/watch?v={vid}",
            "inLanguage": LANG,
            "creator": self.org,
            "publisher": self.org,
        }

    def videos(self, path: str, lista: list[dict]) -> tuple[list[dict], list[dict]]:
        """(nós VideoObject, refs para a página)."""
        nodes = [self.video(path, v, n) for n, v in enumerate(lista, start=1)]
        return nodes, [{"@id": node["@id"]} for node in nodes]

    def perguntas(self, path: str, faq: list[dict]) -> list[dict]:
        return [
            {
                "@type": "Question",
                **self.ref(path, f"pergunta-{n}"),
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for n, item in enumerate(faq, start=1)
        ]

    # --------------------------------------------------------------- páginas
    def home(self, path: str, titulo: str, descricao: str) -> str:
        imoveis = self.repo.ativos()
        lista = self.lista(path, "destaques", "Imóveis de altíssimo padrão em destaque",
                           [(i["titulo"], i["path"]) for i in imoveis])
        perguntas = self.perguntas(path, self.repo.faq_institucional())
        pagina = self.pagina(["WebPage", "FAQPage"], path, titulo, descricao,
                             mainEntity={"@id": lista["@id"]},
                             hasPart=[{"@id": q["@id"]} for q in perguntas],
                             significantLink=[self.url(p) for p in
                                              ("/imoveis/", "/guias/", "/sobre/", "/contato/")])
        return self.render(pagina, lista, *perguntas)

    def contato(self, path: str, titulo: str, descricao: str, crumbs) -> str:
        pagina = self.pagina("ContactPage", path, titulo, descricao, crumbs, mainEntity=self.org)
        return self.render(pagina, self.trilha(path, crumbs))

    def colecao(self, path: str, titulo: str, descricao: str, crumbs, itens) -> str:
        lista = self.lista(path, "lista", titulo, itens)
        pagina = self.pagina("CollectionPage", path, titulo, descricao, crumbs,
                             mainEntity={"@id": lista["@id"]})
        return self.render(pagina, self.trilha(path, crumbs), lista)

    def imovel(self, i: dict, crumbs) -> str:
        path, b = i["path"], self.repo.bairros[i["bairro"]]
        tec = i["tecnico"]
        imagem = self.url(i["imagem"])
        encerrado = bool(i.get("encerrado"))
        resumo = i["resumo_encerrado"] if encerrado else i["resumo"]

        residencia = {
            "@type": i["schema_type"],
            **self.ref(path, "imovel"),
            "name": i["titulo"],
            "description": resumo,
            "image": imagem,
            "floorSize": {"@type": "QuantitativeValue", "value": i["area_privativa"],
                          "unitCode": "MTK", "unitText": "m²"},
            "numberOfRooms": i["dormitorios"],
            "numberOfBedrooms": i["dormitorios"],
            "numberOfBathroomsTotal": i["banheiros"],
            "yearBuilt": i["ano_construcao"],
            "address": {
                "@type": "PostalAddress",
                "addressLocality": self.site["cidade"]["nome"],
                "addressRegion": self.site["cidade"]["uf"],
                "addressCountry": "BR",
                "description": f"{b['nome']}, {b['zona']} {self.site['cidade']['de']}",
            },
            "containedInPlace": self.ref(b["path"], "lugar"),
            "amenityFeature": [
                {"@type": "LocationFeatureSpecification", "name": a["nome"],
                 "value": True, "description": a["detalhe"]}
                for a in i["amenidades"]
            ],
            "additionalProperty": [
                {"@type": "PropertyValue", "name": nome, "value": valor, **({"unitText": unidade} if unidade else {})}
                for nome, valor, unidade in (
                    ("Código do imóvel", i["codigo"], None),
                    ("Suítes", i["suites"], None),
                    ("Vagas de garagem", i["vagas"], None),
                    ("Área do terreno", i.get("area_terreno"), "m²"),
                    ("Condomínio mensal", i.get("condominio_mensal"), "BRL"),
                    ("IPTU anual", i["iptu_anual"], "BRL"),
                    ("Situação", "Não está mais disponível" if encerrado else None, None),
                    ("Indisponível desde", i["data_encerramento"] if encerrado else None, None),
                    ("Dias no mercado", i.get("dias_no_mercado") if encerrado else None, "dias"),
                    ("Valor da venda", i.get("preco_venda_publico") if encerrado else None, "BRL"),
                    ("Preço por m²", None if encerrado else i["preco_m2"], "BRL/m²"),
                    ("Isolamento acústico das esquadrias (Rw)", tec.get("rw_db"), "dB"),
                    ("Nível de blindagem da portaria (ABNT NBR 15000)", tec.get("blindagem_nivel"), None),
                    ("Potência do gerador", tec.get("gerador_kva"), "kVA"),
                    ("Autonomia do gerador", tec.get("gerador_autonomia_h"), "h"),
                )
                if valor is not None
            ],
        }
        if i["schema_type"] == "Apartment" and i.get("andar"):
            residencia["floorLevel"] = i["andar"]

        oferta = {
            "@type": "Offer",
            **self.ref(path, "oferta"),
            "url": self.url(path),
            **({} if encerrado else {"price": i["preco"], "priceCurrency": "BRL"}),
            "availability": ("https://schema.org/SoldOut" if i["status"] == "vendido" else
                             "https://schema.org/OutOfStock") if encerrado else "https://schema.org/InStock",
            "businessFunction": "http://purl.org/goodrelations/v1#Sell",
            "validFrom": i["data_publicacao"],
            "itemOffered": self.ref(path, "imovel"),
            "seller": self.org,
            "offeredBy": self.org,
        }

        extra = {
            "datePosted": i["data_publicacao"],
            "dateModified": i["data_encerramento"] if encerrado else i["data_atualizacao"],
            "image": imagem,
            "mainEntity": self.ref(path, "imovel"),
            "offers": self.ref(path, "oferta"),
            "hasPart": [{"@id": q["@id"]} for q in self.perguntas(path, i["faq"])],
        }
        nodes = [residencia, oferta, self.lugar(b), *self.perguntas(path, i["faq"])]
        if i["videos"]:
            video_nodes, extra["video"] = self.videos(path, i["videos"])
            nodes += video_nodes

        pagina = self.pagina("RealEstateListing", path, i["titulo"], resumo, crumbs, **extra)
        return self.render(pagina, self.trilha(path, crumbs), *nodes)

    def bairro(self, b: dict, crumbs, titulo: str) -> str:
        path = b["path"]
        imoveis = self.repo.ativos(b["slug"])
        lista = self.lista(path, "lista", f"Imóveis de alto padrão à venda {b['em']}",
                           [(i["titulo"], i["path"]) for i in imoveis])
        s, sd = b["sinduscon"], self.repo.sinduscon  # m² do Sinduscon-CE, com fonte e mês
        variaveis = [{"@type": "PropertyValue", "name": f"Preço médio do m² ({sd['ref_txt']})",
                      "value": s["m2"], "unitText": "BRL/m²"}]
        if s["var_mes_pct"] is not None:
            variaveis.append({"@type": "PropertyValue", "name": f"Variação sobre {sd['ref_ant_txt']}",
                              "value": round(s["var_mes_pct"], 2), "unitText": "%"})
        variaveis += [{"@type": "PropertyValue", "name": rotulo, "value": s[chave], "unitText": unid}
                      for chave, rotulo, unid in (("estoque", "Unidades em oferta", "unidades"),
                                                  ("vendas", "Vendas no mês", "unidades"),
                                                  ("ivv_pct", "Índice de velocidade de vendas", "%"))
                      if chave in s]
        dataset = {
            "@type": "Dataset", **self.ref(path, "indicadores"),
            "name": f"Preço do m² {b['em']} em {sd['ref_txt']} (Sinduscon-CE)",
            "description": b["resumo"], "creator": self.org, "isAccessibleForFree": True,
            "temporalCoverage": sd["referencia"], "spatialCoverage": self.ref(path, "lugar"),
            "measurementTechnique": sd["metodo"], "variableMeasured": variaveis,
            "isBasedOn": {"@type": "NewsArticle", "headline": sd["fonte"]["titulo"], "url": sd["fonte"]["url"],
                          "datePublished": sd["fonte"]["publicado"],
                          "author": {"@type": "Person", "name": sd["fonte"]["autor"]},
                          "publisher": {"@type": "Organization", "name": sd["fonte"]["veiculo"]}},
        }
        pagina = self.pagina("CollectionPage", path, titulo, b["resumo"], crumbs,
                             about=[self.ref(path, "lugar"), self.entidade],
                             mainEntity={"@id": lista["@id"]})
        return self.render(pagina, self.trilha(path, crumbs), self.lugar(b), dataset, lista)

    def artigo(self, a: dict, crumbs) -> str:
        path = a["path"]
        perguntas = self.perguntas(path, a["perguntas_todas"])
        artigo = {
            "@type": "Article",
            **self.ref(path, "artigo"),
            "headline": a["titulo"][:110],
            "description": a["descricao"],
            "abstract": a["resumo"],
            "image": [{"@type": "ImageObject", "url": self.url(img), "caption": a.get("imagem_legenda") or a["titulo"],
                       **({"creditText": "Ilustração gerada por inteligência artificial"} if a.get("imagem_ia") else {})}
                      for img in a["imagens"]],
            "datePublished": a["publicado"],
            "dateModified": a["atualizado"],
            "author": self.org,
            "publisher": self.org,
            "mainEntityOfPage": self.ref(path, "webpage"),
            "isPartOf": self.ref(path, "webpage"),
            "articleSection": a["categoria"],
            "inLanguage": LANG,
            "timeRequired": f"PT{a['tempo_leitura']}M",
            "about": [self.entidade, *(self.ref(self.repo.bairros[s]["path"], "lugar")
                                       for s in a.get("bairros_relacionados", []))],
            "mentions": [
                {"@type": "RealEstateListing", "@id": self.url(self.repo.imoveis[s]["path"]) + "#webpage",
                 "name": self.repo.imoveis[s]["titulo"], "url": self.url(self.repo.imoveis[s]["path"])}
                for s in a.get("imoveis_relacionados", [])
            ],
        }
        nodes = [artigo, *perguntas]
        nodes += [self.lugar(self.repo.bairros[s]) for s in a.get("bairros_relacionados", [])]
        extra = {"mainEntity": self.ref(path, "artigo"), "author": self.org,
                 "datePublished": a["publicado"], "dateModified": a["atualizado"]}
        if a["videos"]:
            video_nodes, artigo["video"] = self.videos(path, a["videos"])
            nodes += video_nodes
        tipo = ["WebPage", "FAQPage"] if perguntas else "WebPage"
        if perguntas:
            extra["hasPart"] = [{"@id": q["@id"]} for q in perguntas]
        pagina = self.pagina(tipo, path, a["titulo"], a["descricao"], crumbs, **extra)
        return self.render(pagina, self.trilha(path, crumbs), *nodes)

    def pilar(self, p: dict, crumbs, titulo: str) -> str:
        path, geo = p["path"], p["geo"]
        bairros = [self.repo.bairros[s] for s in p["bairros"]]
        perguntas = self.perguntas(path, p["faq"])
        c = geo["centro_aprox"]

        fontes = {
            k: {"@type": "NewsArticle", **self.ref(path, f"fonte-{k}"), "headline": f["titulo"], "url": f["url"],
                "datePublished": f["publicado"], "author": {"@type": "Person", "name": f["autor"]},
                "publisher": {"@type": "Organization", "name": f["veiculo"]}, "inLanguage": LANG}
            for k, f in p["fontes"].items()
        }
        lugar = {
            "@type": "Place", **self.ref(path, "lugar"), "name": p["nome"],
            "description": f"{p['subtitulo']}, {geo['extensao_km']} km de orla, em {self.site['cidade']['nome']}.",
            "containedInPlace": self.cidade(),
            "containsPlace": [self.ref(b["path"], "lugar") for b in bairros],
            "geo": {"@type": "GeoCoordinates", "latitude": c["lat"], "longitude": c["lon"]},
            "hasMap": f"https://www.openstreetmap.org/#map=15/{c['lat']}/{c['lon']}",
        }
        medidas = []
        for i in p["indicadores"]:
            medidas.append({
                "@type": "PropertyValue", "name": f"Preço médio do m² — {i['rotulo']}", "value": i["valor"],
                "unitText": "BRL/m²", "description": i["nota"] or None,
                "measurementTechnique": f"{i['origem']}, reportado por {i['fonte_info']['veiculo']}",
                "temporalCoverage": i["referencia"] if i["referencia"][:1].isdigit() else None,
                "isBasedOn": {"@id": fontes[i["fonte"]]["@id"]},
            })
        medidas = [{k: v for k, v in m.items() if v is not None} for m in medidas]
        dataset = {
            "@type": "Dataset", **self.ref(path, "dataset"),
            "name": f"Preço do m² na {p['nome']} e nos bairros vizinhos, por fonte e data",
            "description": p["metodo_sinduscon"], "creator": self.org, "isAccessibleForFree": True,
            "temporalCoverage": "2026-07/2026-08", "spatialCoverage": self.ref(path, "lugar"),
            "isBasedOn": [{"@id": f["@id"]} for f in fontes.values()], "variableMeasured": medidas,
        }
        lista = self.lista(path, "imoveis", f"Imóveis à venda na {p['nome']}",
                           [(i["titulo"], i["path"]) for i in p["imoveis"]])
        artigo = {
            "@type": "Article", **self.ref(path, "artigo"), "headline": titulo[:110], "description": p["descricao"],
            "abstract": p["resumo"], "image": self.url("/static/img/mapa-milha-de-ouro.svg"),
            "datePublished": p["publicado"], "dateModified": p["atualizado"],
            "author": self.org, "publisher": self.org,
            "mainEntityOfPage": self.ref(path, "webpage"), "inLanguage": LANG,
            "about": [self.ref(path, "lugar"), self.entidade],
            "citation": [{"@id": f["@id"]} for f in fontes.values()],
        }
        extra = {
            "mainEntity": self.ref(path, "artigo"), "datePublished": p["publicado"],
            "dateModified": p["atualizado"], "lastReviewed": p["atualizado"], "author": self.org,
            "hasPart": [{"@id": q["@id"]} for q in perguntas],
            "mentions": [self.ref(b["path"], "lugar") for b in bairros]
                        + [{"@id": self.url(i["path"]) + "#webpage"} for i in p["imoveis"]],
        }
        pagina = self.pagina(["WebPage", "FAQPage"], path, titulo, p["descricao"], crumbs, **extra)
        nodes = [pagina, self.trilha(path, crumbs), artigo, lugar, dataset, lista, *fontes.values(),
                 *[self.lugar(b) for b in bairros], *perguntas]
        return self.render(*nodes)

    def sobre(self, path: str, titulo: str, descricao: str, crumbs) -> str:
        pagina = self.pagina("AboutPage", path, titulo, descricao, crumbs, mainEntity=self.org)
        return self.render(pagina, self.trilha(path, crumbs))
