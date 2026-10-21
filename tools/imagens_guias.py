"""Gera as imagens dos guias de dados (gráficos) a partir dos mesmos números das páginas.

Cada guia de dados ganha três recortes PNG (16:9, 4:3 e 1:1, os formatos que o Google pede para
Article); o 16:9 também aparece no topo do guia. Os valores usados ficam em
static/img/guias/dados.json: um teste compara esse manifesto com os dados atuais e acusa imagem
desatualizada quando o Sinduscon-CE, o ITBI ou o ITCD mudarem (aí é só rodar este script de novo).

Uso: python tools/imagens_guias.py      (requer matplotlib e Pillow; não fazem parte do site)
"""
from __future__ import annotations

import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seo.content import Repo, itcd_calcular  # noqa: E402
from seo.formatting import brl, data_extenso, num, pct  # noqa: E402

SAIDA = ROOT / "static" / "img" / "guias"
RECORTES = {"16x9": (16, 9), "4x3": (16, 12), "1x1": (12, 12)}  # polegadas a 100 dpi

# Paleta validada (scripts/validate_palette.js da skill dataviz): passa nas 6 checagens sobre branco.
OURO, AZUL = "#b07a1c", "#2a6db0"
CINZA = "#9a948a"  # referência (média da cidade, bairros fora da carteira)
TINTA, TINTA_SUAVE, LINHA, FUNDO = "#1c1a17", "#5f584e", "#e2dccf", "#ffffff"
ASSINATURA = "Alto Padrão Imóveis · vendadeimoveisdealtopadrao.com.br"


def _reais(texto: str) -> int:
    return int(re.sub(r"\D", "", texto))


def _mil(v: float) -> str:
    return f"R$ {num(round(v / 1000))} mil"


