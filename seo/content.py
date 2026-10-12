"""Repositório de conteúdo: carrega /data, valida referências e calcula métricas derivadas.

Todos os números exibidos (preço/m², custo mensal, comparação com o bairro) são
calculados aqui, uma única vez, para que HTML, JSON-LD e FAQ nunca divirjam.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import pilares as _pilares
from .formatting import brl, cap as _cap, data_extenso, num, pct

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _index(items: list[dict]) -> dict[str, dict]:
    return {item["slug"]: item for item in items}


# Imóvel que saiu da carteira. Sem exclusividade, a página nunca diz que a venda foi nossa:
# só "não está mais disponível". `vendido` -> Offer SoldOut; `indisponivel` -> Offer OutOfStock.
ENCERRADOS = ("vendido", "indisponivel")
CAMPO_DATA = {"vendido": "data_venda", "indisponivel": "data_saida"}

# Tokens nos textos dos guias de um pilar: o número vem sempre dos indicadores do pilar (fonte e data).
#   {m2:ID} {m2ant:ID} {ref:ID} {acima:A:B} {acimaant:A:B} {dif:A:B} {total:ID:AREA} {veiculo:FONTE} {dataf:FONTE}
#   (`ant` = valor_anterior do indicador, de julho: mesma fonte e mês de outro recorte)
TOKEN = re.compile(r"\{(m2|m2ant|ref|acima|acimaant|dif|total|veiculo|dataf):([a-z0-9_]+)(?::([a-z0-9_]+))?\}")


def _token(m: re.Match, pilar: dict) -> str:
    kind, a, b = m.groups()
    ind = {i["id"]: i for i in pilar["indicadores"]}
    if kind in ("veiculo", "dataf"):
        f = pilar["fontes"][a]
        return f["veiculo"] if kind == "veiculo" else data_extenso(f["publicado"])
    if a not in ind or (kind in ("acima", "acimaant", "dif") and b not in ind):
        raise ValueError(f"token {m[0]} aponta para indicador inexistente no pilar {pilar['slug']}")
    va = ind[a]["valor"]
    if kind == "m2":
        return brl(va)
    if kind == "m2ant":
        return brl(ind[a]["valor_anterior"])
    if kind == "acimaant":  # A (mês de referência) sobre o valor anterior de B
        return pct((va / ind[b]["valor_anterior"] - 1) * 100)
    if kind == "ref":
        return _pilares.mes_ano(ind[a]["referencia"])
    if kind == "acima":
        return pct((va / ind[b]["valor"] - 1) * 100)
    if kind == "dif":
        return brl(abs(va - ind[b]["valor"]))
    return brl(va * int(b))  # total: m² × área (b é a área em m², número)


def _expandir_tokens(no, pilar: dict):
    """Expande os tokens em todas as strings de um guia, no lugar."""
    if isinstance(no, dict):
        for k, v in no.items():
            no[k] = _expandir_tokens(v, pilar)
    elif isinstance(no, list):
        for n, v in enumerate(no):
            no[n] = _expandir_tokens(v, pilar)
    elif isinstance(no, str) and "{" in no:
        return TOKEN.sub(lambda m: _token(m, pilar), no)
    return no


class Repo:
    def __init__(self, data_dir: str | Path | None = None):
        d = Path(data_dir) if data_dir else DATA_DIR
        self.site: dict = _load(d / "site.json")
        self.bairros = _index(_load(d / "bairros.json"))
        self.pessoas = _index(_load(d / "especialistas.json"))
        self.imoveis = _index(_load(d / "imoveis.json"))
        self.artigos = _index(_load(d / "artigos.json"))
        self.pilares = _index(_load(d / "pilares.json")) if (d / "pilares.json").exists() else {}
        self._data_dir = d
        self._validar()
        self._enriquecer()

    # ------------------------------------------------------------------ carga
    def _validar(self) -> None:
        erros = []
        for i in self.imoveis.values():
            if i["bairro"] not in self.bairros:
                erros.append(f"imóvel {i['slug']}: bairro '{i['bairro']}' inexistente")
            if self._tem_ficha(i) and i["consultor"] not in self.pessoas:
                erros.append(f"imóvel {i['slug']}: consultor '{i['consultor']}' inexistente")
            if i["status"] not in ("ativo", *ENCERRADOS):
                erros.append(f"imóvel {i['slug']}: status '{i['status']}' inválido (ativo, vendido ou indisponivel)")
            if i.get("redirecionar_para_bairro") and i["status"] not in ENCERRADOS:
                erros.append(f"imóvel {i['slug']}: redirecionar_para_bairro só vale para vendido ou indisponivel")
            if self._tem_ficha(i) and i["status"] in ENCERRADOS:
                campo = CAMPO_DATA[i["status"]]
                if not i.get(campo):
                    erros.append(f"imóvel {i['slug']}: {i['status']} com ficha completa exige {campo}")
                if i.get("preco_venda_autorizado") and not i.get("preco_venda"):
                    erros.append(f"imóvel {i['slug']}: preco_venda_autorizado sem preco_venda")
                if i["status"] == "indisponivel" and i.get("preco_venda"):
                    erros.append(f"imóvel {i['slug']}: preco_venda não se aplica a imóvel indisponivel")
        for a in self.artigos.values():
            if a["autor"] not in self.pessoas:
                erros.append(f"artigo {a['slug']}: autor '{a['autor']}' inexistente")
            for s in a.get("imoveis_relacionados", []):
                if s not in self.imoveis or not self._tem_ficha(self.imoveis[s]):
                    erros.append(f"artigo {a['slug']}: imóvel relacionado '{s}' inexistente ou sem ficha no ar "
                                 "(sem publicacao_autorizada: true, ou retirado)")
            for s in a.get("bairros_relacionados", []):
                if s not in self.bairros:
                    erros.append(f"artigo {a['slug']}: bairro '{s}' inexistente")
            if a.get("pilar") and a["pilar"] not in self.pilares:
                erros.append(f"artigo {a['slug']}: pilar '{a['pilar']}' inexistente")
            if a.get("url_sob_pilar") and not a.get("pilar"):
                erros.append(f"artigo {a['slug']}: url_sob_pilar exige o campo pilar")
        for p in self.pilares.values():
            for b in p["bairros"]:
                if b not in self.bairros:
                    erros.append(f"pilar {p['slug']}: bairro '{b}' inexistente")
            for chave in ("autor", "revisor"):
                if p[chave] not in self.pessoas:
                    erros.append(f"pilar {p['slug']}: {chave} '{p[chave]}' inexistente")
            for g in p["guias"]:
                if g not in self.artigos:
                    erros.append(f"pilar {p['slug']}: guia '{g}' inexistente")
            for ind in p["indicadores"]:
                if ind["fonte"] not in p["fontes"]:
                    erros.append(f"pilar {p['slug']}: indicador '{ind['id']}' sem fonte cadastrada")
                if not ind.get("referencia"):
                    erros.append(f"pilar {p['slug']}: indicador '{ind['id']}' sem data de referência")
        for item in [*self.artigos.values(), *(i for i in self.imoveis.values() if self._tem_ficha(i))]:
            for v in item.get("videos", []):
                if v.get("apresentador") and v["apresentador"] not in self.pessoas:
                    erros.append(f"{item['slug']}: apresentador de vídeo '{v['apresentador']}' inexistente")
                if len(v["youtube_id"]) != 11:
                    erros.append(f"{item['slug']}: youtube_id '{v['youtube_id']}' deve ter 11 caracteres")
        if erros:
            raise ValueError("Dados inconsistentes:\n- " + "\n- ".join(erros))

    def _enriquecer(self) -> None:
        for b in self.bairros.values():
            b["path"] = f"/bairros/{b['slug']}/"
        for p in self.pessoas.values():
            p["path"] = f"/especialistas/{p['slug']}/"
        for a in self.artigos.values():
            a["path"] = (f"/{a['pilar']}/{a['slug']}/" if a.get("url_sob_pilar") else f"/guias/{a['slug']}/")
            if a.get("pilar"):
                _expandir_tokens(a, self.pilares[a["pilar"]])
                if "imoveis_relacionados" not in a:  # imóveis no ar, nos bairros do pilar
                    a["imoveis_relacionados"] = [
                        i["slug"] for i in self.ativos() if i["bairro"] in self.pilares[a["pilar"]]["bairros"]]
            a.setdefault("videos", [])
            for v in a["videos"]:
                v.setdefault("apresentador", a["autor"])
            # Respostas rápidas das seções + FAQ final: todas viram Question no JSON-LD.
            a["perguntas_todas"] = [qa for s in a["secoes"] for qa in s.get("respostas_rapidas", [])]
            a["perguntas_todas"] += a.get("faq", [])
        for i in self.imoveis.values():
            i["path"] = f"/imoveis/{i['slug']}/"
            if self._tem_ficha(i):
                self._enriquecer_imovel(i)
                if i["status"] in ENCERRADOS:
                    self._enriquecer_encerrado(i)
        for p in self.pilares.values():
            _pilares.enriquecer(self, p, self._data_dir)

    def _enriquecer_imovel(self, i: dict) -> None:
        b = self.bairros[i["bairro"]]
        i.setdefault("videos", [])
        for v in i["videos"]:
            v.setdefault("apresentador", i["consultor"])
        tec = i["tecnico"]
        responsavel = self.pessoas[self.site["responsavel_tecnico"]]
        i["preco_m2"] = round(i["preco"] / i["area_privativa"])
        i["dif_bairro_pct"] = round((i["preco_m2"] / b["preco_m2"] - 1) * 100, 1)
        i["iptu_mensal"] = round(i["iptu_anual"] / 12)
        custos = [
            ("Condomínio", i.get("condominio_mensal")),
            ("IPTU mensalizado", i["iptu_mensal"]),
            ("Associação de moradores", i.get("taxa_associacao_mensal")),
        ]
        i["custos"] = [(rotulo, valor) for rotulo, valor in custos if valor]
        i["custo_mensal"] = sum(valor for _, valor in i["custos"])

        ref = i["referencia"]
        posicao = "acima" if i["dif_bairro_pct"] >= 0 else "abaixo"
        itens = [f"{rotulo[0].lower() + rotulo[1:] if rotulo[1].islower() else rotulo} de {brl(valor)}"
                 for rotulo, valor in i["custos"]]
        partes = itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]
        sem_condominio = " O imóvel não paga condomínio." if not i.get("condominio_mensal") else ""
        s, cid, itbi_cfg = self.site, self.site["cidade"], self.site["itbi"]
        itbi = round(i["preco"] * itbi_cfg["aliquota"])
        itbi_antecipado = round(i["preco"] * itbi_cfg["aliquota_antecipada"])
        i["faq"] = [
            {
                "grupo": "Preço e custos",
                "q": f"Qual o preço por metro quadrado d{ref}?",
                "a": (f"{_cap(ref)} custa {brl(i['preco_m2'])} por m² de área privativa "
                      f"({num(i['area_privativa'])} m² por {brl(i['preco'])}). O valor está "
                      f"{pct(abs(i['dif_bairro_pct']))} {posicao} da média de {brl(b['preco_m2'])} "
                      f"por m² {b['de']}."),
            },
            {
                "grupo": "Preço e custos",
                "q": f"Quanto custa manter {ref} por mês?",
                "a": (f"O custo fixo mensal d{ref} é de {brl(i['custo_mensal'])}: {partes}. "
                      f"O IPTU anual é de {brl(i['iptu_anual'])}.{sem_condominio}"),
            },
            {
                "grupo": "Preço e custos",
                "q": f"Quanto tempo um imóvel de alto padrão leva para vender {b['em']}?",
                "a": (f"Imóveis acima de {s['limiar_texto']} {b['em']} venderam em {b['tempo_medio_venda']} dias, "
                      f"em média, com desconto de negociação de {pct(b['desconto_negociacao'])} "
                      f"{s['periodo_texto']}."),
                "link": self._link_guia("liquidez-imoveis-alto-padrao-por-bairro-fortaleza"),
            },
            {
                "grupo": "Tributos e prazos da compra",
                "q": f"Quanto é o ITBI na compra d{ref}?",
                "a": (f"O ITBI d{ref} é de {brl(itbi)}, alíquota de {itbi_cfg['aliquota_texto']} cobrada "
                      f"{cid['por']} sobre o valor da transação de {brl(i['preco'])}. {itbi_cfg['regra_reducao']} "
                      f"o imposto cai para {brl(itbi_antecipado)}. O ITBI é pago pelo comprador; escritura e "
                      f"registro seguem a tabela de emolumentos do Estado {cid['do_estado']}."),
            },
            {
                "grupo": "Tributos e prazos da compra",
                "q": f"Quanto tempo leva a transferência d{ref} após a escritura?",
                "a": ("O Cartório de Registro de Imóveis tem prazo legal de até 10 dias úteis, contados do "
                      "protocolo, para registrar a transferência (art. 188 da Lei 6.015/1973). Com financiamento "
                      "bancário, a análise de crédito e a avaliação do imóvel precedem a escritura."),
            },
            {
                "grupo": "Tributos e prazos da compra",
                "q": f"Comprar {ref} por holding familiar muda o ITBI?",
                "a": ("Não. A compra direta por uma holding paga o mesmo ITBI da pessoa física. A imunidade vale apenas "
                      "para imóveis que o sócio já possui e integraliza no capital social da holding."),
                "link": self._link_guia("holding-familiar-imoveis-alto-padrao"),
            },
            {
                "grupo": "Medições técnicas",
                "q": f"Como foi medido o isolamento acústico d{ref}?",
                "a": (f"As esquadrias d{ref} têm índice Rw {tec['rw_db']} dB, medido em laboratório pela "
                      f"ISO 10140-2 e classificado pela EN ISO 717-1. O laudo de compra inclui a medição em "
                      f"campo da fachada (índice D2m,nT,w, ISO 16283-3), revisada pela arquiteta {responsavel['nome']}."),
                "link": self._link_guia("isolamento-acustico-blindagem-gerador-imoveis-luxo"),
            },
            {
                "grupo": "Medições técnicas",
                "q": f"O gerador d{ref} atende toda a carga elétrica?",
                "a": (f"Sim. O gerador de {num(tec['gerador_kva'])} kVA atende {tec['gerador_cobertura_pct']}% "
                      f"da carga elétrica, com autonomia de {tec['gerador_autonomia_h']} horas."),
            },
            {
                "grupo": "Medições técnicas",
                "q": f"Qual o nível de blindagem da portaria d{ref}?",
                "a": (f"Nível {tec['blindagem_nivel']} pela ABNT NBR 15000, testado contra disparos de 9 mm "
                      f"e .44 Magnum."),
            },
            *([{
                "grupo": "Medições técnicas",
                "q": f"{_cap(ref)} tem proteção contra maresia?",
                "a": (f"Sim. {tec['maresia']}. A especificação para ambiente marinho é exigida pela "
                      f"{s['nome']} em imóveis a menos de 500 m do mar."),
                "link": self._link_guia("isolamento-acustico-blindagem-gerador-imoveis-luxo"),
            }] if tec.get("maresia") else []),
            *i.get("perguntas", []),
        ]

    @staticmethod
    def _tem_ficha(i: dict) -> bool:
        """Ficha no ar: ativo, ou encerrado (vendido/indisponivel) que manteve a ficha completa.

        Só vai ao ar com `publicacao_autorizada: true` (exatamente o booleano). Sem isso é rascunho: não tem
        página, não entra no sitemap nem no llms.txt. Com `redirecionar_para_bairro` a ficha dá lugar a uma
        página de redirecionamento. Encerrado só com código/título/data (registro mínimo) é 404 real.
        """
        completo = i["status"] == "ativo" or (i["status"] in ENCERRADOS and "resumo" in i)
        return (completo and i.get("publicacao_autorizada") is True
                and not i.get("redirecionar_para_bairro"))

    def _enriquecer_encerrado(self, i: dict) -> None:
        """Ficha de imóvel que saiu da carteira: sem preço anunciado e sem alegar a venda como nossa.

        Texto sempre "não está mais disponível": sem exclusividade, o imóvel pode ter sido vendido por
        terceiros ou retirado. Valor da venda e % do pedido só com `preco_venda_autorizado: true` (e só em
        `vendido`): com o preço anunciado já público, o percentual revela o valor da venda do mesmo jeito.
        """
        b, s = self.bairros[i["bairro"]], self.site
        ref = i["referencia"]
        i["data_encerramento"] = i[CAMPO_DATA[i["status"]]]
        data = data_extenso(i["data_encerramento"])
        dias = i.get("dias_no_mercado")
        autorizado = bool(i["status"] == "vendido" and i.get("preco_venda_autorizado") and i.get("preco_venda"))
        i["encerrado"] = True
        i["preco_venda_publico"] = i["preco_venda"] if autorizado else None
        i["pct_do_pedido"] = round(i["preco_venda"] / i["preco"] * 100, 1) if autorizado else None
        prazo = f" Ficou {num(dias)} dias no mercado." if dias else ""
        i["resumo_encerrado"] = (
            f"{_cap(ref)} não está mais disponível desde {data}.{prazo} O imóvel tem {num(i['area_privativa'])} m², "
            f"{i['suites']} suítes e {i['vagas']} vagas, fica {b['em']} e foi entregue em {i['ano_construcao']}. "
            f"A {s['nome']} mantém imóveis semelhantes disponíveis {b['em']} e em bairros vizinhos."
        )
        situacao = [
            {"grupo": "Situação do imóvel", "q": f"{_cap(ref)} ainda está disponível?",
             "a": (f"Não. {_cap(ref)} não está mais disponível desde {data}. Veja os imóveis parecidos "
                   f"disponíveis na carteira da {s['nome']}.")},
        ]
        if dias:
            situacao.append({
                "grupo": "Situação do imóvel",
                "q": f"Quanto tempo {ref} ficou no mercado?",
                "a": (f"{num(dias)} dias, contra prazo médio de venda de {b['tempo_medio_venda']} dias dos imóveis "
                      f"acima de {s['limiar_texto']} {b['em']} {s['periodo_texto']}."),
            })
        if i["status"] == "vendido":
            situacao.append({
                "grupo": "Situação do imóvel",
                "q": f"Por quanto {ref} foi vendido?",
                "a": (f"{brl(i['preco_venda'])}, {pct(i['pct_do_pedido'])} do preço anunciado de {brl(i['preco'])}."
                      if autorizado else "O valor da venda não é divulgado."),
            })
        # preço, ITBI e prazos de compra deixam de valer; medições técnicas e perguntas próprias ficam
        i["faq"] = situacao + [q for q in i["faq"]
                               if q["grupo"] not in ("Preço e custos", "Tributos e prazos da compra")]

    def _link_guia(self, slug: str) -> dict | None:
        if slug not in self.artigos:
            raise ValueError(f"FAQ aponta para guia inexistente: {slug}")
        return {"href": f"/guias/{slug}/", "texto": self.artigos[slug]["titulo"]}

    # -------------------------------------------------------------- consultas
    def ativos(self, bairro: str | None = None) -> list[dict]:
        itens = [i for i in self.imoveis.values()
                 if i["status"] == "ativo" and self._tem_ficha(i) and (bairro is None or i["bairro"] == bairro)]
        return sorted(itens, key=lambda i: i["preco"], reverse=True)

    def encerrados(self) -> list[dict]:
        """Imóveis que saíram da carteira e mantêm a ficha no ar, do mais recente para o mais antigo."""
        itens = [i for i in self.imoveis.values() if i.get("encerrado")]
        return sorted(itens, key=lambda i: i["data_encerramento"], reverse=True)

    def redirecionados(self) -> dict[str, dict]:
        """slug -> bairro de destino dos imóveis marcados com `redirecionar_para_bairro`."""
        return {i["slug"]: self.bairros[i["bairro"]] for i in self.imoveis.values()
                if i.get("redirecionar_para_bairro") and i["status"] in ENCERRADOS}

    def imovel(self, slug: str) -> dict | None:
        """Registro do imóvel; None se não existe ou é rascunho (ficha completa sem autorização)."""
        i = self.imoveis.get(slug)
        if i is None:
            return None
        if slug in self.redirecionados():
            return i
        if i["status"] == "ativo" or "resumo" in i:
            return i if self._tem_ficha(i) else None
        return i  # registro mínimo de vendido/retirado: o app responde 404 informativo

    def imoveis_por_consultor(self, slug: str) -> list[dict]:
        return [i for i in self.ativos() if i["consultor"] == slug]

    def artigos_recentes(self) -> list[dict]:
        return sorted(self.artigos.values(), key=lambda a: a["publicado"], reverse=True)

    def artigos_sobre_imovel(self, slug: str) -> list[dict]:
        return [a for a in self.artigos_recentes() if slug in a.get("imoveis_relacionados", [])]

    def artigos_sobre_bairro(self, slug: str) -> list[dict]:
        """Guias que citam o bairro primeiro; depois os demais guias (todo comprador precisa deles)."""
        todos = self.artigos_recentes()
        return sorted(todos, key=lambda a: slug not in a.get("bairros_relacionados", []))

    def artigos_por_autor(self, slug: str) -> list[dict]:
        return [a for a in self.artigos_recentes() if a["autor"] == slug]

    def videos_por_pessoa(self, slug: str) -> list[tuple[dict, dict]]:
        """(vídeo, página onde está incorporado) apresentados pela pessoa."""
        paginas = [*self.ativos(), *self.artigos_recentes()]
        return [(v, pg) for pg in paginas for v in pg.get("videos", []) if v["apresentador"] == slug]

    def pilar_do_bairro(self, slug: str) -> dict | None:
        return next((p for p in self.pilares.values() if slug in p["bairros"]), None)

    def bairros_por_liquidez(self) -> list[dict]:
        return sorted(self.bairros.values(), key=lambda b: b["tempo_medio_venda"])

    def faq_institucional(self) -> list[dict]:
        """Perguntas que o comprador faz sobre a empresa e o mercado, respondidas só com dados do site.json.

        Valores (preços, prazos, alíquotas, endereço) saem dos mesmos dados das páginas: nada digitado à mão.
        """
        from .formatting import brl

        s, cid, e = self.site, self.site["cidade"], self.site["endereco"]
        ativos = self.ativos()
        liquidez = self.bairros_por_liquidez()
        rapido, lento = liquidez[0], liquidez[-1]
        nomes = [b["nome"] for b in liquidez]
        bairros_txt = ", ".join(nomes[:-1]) + " e " + nomes[-1]
        itbi = s["itbi"]
        carteira = (f"a carteira atual tem {len(ativos)} ofertas entre {brl(ativos[-1]['preco'])} e "
                    f"{brl(ativos[0]['preco'])}, nos bairros {bairros_txt}." if ativos else
                    f"a carteira está em atualização; fale com a equipe sobre os bairros {bairros_txt}.")
        return [
            {"q": f"O que é a {s['nome']}?",
             "a": f"{s['contexto_fonte'][0]} Registro {s['creci']}, CNPJ {s['cnpj']}, escritório na {e['rua']}, {e['bairro']}, {e['cidade']} ({e['uf']})."},
            {"q": f"Onde fica o escritório da {s['nome']} {cid['em']}?",
             "a": f"Na {e['rua']}, bairro {e['bairro']}, {e['cidade']} – {e['uf']}, CEP {e['cep']}. Atendimento {s['horario_texto'].lower()}."},
            {"q": "Como falar com um consultor?",
             "a": f"Pelo WhatsApp e telefone {s['telefone']} ou pelo e-mail {s['email']}. {s['horario_texto']}."},
            {"q": f"Quais imóveis a {s['nome']} vende {cid['em']}?",
             "a": f"Imóveis acima de {s['limiar_texto']}: {carteira}"},
            {"q": f"Qual bairro de alto padrão {cid['em']} vende mais rápido?",
             "a": f"{rapido['nome']}: {rapido['tempo_medio_venda']} dias de prazo médio de venda {s['periodo_texto']}. O maior prazo foi {lento['nome']}, com {lento['tempo_medio_venda']} dias."},
            {"q": f"Qual a alíquota do ITBI {cid['em']}?",
             "a": f"A alíquota do ITBI {cid['em']} é de {itbi['aliquota_texto']} sobre o valor do imóvel, conforme os parâmetros deste site. Há alíquota reduzida de {itbi['aliquota_antecipada'] * 100:g}% no pagamento antecipado dentro dos prazos da Lei Complementar municipal 159/2013. Confirme valores e prazos com a Prefeitura ou com seu advogado antes de fechar negócio."},
            {"q": "Os preços por m² são de que fonte e período?",
             "a": f"{s['fonte_dados']} No pilar de mercado, cada indicador traz fonte, data e link da publicação original."},
        ]

    def paginas_indexaveis(self) -> list[tuple[str, str | None]]:
        """(path, lastmod) de todas as URLs que devem responder HTTP 200."""
        ult_artigo = max(a["atualizado"] for a in self.artigos.values())
        ult_imovel = max((i["data_atualizacao"] for i in self.ativos()), default=ult_artigo)
        paginas = [("/", max(ult_imovel, ult_artigo)), ("/imoveis/", ult_imovel),
                   ("/guias/", ult_artigo), ("/especialistas/", None), ("/sobre/", None), ("/contato/", None)]
        paginas += [(i["path"], i["data_atualizacao"]) for i in self.ativos()]
        paginas += [(i["path"], i["data_encerramento"]) for i in self.encerrados()]
        paginas += [(b["path"], ult_imovel) for b in self.bairros.values()]
        paginas += [(a["path"], a["atualizado"]) for a in self.artigos_recentes()]
        paginas += [(p["path"], None) for p in self.pessoas.values()]
        paginas += [(p["path"], p["atualizado"]) for p in self.pilares.values()]
        return paginas

    def paginas_redirecionadas(self) -> list[str]:
        """URLs que respondem com a página de redirecionamento (fora do sitemap e do llms.txt)."""
        return [self.imoveis[s]["path"] for s in self.redirecionados()]
