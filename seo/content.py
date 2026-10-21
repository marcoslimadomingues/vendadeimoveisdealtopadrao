"""Repositório de conteúdo: carrega /data, valida referências e calcula métricas derivadas.

Todos os números exibidos (preço/m², custo mensal, comparação com o bairro) são
calculados aqui, uma única vez, para que HTML, JSON-LD e FAQ nunca divirjam.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import pilares as _pilares
from .formatting import brl, cap as _cap, data_extenso, num, pct

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
# SITE_DATA_DIR troca a pasta de dados (os testes usam uma carteira de demonstração fora de data/).
DATA_DIR = Path(os.environ.get("SITE_DATA_DIR") or Path(__file__).resolve().parent.parent / "data")


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


# Tokens do levantamento do Sinduscon-CE (data/sinduscon.json), em guias com `"dados": "sinduscon"`:
#   {sm2:ID} {sant:ID} {svar:ID} {sacima:ID} {sdif:A:B} {spct:A:B} {spos:ID}
#   {sref} {srefant} {sveic} {sdata} {sfm} {sfa}
TOKEN_S = re.compile(r"\{(sm2|sant|svar|sacima|sdif|spct|spos):([a-z0-9_]+)(?::([a-z0-9_]+))?\}")
TOKEN_S0 = re.compile(r"\{(sref|srefant|sveic|sdata|sfm|sfa)\}")


def _token_s(m: re.Match, sd: dict) -> str:
    kind, a, b = (m.groups() + (None, None))[:3]
    if kind in ("sref", "srefant", "sveic", "sdata", "sfm", "sfa"):
        return {"sref": sd["ref_txt"], "srefant": sd["ref_ant_txt"], "sveic": sd["fonte"]["veiculo"],
                "sdata": data_extenso(sd["fonte"]["publicado"]),
                "sfm": num(sd["fortaleza"]["var_mes_pct"], 0) + "%",
                "sfa": num(sd["fortaleza"]["var_ano_pct"], 0) + "%"}[kind]
    ind = sd["por_id"]
    cidade = {"m2": sd["fortaleza"]["m2"]}
    ref = {**ind, "fortaleza": cidade}
    if a not in ref or (kind in ("sdif", "spct") and b not in ref):
        raise ValueError(f"token {m[0]} aponta para bairro inexistente em sinduscon.json")
    if kind == "sm2":
        return brl(ref[a]["m2"])
    if kind == "sant":
        return brl(ref[a]["m2_anterior"])
    if kind == "svar":
        return pct(abs(ref[a]["var_mes_pct"]))
    if kind == "sacima":
        return pct(ref[a]["acima_cidade_pct"])
    if kind == "spos":
        return f"{ref[a]['posicao']}º"
    if kind == "sdif":
        return brl(abs(ref[a]["m2"] - ref[b]["m2"]))
    return pct((ref[a]["m2"] / ref[b]["m2"] - 1) * 100)  # spct


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


# Tributos (data/site.json: itbi e itcd), em qualquer guia:
#   {t:itbi} {t:itbi2} {t:sfh} {t:sfhteto} {t:ufirce} {t:ufirceano}   {u:N} = N Ufirces em reais
#   {ti:VALOR} ITBI geral sobre VALOR   {ta:VALOR} ITBI antecipado sobre VALOR
#   ITCD sobre VALOR: {ih} herança, {dd} doação, {dn} doação da nua-propriedade; {eh} {ed} {en} = alíquota efetiva
TOKEN_T = re.compile(r"\{(t|u|ti|ta|ih|eh|dd|ed|dn|en):([a-z0-9_]+)\}")


def brl2(valor: float) -> str:
    return f"R$ {num(valor, 2)}"


def _token_t(m: re.Match, site: dict) -> str:
    kind, a = m.groups()
    itbi, itcd = site["itbi"], site["itcd"]
    if kind == "u":
        return brl(int(a) * itcd["ufirce"])
    if kind == "ti":
        return brl(int(a) * itbi["aliquota"])
    if kind == "ta":
        return brl(int(a) * itbi["aliquota_antecipada"])
    if kind in ("ih", "eh", "dd", "ed", "dn", "en"):
        tipo = "causa_mortis" if kind in ("ih", "eh") else "doacao"
        r = itcd_calcular(site, int(a), tipo, nua_propriedade=kind in ("dn", "en"))
        return brl(r["imposto"]) if kind in ("ih", "dd", "dn") else pct(r["efetiva"])
    try:
        return {
            "itbi": f"{itbi['aliquota'] * 100:g}%".replace(".", ","),
            "itbi2": f"{itbi['aliquota_antecipada'] * 100:g}%".replace(".", ","),
            "sfh": f"{itbi['sfh_aliquota'] * 100:g}%".replace(".", ","),
            "sfhteto": brl2(itbi["sfh_teto"]),
            "sfhano": str(itbi["sfh_ano"]),
            "ufirce": f"R$ {num(itcd['ufirce'], 5)}",
            "ufirceano": str(itcd["ufirce_ano"]),
        }[a]
    except KeyError:
        raise ValueError(f"token {m[0]} desconhecido") from None


def _expandir_tributos(no, site: dict):
    if isinstance(no, dict):
        for k, v in no.items():
            no[k] = _expandir_tributos(v, site)
    elif isinstance(no, list):
        for n, v in enumerate(no):
            no[n] = _expandir_tributos(v, site)
    elif isinstance(no, str) and "{" in no:
        return TOKEN_T.sub(lambda m: _token_t(m, site), no)
    return no


def itcd_calcular(site: dict, valor: float, tipo: str, nua_propriedade: bool = False) -> dict:
    """ITCD do Ceará por decomposição em faixas (Lei 15.812/2015, arts. 8º, 12, 16 e 17).

    tipo: "causa_mortis" (isenção de 7.000 Ufirces deduzida da base) ou "doacao".
    nua_propriedade: doação com reserva de usufruto tributa 2/3 do valor venal (art. 12).
    """
    c = site["itcd"]
    base_valor = valor * (2 / 3 if nua_propriedade else 1)
    ufirces = base_valor / c["ufirce"]
    if tipo == "causa_mortis":
        ufirces = max(0.0, ufirces - c["isencao_ufirces"])
    imposto_u, anterior = 0.0, 0.0
    for limite, aliq in c[tipo]:
        topo = ufirces if limite is None else min(ufirces, limite)
        if topo > anterior:
            imposto_u += (topo - anterior) * aliq
        anterior = limite if limite is not None else anterior
        if limite is None or ufirces <= limite:
            break
    imposto = imposto_u * c["ufirce"]
    return {"base_ufirces": ufirces, "imposto": imposto, "efetiva": imposto / valor * 100 if valor else 0.0}


def _chaves_fonte(item: dict) -> list[str]:
    """Item do radar cita uma fonte ("fonte": "chave") ou várias ("fonte": ["a", "b"])."""
    return [item["fonte"]] if isinstance(item["fonte"], str) else list(item["fonte"])


def _expandir_tokens(no, pilar: dict | None = None, sinduscon: dict | None = None):
    """Expande os tokens em todas as strings de um guia, no lugar."""
    if isinstance(no, dict):
        for k, v in no.items():
            no[k] = _expandir_tokens(v, pilar, sinduscon)
    elif isinstance(no, list):
        for n, v in enumerate(no):
            no[n] = _expandir_tokens(v, pilar, sinduscon)
    elif isinstance(no, str) and "{" in no:
        if pilar is not None:
            no = TOKEN.sub(lambda m: _token(m, pilar), no)
        if sinduscon is not None:
            no = TOKEN_S0.sub(lambda m: _token_s(m, sinduscon), no)
            no = TOKEN_S.sub(lambda m: _token_s(m, sinduscon), no)
        return no
    return no


class Repo:
    def __init__(self, data_dir: str | Path | None = None):
        d = Path(data_dir) if data_dir else DATA_DIR
        self.site: dict = _load(d / "site.json")
        self.bairros = _index(_load(d / "bairros.json"))
        self.imoveis = _index(_load(d / "imoveis.json"))
        self.artigos = _index(_load(d / "artigos.json"))
        self.pilares = _index(_load(d / "pilares.json")) if (d / "pilares.json").exists() else {}
        self.sinduscon: dict = _load(d / "sinduscon.json")  # m² de referência de todos os bairros
        # Radar de lançamentos: uma edição por semana, cada fato com fonte publicada
        self.radar = _index(_load(d / "radar.json")) if (d / "radar.json").exists() else {}
        self._data_dir = d
        self._validar()
        self._enriquecer()

    # ------------------------------------------------------------------ carga
    def _validar(self) -> None:
        erros = []
        for i in self.imoveis.values():
            if i["bairro"] not in self.bairros:
                erros.append(f"imóvel {i['slug']}: bairro '{i['bairro']}' inexistente")
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
            for s in a.get("imoveis_relacionados", []):
                if s not in self.imoveis or not self._tem_ficha(self.imoveis[s]):
                    erros.append(f"artigo {a['slug']}: imóvel relacionado '{s}' inexistente ou sem ficha no ar "
                                 "(sem publicacao_autorizada: true, ou retirado)")
            for s in a.get("bairros_relacionados", []):
                if s not in self.bairros:
                    erros.append(f"artigo {a['slug']}: bairro '{s}' inexistente")
            if a.get("pilar") and a["pilar"] not in self.pilares:
                erros.append(f"artigo {a['slug']}: pilar '{a['pilar']}' inexistente")
            if a.get("guia_pilar") and a["guia_pilar"] not in self.artigos:
                erros.append(f"artigo {a['slug']}: guia_pilar '{a['guia_pilar']}' inexistente")
            if not (STATIC_DIR / a["imagem"].removeprefix("/static/")).is_file():
                erros.append(f"artigo {a['slug']}: imagem '{a['imagem']}' não existe em static/")
            if "placeholder" not in a["imagem"] and not a.get("imagem_alt"):
                erros.append(f"artigo {a['slug']}: imagem sem imagem_alt")
            if a.get("imagem_ia") and "inteligência artificial" not in a.get("imagem_legenda", ""):
                erros.append(f"artigo {a['slug']}: imagem gerada por IA precisa dizer isso na legenda")
            if a.get("url_sob_pilar") and not a.get("pilar"):
                erros.append(f"artigo {a['slug']}: url_sob_pilar exige o campo pilar")
        for p in self.pilares.values():
            for b in p["bairros"]:
                if b not in self.bairros:
                    erros.append(f"pilar {p['slug']}: bairro '{b}' inexistente")
            for g in p["guias"]:
                if g not in self.artigos:
                    erros.append(f"pilar {p['slug']}: guia '{g}' inexistente")
            for ind in p["indicadores"]:
                if ind["fonte"] not in p["fontes"]:
                    erros.append(f"pilar {p['slug']}: indicador '{ind['id']}' sem fonte cadastrada")
                if not ind.get("referencia"):
                    erros.append(f"pilar {p['slug']}: indicador '{ind['id']}' sem data de referência")
        ids = [b["id"] for b in self.sinduscon["bairros"]]
        if len(ids) != len(set(ids)):
            erros.append("sinduscon.json: bairro repetido")
        for b in self.sinduscon["bairros"]:
            if not b.get("m2"):
                erros.append(f"sinduscon.json: '{b['id']}' sem m2")
        if not self.sinduscon.get("fonte", {}).get("url"):
            erros.append("sinduscon.json: fonte sem url")
        for slug in self.bairros:
            if slug not in ids:  # sem m² publicado, o bairro não tem número para mostrar
                erros.append(f"bairro '{slug}' sem preço do m² em sinduscon.json")
        for e in self.radar.values():
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["slug"]) or e["slug"] != e["publicado"]:
                erros.append(f"radar {e['slug']}: slug deve ser a data de publicação (AAAA-MM-DD)")
            usadas = set()
            for item in [*e["mercado"], *e["lancamentos"]]:
                for chave in _chaves_fonte(item):
                    usadas.add(chave)
                    if chave not in e["fontes"]:
                        erros.append(f"radar {e['slug']}: fonte '{chave}' não cadastrada")
                if item.get("bairro") and item["bairro"] not in self.bairros:
                    erros.append(f"radar {e['slug']}: bairro '{item['bairro']}' inexistente")
            for chave, f in e["fontes"].items():
                if not f.get("url", "").startswith("https://") or not f.get("veiculo") or not f.get("publicado"):
                    erros.append(f"radar {e['slug']}: fonte '{chave}' exige veiculo, publicado e url https")
                if chave not in usadas:
                    erros.append(f"radar {e['slug']}: fonte '{chave}' cadastrada e não citada")
            if "indexar" in e and e["indexar"] is not False:
                erros.append(f"radar {e['slug']}: 'indexar' só aceita false (fora do índice); omita para indexar")
        # Indicador de mercado não se repete entre edições: número já publicado fica na edição em que saiu
        # (e no guia de m² por bairro). Repetir faz as edições parecerem cópias umas das outras.
        ja_citadas: dict[str, str] = {}
        for e in sorted(self.radar.values(), key=lambda x: x["publicado"]):
            for item in e["mercado"]:
                for chave in _chaves_fonte(item):
                    url = e["fontes"].get(chave, {}).get("url")
                    if url in ja_citadas and ja_citadas[url] != e["slug"]:
                        erros.append(f"radar {e['slug']}: indicador '{item['fato']}' repete fonte já usada na edição "
                                     f"{ja_citadas[url]}; ligue para o guia em vez de repetir o número")
                    elif url:
                        ja_citadas[url] = e["slug"]
        for item in [*self.artigos.values(), *(i for i in self.imoveis.values() if self._tem_ficha(i))]:
            for v in item.get("videos", []):
                if len(v["youtube_id"]) != 11:
                    erros.append(f"{item['slug']}: youtube_id '{v['youtube_id']}' deve ter 11 caracteres")
        if erros:
            raise ValueError("Dados inconsistentes:\n- " + "\n- ".join(erros))

    def _enriquecer(self) -> None:
        for b in self.bairros.values():
            b["path"] = f"/bairros/{b['slug']}/"
        self._enriquecer_sinduscon()
        for a in self.artigos.values():
            a["path"] = (f"/{a['pilar']}/{a['slug']}/" if a.get("url_sob_pilar") else f"/guias/{a['slug']}/")
            # gráfico gerado por tools/imagens_guias.py: recortes 16:9, 4:3 e 1:1 para o Google
            a["imagens"] = ([a["imagem"].replace("-16x9.", f"-{r}.") for r in ("16x9", "4x3", "1x1")]
                            if "-16x9." in a["imagem"] else [a["imagem"]])
            _expandir_tributos(a, self.site)
            if a.get("pilar") or a.get("dados") == "sinduscon":
                _expandir_tokens(a, self.pilares.get(a.get("pilar", "")),
                                 self.sinduscon if a.get("dados") == "sinduscon" else None)
            if a.get("pilar"):
                if "imoveis_relacionados" not in a:  # imóveis no ar, nos bairros do pilar
                    a["imoveis_relacionados"] = [
                        i["slug"] for i in self.ativos() if i["bairro"] in self.pilares[a["pilar"]]["bairros"]]
            a.setdefault("videos", [])
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
        for e in self.radar.values():
            e["path"] = f"/radar/{e['slug']}/"
            # fontes na ordem em que aparecem na edição, numeradas para a nota de rodapé
            ordem = list(dict.fromkeys(k for item in [*e["lancamentos"], *e["mercado"]] for k in _chaves_fonte(item)))
            for item in [*e["lancamentos"], *e["mercado"]]:
                item["fontes_item"] = _chaves_fonte(item)
            e["fontes_lista"] = [{"chave": k, "n": n, **e["fontes"][k]} for n, k in enumerate(ordem, start=1)]
            e["fonte_n"] = {f["chave"]: f["n"] for f in e["fontes_lista"]}

    def _enriquecer_sinduscon(self) -> None:
        """Ranking do levantamento e dados dos bairros do site: o m² de referência é sempre o do Sinduscon-CE.

        O m² médio e o resumo de cada bairro vêm daqui. O site não publica métrica própria (valorização,
        prazo de venda, desconto): só o que o levantamento divulgou.
        """
        sd = self.sinduscon
        cidade = sd["fortaleza"]["m2"]
        itens = sorted(sd["bairros"], key=lambda x: x["m2"], reverse=True)
        for pos, it in enumerate(itens, start=1):
            it["posicao"] = pos
            it["acima_cidade_pct"] = (it["m2"] / cidade - 1) * 100
            it["var_mes_pct"] = (it["m2"] / it["m2_anterior"] - 1) * 100 if it.get("m2_anterior") else None
            it["slug_pagina"] = it["id"] if it["id"] in self.bairros else None
        sd["ranking"] = itens
        sd["total"] = len(itens)
        sd["por_id"] = {it["id"]: it for it in itens}
        sd["ref_txt"] = _pilares.mes_ano(sd["referencia"])
        sd["ref_ant_txt"] = _pilares.mes_ano(sd["referencia_anterior"])
        for b in self.bairros.values():
            it = sd["por_id"][b["slug"]]
            b["sinduscon"] = it
            b["preco_m2"] = it["m2"]
            variacao = ""
            if it["var_mes_pct"] is not None:
                verbo = "subiu" if it["var_mes_pct"] >= 0 else "caiu"
                variacao = f" Em relação a {sd['ref_ant_txt']}, o valor {verbo} {pct(abs(it['var_mes_pct']))}."
            b["resumo"] = (
                f"{_cap(b['em'])}, o preço médio do m² foi de {brl(it['m2'])} em {sd['ref_txt']}, segundo o "
                f"Sinduscon-CE divulgado por {sd['fonte']['veiculo']}: {it['posicao']}º entre os {sd['total']} bairros "
                f"do levantamento e {pct(it['acima_cidade_pct'])} acima da média de Fortaleza "
                f"({brl(cidade)}).{variacao}")

    def _enriquecer_imovel(self, i: dict) -> None:
        b = self.bairros[i["bairro"]]
        i.setdefault("videos", [])
        i.setdefault("amenidades", [])
        i.setdefault("especificacoes", [])
        # Dados técnicos só com documento (laudo, memorial, certificado): cada campo é opcional.
        tec = i["tecnico"] = {k: v for k, v in (i.get("tecnico") or {}).items() if v not in (None, "")}
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
                      f"por m² {b['de']} ({self.sinduscon['ref_txt']}, Sinduscon-CE)."),
            },
            {
                "grupo": "Preço e custos",
                "q": f"Quanto custa manter {ref} por mês?",
                "a": (f"O custo fixo mensal d{ref} é de {brl(i['custo_mensal'])}: {partes}. "
                      f"O IPTU anual é de {brl(i['iptu_anual'])}.{sem_condominio}"),
            },
            {
                "grupo": "Tributos e prazos da compra",
                "q": f"Quanto é o ITBI na compra d{ref}?",
                "a": (f"O ITBI d{ref} é de {brl(itbi)}, alíquota geral de {itbi_cfg['aliquota_texto']} cobrada "
                      f"{cid['por']} sobre a base de {brl(i['preco'])} (o maior valor entre o de mercado, o "
                      f"declarado e o do IPTU). {itbi_cfg['regra_reducao']} o imposto cai para "
                      f"{brl(itbi_antecipado)}. O ITBI é pago pelo comprador; escritura e registro seguem a "
                      f"tabela de emolumentos do Estado {cid['do_estado']}."),
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
            *self._faq_tecnico(i),
            *i.get("perguntas", []),
        ]

    def _faq_tecnico(self, i: dict) -> list[dict]:
        """Perguntas técnicas só para o que a documentação do imóvel informa."""
        tec, ref = i["tecnico"], i["referencia"]
        guia = self._link_guia("isolamento-acustico-blindagem-gerador-imoveis-luxo")
        faq = []
        if tec.get("rw_db"):
            faq.append({"q": f"Qual o isolamento acústico das esquadrias d{ref}?",
                        "a": (f"Índice Rw {tec['rw_db']} dB, medido em laboratório pela ISO 10140-2 e classificado "
                              f"pela EN ISO 717-1. O desempenho da fachada instalada é medido em campo pelo índice "
                              f"D2m,nT,w (ISO 16283-3)."),
                        "link": guia})
        if tec.get("gerador_kva"):
            cobertura = tec.get("gerador_cobertura_pct")
            autonomia = f", com autonomia de {tec['gerador_autonomia_h']} horas" if tec.get("gerador_autonomia_h") else ""
            faq.append({"q": f"O gerador d{ref} atende toda a carga elétrica?",
                        "a": (f"{'Sim. ' if cobertura == 100 else ''}O gerador de {num(tec['gerador_kva'])} kVA "
                              + (f"atende {cobertura}% da carga elétrica" if cobertura else "atende o edifício")
                              + f"{autonomia}.")})
        if tec.get("blindagem_nivel"):
            faq.append({"q": f"Qual o nível de blindagem da portaria d{ref}?",
                        "a": f"Nível {tec['blindagem_nivel']} pela ABNT NBR 15000."})
        if tec.get("maresia"):
            faq.append({"q": f"{_cap(ref)} tem proteção contra maresia?", "a": f"Sim. {tec['maresia']}.", "link": guia})
        return [{"grupo": "Medições técnicas", **q} for q in faq]

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
                "a": f"{num(dias)} dias no mercado, do anúncio à saída da carteira.",
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

    # ---------------------------------------------------- tabelas de tributos (calculadas)
    VALORES_EXEMPLO = (3_000_000, 5_000_000, 10_000_000)

    def tabela_itbi(self) -> dict:
        itbi = self.site["itbi"]
        linhas = []
        for v in (3_000_000, 5_000_000, 8_000_000, 10_000_000, 15_000_000):
            geral, antec = v * itbi["aliquota"], v * itbi["aliquota_antecipada"]
            linhas.append([brl(v), brl(geral), brl(antec), brl(geral - antec)])
        return {"caption": f"ITBI em Fortaleza por valor do imóvel: alíquota geral de {itbi['aliquota_texto']} e "
                           f"de {itbi['aliquota_antecipada'] * 100:g}% no pagamento antecipado",
                "cabecalho": ["Valor do imóvel", f"ITBI a {itbi['aliquota_texto']} (geral)",
                              f"ITBI a {itbi['aliquota_antecipada'] * 100:g}% (antes da escritura)",
                              "Economia com o pagamento antecipado"],
                "linhas": linhas}

    def tabela_itcd_faixas(self) -> dict:
        c = self.site["itcd"]
        linhas = []
        for chave, rotulo in (("causa_mortis", "Herança (causa mortis)"), ("doacao", "Doação")):
            anterior = 0
            for limite, aliq in c[chave]:
                if limite is None:
                    faixa_u, faixa_r = f"acima de {num(anterior)}", f"acima de {brl(anterior * c['ufirce'])}"
                else:
                    faixa_u = f"{num(anterior)} a {num(limite)}" if anterior else f"até {num(limite)}"
                    faixa_r = (f"{brl(anterior * c['ufirce'])} a {brl(limite * c['ufirce'])}" if anterior
                               else f"até {brl(limite * c['ufirce'])}")
                linhas.append([rotulo, faixa_u, faixa_r, f"{aliq * 100:g}%"])
                anterior = limite or anterior
        return {"caption": f"Faixas e alíquotas do ITCD no Ceará, em Ufirces e em reais (Ufirce {c['ufirce_ano']}: "
                           f"R$ {num(c['ufirce'], 5)})",
                "cabecalho": ["Tipo", "Faixa em Ufirces", f"Faixa em reais (Ufirce {c['ufirce_ano']})", "Alíquota da faixa"],
                "linhas": linhas}

    def tabela_itcd_exemplos(self) -> dict:
        linhas = []
        for v in self.VALORES_EXEMPLO:
            h = itcd_calcular(self.site, v, "causa_mortis")
            d = itcd_calcular(self.site, v, "doacao")
            n = itcd_calcular(self.site, v, "doacao", nua_propriedade=True)
            linhas.append([brl(v), brl(h["imposto"]), pct(h["efetiva"]), brl(d["imposto"]), pct(d["efetiva"]),
                           brl(n["imposto"]), pct(n["efetiva"])])
        return {"caption": "Simulação do ITCD no Ceará para um único imóvel, com a Ufirce de "
                           f"{self.site['itcd']['ufirce_ano']} (estimativa, sem outras deduções)",
                "cabecalho": ["Valor do imóvel", "Herança", "Alíquota efetiva", "Doação", "Alíquota efetiva",
                              "Doação da nua-propriedade (2/3)", "Alíquota efetiva sobre o valor total"],
                "linhas": linhas}

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

    def com_dados_tecnicos(self) -> list[dict]:
        """Imóveis no ar com ao menos um dado técnico documentado."""
        return [i for i in self.ativos() if i["tecnico"]]

    def artigos_recentes(self) -> list[dict]:
        return sorted(self.artigos.values(), key=lambda a: a["publicado"], reverse=True)

    def radar_edicoes(self) -> list[dict]:
        """Edições do radar, da mais recente para a mais antiga."""
        return sorted(self.radar.values(), key=lambda e: e["publicado"], reverse=True)

    def satelites_do_guia(self, slug: str) -> list[dict]:
        """Guias que declaram `guia_pilar: <slug>`, do mais recente para o mais antigo."""
        return [a for a in self.artigos_recentes() if a.get("guia_pilar") == slug]

    def artigos_sobre_imovel(self, slug: str) -> list[dict]:
        return [a for a in self.artigos_recentes() if slug in a.get("imoveis_relacionados", [])]

    def artigos_sobre_bairro(self, slug: str) -> list[dict]:
        """Guias que citam o bairro primeiro; depois os demais guias (todo comprador precisa deles)."""
        todos = self.artigos_recentes()
        return sorted(todos, key=lambda a: slug not in a.get("bairros_relacionados", []))

    def pilar_do_bairro(self, slug: str) -> dict | None:
        return next((p for p in self.pilares.values() if slug in p["bairros"]), None)

    def bairros_por_m2(self) -> list[dict]:
        """Bairros atendidos, do m² mais caro ao mais barato (Sinduscon-CE)."""
        return sorted(self.bairros.values(), key=lambda b: b["preco_m2"], reverse=True)

    def faq_institucional(self) -> list[dict]:
        """Perguntas que o comprador faz sobre a empresa e o mercado, respondidas só com dados do site.json.

        Valores (preços, alíquotas, endereço) saem dos mesmos dados das páginas: nada digitado à mão.
        """
        s, cid, e = self.site, self.site["cidade"], self.site["endereco"]
        ativos = self.ativos()
        sd = self.sinduscon
        nomes = [b["nome"] for b in self.bairros_por_m2()]
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
            {"q": f"Qual bairro {cid['de']} tem o m² mais caro?",
             "a": (f"{sd['ranking'][0]['nome']}, com {brl(sd['ranking'][0]['m2'])} em {sd['ref_txt']}, segundo o "
                   f"Sinduscon-CE divulgado por {sd['fonte']['veiculo']}. A média de {cid['nome']} foi de "
                   f"{brl(sd['fortaleza']['m2'])}.")},
            {"q": f"Qual a alíquota do ITBI {cid['em']}?",
             "a": f"A alíquota geral do ITBI {cid['em']} é de {itbi['aliquota_texto']} sobre a base de cálculo, segundo a Sefin. Pagando até o dia anterior à lavratura da escritura ou do contrato de financiamento, a alíquota é de {itbi['aliquota_antecipada'] * 100:g}%; na parte financiada pelo SFH, até {brl2(itbi['sfh_teto'])}, é de {itbi['sfh_aliquota'] * 100:g}%. Confirme valores e prazos com a Prefeitura ou com seu advogado antes de fechar negócio."},
            {"q": "Os preços por m² são de que fonte e período?",
             "a": (f"Os valores por bairro vêm do Sinduscon-CE, divulgados por {sd['fonte']['veiculo']} em "
                   f"{data_extenso(sd['fonte']['publicado'])}, com referência em {sd['ref_txt']}. Cada indicador "
                   f"traz fonte, data e link da publicação original. A {s['nome']} não publica estimativa própria "
                   "de valorização, prazo de venda ou desconto.")},
        ]

    def paginas_indexaveis(self) -> list[tuple[str, str | None]]:
        """(path, lastmod) de todas as URLs que devem responder HTTP 200."""
        ult_artigo = max(a["atualizado"] for a in self.artigos.values())
        ult_imovel = max((i["data_atualizacao"] for i in self.ativos()), default=ult_artigo)
        paginas = [("/", max(ult_imovel, ult_artigo)), ("/imoveis/", ult_imovel),
                   ("/guias/", ult_artigo), ("/sobre/", None), ("/contato/", None)]
        paginas += [(i["path"], i["data_atualizacao"]) for i in self.ativos()]
        paginas += [(i["path"], i["data_encerramento"]) for i in self.encerrados()]
        paginas += [(b["path"], ult_imovel) for b in self.bairros.values()]
        paginas += [(a["path"], a["atualizado"]) for a in self.artigos_recentes()]
        paginas += [(p["path"], p["atualizado"]) for p in self.pilares.values()]
        if self.radar:
            edicoes = self.radar_edicoes()
            paginas += [("/radar/", max(e.get("atualizado", e["publicado"]) for e in edicoes))]
            paginas += [(e["path"], e.get("atualizado", e["publicado"])) for e in edicoes if e.get("indexar") is not False]
        return paginas

    def paginas_fora_do_indice(self) -> list[str]:
        """Páginas no ar (HTTP 200, noindex) mas fora do sitemap: edições antigas do radar sem impressões."""
        return [e["path"] for e in self.radar_edicoes() if e.get("indexar") is False]

    def paginas_redirecionadas(self) -> list[str]:
        """URLs que respondem com a página de redirecionamento (fora do sitemap e do llms.txt)."""
        return [self.imoveis[s]["path"] for s in self.redirecionados()]
