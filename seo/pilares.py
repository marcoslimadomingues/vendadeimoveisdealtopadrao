"""Páginas-pilar: indicadores com fonte e data, geografia (OpenStreetMap) e textos derivados.

Todo número que aparece em texto corrido (resumo, delimitação, FAQ) é calculado aqui a partir
de `indicadores` e de `data/geo/milha_de_ouro.json`, para que tabela, texto e JSON-LD nunca divirjam.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .formatting import MESES, brl, num, pct

REF_MES = re.compile(r"^(\d{4})-(\d{2})$")


def mes_ano(ref: str) -> str:
    m = REF_MES.match(ref)
    return f"{MESES[int(m[2]) - 1]} de {m[1]}" if m else ref


def _lista(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def enriquecer(repo, p: dict, data_dir: Path) -> None:
    s, cid = repo.site, repo.site["cidade"]
    p["path"] = f"/{p['slug']}/"
    geo = json.loads((data_dir / "geo" / "milha_de_ouro.json").read_text(encoding="utf-8"))
    p["geo"] = geo
    fontes = p["fontes"]

    ind = {}
    for i in p["indicadores"]:
        i["fonte_info"] = fontes[i["fonte"]]
        i["valor_txt"] = ("perto de " if i.get("aproximado") else "") + brl(i["valor"]) + "/m²"
        i["ref_txt"] = mes_ano(i["referencia"])
        ind[i["id"]] = i
    p["indic"] = ind
    mi, me, fo, be, ir, mu = (ind[k] for k in ("milha", "meireles", "fortaleza", "beira_mar", "praia_iracema", "mucuripe"))

    d = {
        "meireles_vs_cidade": (me["valor"] / fo["valor"] - 1) * 100,
        "mucuripe_vs_cidade": (mu["valor"] / fo["valor"] - 1) * 100,
        "mucuripe_vs_meireles": (mu["valor"] / me["valor"] - 1) * 100,
        # mesma fonte e mesmo mês (julho/2026): Beira Mar × Meireles
        "beira_vs_meireles_jul": (be["valor"] / me["valor_anterior"] - 1) * 100,
    }
    p["derivados"] = d
    ext = num(geo["extensao_km"], 1)
    fn_dn, fn_op = fontes["dn"], fontes["op"]
    dn_data = f"{int(fn_dn['publicado'][8:])} de {MESES[int(fn_dn['publicado'][5:7]) - 1]} de {fn_dn['publicado'][:4]}"
    maior, menor = ("Mucuripe", "Meireles") if mu["valor"] >= me["valor"] else ("Meireles", "Mucuripe")

    p["titulo_h1"] = f"{p['nome']}: {p['subtitulo']}"
    p["resumo"] = (
        f"A milha de ouro de Fortaleza é a faixa da Avenida Beira Mar entre o Meireles e o Mucuripe, com {ext} km de orla. "
        f"Em agosto de 2026, o m² privativo médio foi de {brl(mu['valor'])} no Mucuripe e de {brl(me['valor'])} no Meireles "
        f"(Sinduscon-CE). O valor do Meireles é {pct(d['meireles_vs_cidade'])} maior que a média de Fortaleza, de {brl(fo['valor'])}. "
        f"Em julho, a Avenida Beira Mar liderava o ranking com {brl(be['valor'])} por m², e coluna do {fn_dn['veiculo']} de "
        f"{dn_data} situa a milha de ouro perto de R$ 25 mil por m²."
    )
    p["descricao"] = (
        f"Milha de ouro de Fortaleza: Avenida Beira Mar entre Meireles e Mucuripe, {ext} km de orla. "
        f"Mapa, ruas, marcos, m² por fonte e data (Meireles {brl(me['valor'])}, Mucuripe {brl(mu['valor'])}, ago/2026) e perguntas respondidas."
    )
    p["delimitacao"] = [
        (f"Neste guia, a milha de ouro é a Avenida Beira Mar dentro dos bairros Meireles e Mucuripe: {ext} km de orla, "
         f"do limite do Meireles com a Praia de Iracema, a oeste, até o fim do Mucuripe, a leste. "
         f"O termo é usado pela imprensa local e não tem delimitação oficial."),
        (f"Os limites seguem os polígonos administrativos do OpenStreetMap, consultados em 12 de outubro de 2026, e podem "
         f"diferir em alguns metros dos limites oficiais da Prefeitura de Fortaleza. A Praia de Iracema, vizinha a oeste, "
         f"fica fora da faixa."),
    ]

    transversais = [t["nome"] for t in geo["transversais"]]
    ab = next((r for r in geo["paralelas"] if r["nome"] == "Avenida da Abolição"), None)
    abolicao = (f"A Avenida da Abolição corre paralela à orla, a cerca de {ab['distancia_m']} m da Avenida Beira Mar "
                f"em média." if ab else "")
    p["faq"] = [
        {"q": "O que é a milha de ouro de Fortaleza?",
         "a": (f"A milha de ouro de Fortaleza é o nome que a imprensa local usa para a faixa da Avenida Beira Mar entre o "
               f"Meireles e o Mucuripe, com {ext} km de orla. O termo não tem delimitação oficial. O {fn_dn['veiculo']} o "
               f"empregou em coluna de {dn_data} sobre os lançamentos da Dasart na região.")},
        {"q": "Quanto custa o metro quadrado na milha de ouro de Fortaleza?",
         "a": (f"A coluna do {fn_dn['veiculo']} de {dn_data} situa o m² da milha de ouro perto de R$ 25 mil, citando o "
               f"Sinduscon-CE. O dado é aproximado e o recorte não consta no levantamento de agosto de 2026. Em julho de 2026, "
               f"o Sinduscon-CE registrou {brl(be['valor'])} por m² na Avenida Beira Mar.")},
        {"q": "Qual o preço médio do m² no Meireles?",
         "a": (f"{brl(me['valor'])} por m² privativo em agosto de 2026, alta de {num(me['variacao_mensal'], 2)}% sobre julho "
               f"({brl(me['valor_anterior'])}), segundo o Sinduscon-CE. O valor é {pct(d['meireles_vs_cidade'])} maior que a "
               f"média de Fortaleza, de {brl(fo['valor'])}.")},
        {"q": "O Mucuripe é mais caro que o Meireles?",
         "a": (f"Em agosto de 2026, o {maior} ficou à frente do {menor} por {pct(abs(d['mucuripe_vs_meireles']))}, "
               f"ou {brl(abs(mu['valor'] - me['valor']))} por m²: {brl(mu['valor'])} no Mucuripe contra "
               f"{brl(me['valor'])} no Meireles (Sinduscon-CE). A diferença é pequena.")},
        {"q": "Qual o bairro mais caro de Fortaleza?",
         "a": (f"Em agosto de 2026, a Praia de Iracema, com {brl(ir['valor'])} por m², à frente do Mucuripe "
               f"({brl(mu['valor'])}) e do Meireles ({brl(me['valor'])}), segundo o Sinduscon-CE. A Praia de Iracema não "
               f"faz parte da faixa tratada neste guia.")},
        {"q": "Quais ruas chegam à Avenida Beira Mar na milha de ouro?",
         "a": (f"As principais transversais, de oeste para leste, são {_lista(transversais)}, segundo o mapa viário do "
               f"OpenStreetMap. {abolicao}")},
        {"q": "A maresia e o ruído afetam os imóveis da orla de Fortaleza?",
         "a": ("Sim. Nas primeiras quadras da orla, a névoa salina corrói esquadrias e equipamentos, e o ruído noturno da "
               "Avenida Beira Mar e dos eventos exige esquadrias acústicas. A "
               f"{s['nome']} só classifica como Isolamento Acústico Europeu esquadrias com Rw de 42 dB ou mais, e exige "
               "especificação para ambiente marinho em imóveis a menos de 500 m do mar, com laudos revisados pela "
               "arquiteta Marina Albuquerque."),
         "link": {"href": "/guias/isolamento-acustico-blindagem-gerador-imoveis-luxo/",
                  "texto": repo.artigos["isolamento-acustico-blindagem-gerador-imoveis-luxo"]["titulo"]}},
        {"q": "Quais empreendimentos a imprensa cita na milha de ouro?",
         "a": (f"O {fn_dn['veiculo']}, em {dn_data}, cita os empreendimentos "
               f"{_lista([e['nome'] for e in p['empreendimentos_citados']])}, da Dasart "
               f"(o DM 210, em parceria com a Normatel Incorporações).")},
    ]
    p["imoveis"] = [i for i in repo.ativos() if i["bairro"] in p["bairros"]]
    p["fonte_txt"] = {k: f"{v['veiculo']}, {v['publicado'][8:]}/{v['publicado'][5:7]}/{v['publicado'][:4]}"
                      for k, v in fontes.items()}
    p["cidade"] = cid["nome"]
