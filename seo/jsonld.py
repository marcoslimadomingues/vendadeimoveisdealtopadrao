"""Gerador de dados estruturados Schema.org (JSON-LD) com @graph único por página.

Cada página recebe, injetado estaticamente no <head> pelo servidor:
  - nós globais: Organization/RealEstateAgent, WebSite e a Entidade Central;
  - o nó da página (WebPage, RealEstateListing, CollectionPage, ProfilePage...);
  - BreadcrumbList e os nós específicos (Offer, SingleFamilyResidence/Apartment,
    Article, Person, VideoObject, Dataset, Question...).
Os nós se referenciam por @id, formando um grafo de entidades conectado.
"""
from __future__ import annotations

import json
import re

from .content import Repo

SCHEMA = "https://schema.org"
LANG = "pt-BR"
AMENIDADES_OBRIGATORIAS = ("Isolamento Acústico Europeu", "Portaria Blindada", "Gerador Total")


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
            "foundingDate": s["fundacao"],
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
            "employee": [self.ref(p["path"], "pessoa") for p in self.repo.pessoas.values()],
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

    def pessoa(self, p: dict, completa: bool = False) -> dict:
        node = {
            "@type": "Person",
            **self.ref(p["path"], "pessoa"),
            "name": p["nome"],
            "jobTitle": p["cargo"],
            "url": self.url(p["path"]),
            "image": self.url(p["foto"]),
            "worksFor": self.org,
            "sameAs": [p["linkedin"], p["youtube"]],
        }
        if completa:
            node.update({
                "description": p["resumo"],
                "knowsAbout": p["areas"],
                "knowsLanguage": "pt-BR",
                "hasOccupation": {"@type": "Occupation", "name": p["cargo"],
                                  "occupationLocation": self.cidade()},
                "hasCredential": {
                    "@type": "EducationalOccupationalCredential",
                    "credentialCategory": p["credencial"]["categoria"],
                    "name": p["credencial"]["nome"],
                    "recognizedBy": {"@type": "Organization", "name": p["credencial"]["orgao"]},
                },
            })
        return node

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
        apresentador = self.repo.pessoas[v["apresentador"]]
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
            "actor": self.ref(apresentador["path"], "pessoa"),
            "creator": self.org,
            "publisher": self.org,
        }

    def videos(self, path: str, lista: list[dict], ja_presentes: set[str]) -> tuple[list[dict], list[dict]]:
        """(nós VideoObject + Person dos apresentadores ausentes, refs para a página)."""
        nodes, refs = [], []
        for n, v in enumerate(lista, start=1):
            node = self.video(path, v, n)
            nodes.append(node)
            refs.append({"@id": node["@id"]})
            pessoa = self.repo.pessoas[v["apresentador"]]
            if pessoa["slug"] not in ja_presentes:
                nodes.append(self.pessoa(pessoa))
                ja_presentes.add(pessoa["slug"])
        return nodes, refs

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
                                              ("/imoveis/", "/guias/", "/especialistas/", "/contato/")])
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
        consultor = self.repo.pessoas[i["consultor"]]
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
                    ("Isolamento acústico das esquadrias (Rw)", i["tecnico"]["rw_db"], "dB"),
                    ("Nível de blindagem da portaria (ABNT NBR 15000)", i["tecnico"]["blindagem_nivel"], None),
                    ("Potência do gerador", i["tecnico"]["gerador_kva"], "kVA"),
                    ("Autonomia do gerador", i["tecnico"]["gerador_autonomia_h"], "h"),
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
            "offeredBy": self.ref(consultor["path"], "pessoa"),
        }

        extra = {
            "datePosted": i["data_publicacao"],
            "dateModified": i["data_encerramento"] if encerrado else i["data_atualizacao"],
            "image": imagem,
            "mainEntity": self.ref(path, "imovel"),
            "offers": self.ref(path, "oferta"),
            "accountablePerson": self.ref(consultor["path"], "pessoa"),
            "hasPart": [{"@id": q["@id"]} for q in self.perguntas(path, i["faq"])],
        }
        nodes = [residencia, oferta, self.lugar(b), self.pessoa(consultor), *self.perguntas(path, i["faq"])]
        if i["videos"]:
            video_nodes, extra["video"] = self.videos(path, i["videos"], {consultor["slug"]})
            nodes += video_nodes

        pagina = self.pagina("RealEstateListing", path, i["titulo"], resumo, crumbs, **extra)
        return self.render(pagina, self.trilha(path, crumbs), *nodes)

    def bairro(self, b: dict, crumbs, titulo: str) -> str:
        path = b["path"]
        imoveis = self.repo.ativos(b["slug"])
        lista = self.lista(path, "lista", f"Imóveis de alto padrão à venda {b['em']}",
                           [(i["titulo"], i["path"]) for i in imoveis])
        dataset = {
            "@type": "Dataset",
            **self.ref(path, "indicadores"),
            "name": f"Indicadores do mercado de alto padrão {b['em']} ({self.site['periodo_curto']})",
            "description": b["resumo"],
            "creator": self.org,
            "isAccessibleForFree": True,
            "temporalCoverage": self.site["periodo_dados"],
            "spatialCoverage": self.ref(path, "lugar"),
            "measurementTechnique": self.site["fonte_dados"],
            "variableMeasured": [
                {"@type": "PropertyValue", "name": "Preço médio por m²", "value": b["preco_m2"], "unitText": "BRL/m²"},
                {"@type": "PropertyValue", "name": "Valorização em 12 meses", "value": b["valorizacao_12m"], "unitText": "%"},
                {"@type": "PropertyValue", "name": "Tempo médio de venda", "value": b["tempo_medio_venda"], "unitText": "dias"},
                {"@type": "PropertyValue", "name": "Desconto médio de negociação", "value": b["desconto_negociacao"], "unitText": "%"},
            ],
        }
        pagina = self.pagina("CollectionPage", path, titulo, b["resumo"], crumbs,
                             about=[self.ref(path, "lugar"), self.entidade],
                             mainEntity={"@id": lista["@id"]})
        return self.render(pagina, self.trilha(path, crumbs), self.lugar(b), dataset, lista)

    def artigo(self, a: dict, crumbs) -> str:
        path = a["path"]
        autor = self.repo.pessoas[a["autor"]]
        perguntas = self.perguntas(path, a["perguntas_todas"])
        artigo = {
            "@type": "Article",
            **self.ref(path, "artigo"),
            "headline": a["titulo"][:110],
            "description": a["descricao"],
            "abstract": a["resumo"],
            "image": self.url(a["imagem"]),
            "datePublished": a["publicado"],
            "dateModified": a["atualizado"],
            "author": self.ref(autor["path"], "pessoa"),
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
        nodes = [artigo, self.pessoa(autor), *perguntas]
        nodes += [self.lugar(self.repo.bairros[s]) for s in a.get("bairros_relacionados", [])]
        extra = {"mainEntity": self.ref(path, "artigo"), "author": self.ref(autor["path"], "pessoa"),
                 "datePublished": a["publicado"], "dateModified": a["atualizado"]}
        if a["videos"]:
            video_nodes, artigo["video"] = self.videos(path, a["videos"], {autor["slug"]})
            nodes += video_nodes
        tipo = ["WebPage", "FAQPage"] if perguntas else "WebPage"
        if perguntas:
            extra["hasPart"] = [{"@id": q["@id"]} for q in perguntas]
        pagina = self.pagina(tipo, path, a["titulo"], a["descricao"], crumbs, **extra)
        return self.render(pagina, self.trilha(path, crumbs), *nodes)

    def perfil(self, p: dict, crumbs) -> str:
        path = p["path"]
        pessoa = self.pessoa(p, completa=True)
        videos = self.repo.videos_por_pessoa(p["slug"])
        if videos:
            # Vídeos vivem nas páginas onde estão incorporados; o perfil só os referencia.
            pessoa["subjectOf"] = [
                {"@type": "VideoObject", "@id": f"{self.url(pg['path'])}#video-{pg['videos'].index(v) + 1}",
                 "name": v["titulo"], "url": self.url(pg["path"])}
                for v, pg in videos
            ]
        pagina = self.pagina("ProfilePage", path, f"{p['nome']} — {p['cargo']}", p["resumo"], crumbs,
                             mainEntity=self.ref(path, "pessoa"))
        return self.render(pagina, self.trilha(path, crumbs), pessoa)

    def pilar(self, p: dict, crumbs, titulo: str) -> str:
        path, geo = p["path"], p["geo"]
        autor, revisor = self.repo.pessoas[p["autor"]], self.repo.pessoas[p["revisor"]]
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
            "author": self.ref(autor["path"], "pessoa"), "publisher": self.org,
            "mainEntityOfPage": self.ref(path, "webpage"), "inLanguage": LANG,
            "about": [self.ref(path, "lugar"), self.entidade],
            "citation": [{"@id": f["@id"]} for f in fontes.values()],
        }
        extra = {
            "mainEntity": self.ref(path, "artigo"), "datePublished": p["publicado"],
            "dateModified": p["atualizado"], "lastReviewed": p["atualizado"],
            "reviewedBy": self.ref(revisor["path"], "pessoa"), "author": self.ref(autor["path"], "pessoa"),
            "hasPart": [{"@id": q["@id"]} for q in perguntas],
            "mentions": [self.ref(b["path"], "lugar") for b in bairros]
                        + [{"@id": self.url(i["path"]) + "#webpage"} for i in p["imoveis"]],
        }
        pagina = self.pagina(["WebPage", "FAQPage"], path, titulo, p["descricao"], crumbs, **extra)
        nodes = [pagina, self.trilha(path, crumbs), artigo, lugar, dataset, lista, *fontes.values(),
                 *[self.lugar(b) for b in bairros], self.pessoa(autor), self.pessoa(revisor), *perguntas]
        return self.render(*nodes)

    def sobre(self, path: str, titulo: str, descricao: str, crumbs) -> str:
        pagina = self.pagina("AboutPage", path, titulo, descricao, crumbs, mainEntity=self.org)
        return self.render(pagina, self.trilha(path, crumbs))