def dados_graficos(repo: Repo) -> dict[str, dict]:
    """Números de cada gráfico, tirados dos dados do site (fonte única para imagem, texto e teste)."""
    sd, site = repo.sinduscon, repo.site
    fonte_sd = f"Fonte: Sinduscon-CE, divulgado por {sd['fonte']['veiculo']} em {data_extenso(sd['fonte']['publicado'])}."
    d: dict[str, dict] = {}

    d["preco-m2-por-bairro-fortaleza"] = {
        "tipo": "ranking",
        "titulo": "Preço do m² por bairro em Fortaleza",
        "subtitulo": f"{sd['ref_txt'].capitalize()} · R$ por m² privativo · média da cidade: {brl(sd['fortaleza']['m2'])}",
        "fonte": fonte_sd,
        "barras": [[b["nome"], b["m2"], b["id"] in repo.bairros] for b in sd["ranking"]],
        "referencia": ["Média de Fortaleza", sd["fortaleza"]["m2"]],
        "legenda": "Em dourado, os bairros atendidos pela Alto Padrão Imóveis",
    }

    serie = next(s for s in repo.artigos["preco-m2-beira-mar"]["secoes"] if s["id"] == "serie")["tabela"]["linhas"]
    d["preco-m2-beira-mar"] = {
        "tipo": "colunas",
        "titulo": "Preço do m² na Avenida Beira Mar",
        "subtitulo": "R$ por m² privativo, por levantamento do Sinduscon-CE",
        "fonte": "Fontes: " + "; ".join(f"{ref}, {div}" for ref, _, _, div in serie) + ".",
        "barras": [[f"{ref}\n({lev.split(',')[0].lower()})", _reais(valor), True] for ref, valor, lev, _ in serie],
        "legenda": "Levantamentos trimestral e mensal têm bases diferentes: a diferença não mede valorização",
    }

    ind = repo.pilares["milha-de-ouro-fortaleza"]["indic"]
    d["meireles-ou-mucuripe-investir"] = {
        "tipo": "colunas",
        "titulo": "Meireles × Mucuripe: preço do m²",
        "subtitulo": f"{ind['mucuripe']['ref_txt'].capitalize()} · R$ por m² privativo",
        "fonte": f"Fonte: Sinduscon-CE, divulgado por {ind['mucuripe']['fonte_info']['veiculo']} em "
                 f"{data_extenso(ind['mucuripe']['fonte_info']['publicado'])}.",
        "barras": [["Mucuripe", ind["mucuripe"]["valor"], True], ["Meireles", ind["meireles"]["valor"], True],
                   ["Média de Fortaleza", ind["fortaleza"]["valor"], False]],
        "legenda": f"Diferença entre os dois bairros: {brl(abs(ind['mucuripe']['valor'] - ind['meireles']['valor']))} por m²",
    }

    itbi = site["itbi"]
    valores = (3_000_000, 5_000_000, 8_000_000, 10_000_000, 15_000_000)
    d["itbi-fortaleza-imoveis-alto-padrao"] = {
        "tipo": "grupos",
        "titulo": "ITBI em Fortaleza por valor do imóvel",
        "subtitulo": (f"Alíquota geral de {itbi['aliquota_texto']} e de {itbi['aliquota_antecipada'] * 100:g}% "
                      "com pagamento antes da escritura"),
        "fonte": f"Fonte: {itbi['fonte_nome']} (alíquotas de {itbi['sfh_ano']}). Base de cálculo igual ao valor do imóvel.",
        "grupos": [f"R$ {v // 1_000_000} mi" for v in valores],
        "series": [[f"ITBI geral ({itbi['aliquota_texto']})", [round(v * itbi["aliquota"]) for v in valores]],
                   [f"Pago antes da escritura ({itbi['aliquota_antecipada'] * 100:g}%)",
                    [round(v * itbi["aliquota_antecipada"]) for v in valores]]],
    }

    c = site["itcd"]
    exemplos = repo.VALORES_EXEMPLO
    d["itcd-ceara-imoveis"] = {
        "tipo": "grupos",
        "titulo": "ITCD no Ceará: herança × doação",
        "subtitulo": f"Imposto sobre um único imóvel · Ufirce de {c['ufirce_ano']} (R$ {num(c['ufirce'], 5)})",
        "fonte": f"Fonte: {c['lei']} e {c['ufirce_norma']}. Estimativa sem outras deduções.",
        "grupos": [f"Imóvel de R$ {v // 1_000_000} mi" for v in exemplos],
        "series": [["Herança", [round(itcd_calcular(site, v, "causa_mortis")["imposto"]) for v in exemplos]],
                   ["Doação", [round(itcd_calcular(site, v, "doacao")["imposto"]) for v in exemplos]]],
        "valores_base": list(exemplos),
    }
    return d


# ------------------------------------------------------------------------------------------ desenho
def _desenhar(slug: str, g: dict, recorte: str, destino: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["text.parse_math"] = False  # "R$" é moeda, não fórmula

    w, h = RECORTES[recorte]
    k = w / 16  # escala da tipografia
    fig = plt.figure(figsize=(w, h), dpi=100, facecolor=FUNDO)
    topo = 1 - 1.55 / h  # espaço do título e subtítulo, em fração da figura
    base = 1.55 / h
    esq = 0.06 + (2.3 / w if g["tipo"] == "ranking" else 0)  # nomes dos bairros à esquerda das barras
    ax = fig.add_axes((esq, base + 0.03, 0.94 - esq, topo - base - 0.07))
    fig.text(0.06, 1 - 0.55 / h, g["titulo"], fontsize=31 * k, fontweight="bold", color=TINTA, va="top")
    fig.text(0.06, 1 - 1.12 / h, g["subtitulo"], fontsize=18 * k, color=TINTA_SUAVE, va="top")
    fonte = textwrap.fill(g["fonte"], width=int(150 * w / 16 / k))
    fig.text(0.06, 0.62 / h, fonte, fontsize=13.5 * k, color=TINTA_SUAVE, va="bottom", linespacing=1.4)
    fig.text(0.06, 0.25 / h, ASSINATURA, fontsize=13.5 * k, color=OURO, va="bottom")
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_visible(False)
    ax.set_facecolor(FUNDO)
    rot = 17 * k

    if g["tipo"] == "ranking":
        nomes = [b[0] for b in g["barras"]][::-1]
        vals = [b[1] for b in g["barras"]][::-1]
        cores = [OURO if b[2] else CINZA for b in g["barras"]][::-1]
        ax.barh(nomes, vals, color=cores, height=0.68)
        ax.axvline(g["referencia"][1], color=TINTA, lw=2, ls=(0, (4, 3)))
        ax.text(g["referencia"][1], len(nomes) - 0.35, f" {g['referencia'][0]}", fontsize=rot * 0.85,
                color=TINTA, va="bottom")
        for y, v in enumerate(vals):
            ax.text(v + max(vals) * 0.01, y, brl(v), va="center", fontsize=rot, color=TINTA)
        ax.set_xlim(0, max(vals) * 1.17)
        ax.set_xticks([])
        ax.tick_params(axis="y", length=0, labelsize=rot, labelcolor=TINTA)
        ax.set_ylim(-0.6, len(nomes) - 0.2)
    elif g["tipo"] == "colunas":
        nomes = [b[0] for b in g["barras"]]
        vals = [b[1] for b in g["barras"]]
        cores = [OURO if b[2] else CINZA for b in g["barras"]]
        ax.bar(nomes, vals, color=cores, width=0.56)
        for x, v in enumerate(vals):
            ax.text(x, v + max(vals) * 0.02, brl(v), ha="center", fontsize=rot * 1.15, color=TINTA, fontweight="bold")
        ax.set_ylim(0, max(vals) * 1.16)
        ax.set_yticks([])
        ax.tick_params(axis="x", length=0, labelsize=rot, labelcolor=TINTA)
        ax.axhline(0, color=LINHA, lw=1.5)
    else:  # grupos: duas séries lado a lado, rótulo direto em cada barra
        n = len(g["grupos"])
        larg = 0.36
        maior = max(max(s[1]) for s in g["series"])
        for i, ((nome, vals), cor) in enumerate(zip(g["series"], (OURO, AZUL))):
            xs = [x + (i - 0.5) * (larg + 0.02) for x in range(n)]
            ax.bar(xs, vals, width=larg, color=cor, label=nome)
            for x, v in zip(xs, vals):
                ax.text(x, v + maior * 0.015, _mil(v), ha="center", fontsize=rot * (0.78 if n > 3 else 0.95),
                        color=TINTA)
        ax.set_xticks(range(n), g["grupos"])
        ax.set_ylim(0, maior * 1.18)
        ax.set_yticks([])
        ax.tick_params(axis="x", length=0, labelsize=rot, labelcolor=TINTA)
        ax.axhline(0, color=LINHA, lw=1.5)
        ax.legend(loc="upper left", frameon=False, fontsize=rot * 0.95, labelcolor=TINTA)
    if g.get("legenda"):
        fig.text(0.06, 1 - 1.55 / h, g["legenda"], fontsize=14.5 * k, color=TINTA_SUAVE, va="top", style="italic")

    fig.savefig(destino, dpi=100, facecolor=FUNDO)
    plt.close(fig)


def main() -> int:
    from PIL import Image

    repo = Repo()
    dados = dados_graficos(repo)
    SAIDA.mkdir(parents=True, exist_ok=True)
    for slug, g in dados.items():
        for recorte in RECORTES:
            png = SAIDA / f"{slug}-{recorte}.png"
            _desenhar(slug, g, recorte, png)
            # paleta reduzida: o gráfico tem poucas cores e o PNG fica com 20-30 KB (menor que WebP)
            Image.open(png).convert("RGB").quantize(colors=128).save(png, optimize=True)
        print(f"{slug}: {', '.join(RECORTES)}")
    (SAIDA / "dados.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
