"""Imagem 4:3 (1600×1200) da postagem semanal do radar no Perfil da Empresa no Google.

Lê postagens/<AAAA-MM-DD>/imagem.json e grava postagens/<AAAA-MM-DD>/imagem-4x3.png, na paleta dos gráficos
dos guias. Dois formatos:

  "tipo": "blocos"  até 3 números em destaque:
      {"rotulo": "Padrão elevado", "valor": "482", "unidade": "unidades lançadas", "destaque": "−32%",
       "atendido": true}
  "tipo": "barras"  barras horizontais, uma série (contagem ou valor por bairro):
      {"nome": "Meireles", "valor": 11, "atendido": true}

Campos comuns: "titulo", "subtitulo", "fonte" (obrigatórios) e "nota" (opcional, sob o subtítulo).
"atendido": true pinta de dourado (bairro atendido pelo site ou item principal); o resto fica cinza.

    python tools/postagem_radar.py 2026-10-26        (requer matplotlib)
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OURO, CINZA = "#b07a1c", "#9a948a"
TINTA, TINTA_SUAVE, LINHA, FUNDO = "#1c1a17", "#5f584e", "#e2dccf", "#ffffff"
ASSINATURA = "Alto Padrão Imóveis · vendadeimoveisdealtopadrao.com.br/radar"


def validar(spec: dict) -> list[str]:
    erros = [f"falta '{c}'" for c in ("titulo", "subtitulo", "fonte", "tipo") if not spec.get(c)]
    if spec.get("tipo") == "blocos":
        if not 1 <= len(spec.get("blocos", [])) <= 3:
            erros.append("'blocos' precisa de 1 a 3 itens")
        for b in spec.get("blocos", []):
            erros += [f"bloco sem '{c}'" for c in ("rotulo", "valor") if not b.get(c)]
    elif spec.get("tipo") == "barras":
        if not 2 <= len(spec.get("barras", [])) <= 10:
            erros.append("'barras' precisa de 2 a 10 itens")
        if any(not isinstance(b.get("valor"), (int, float)) for b in spec.get("barras", [])):
            erros.append("cada barra precisa de 'valor' numérico")
    else:
        erros.append("'tipo' deve ser 'blocos' ou 'barras'")
    return erros


def desenhar(spec: dict, saida: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle

    matplotlib.rcParams["text.parse_math"] = False  # "R$" é moeda, não fórmula
    fig = plt.figure(figsize=(16, 12), dpi=100, facecolor=FUNDO)
    fig.text(0.06, 0.93, spec["titulo"], fontsize=40, fontweight="bold", color=TINTA, va="top")
    fig.text(0.06, 0.865, spec["subtitulo"], fontsize=22, color=TINTA_SUAVE, va="top")
    if spec.get("nota"):
        fig.text(0.06, 0.82, spec["nota"], fontsize=17, color=TINTA_SUAVE, style="italic", va="top")
    topo = 0.78 if not spec.get("nota") else 0.76

    if spec["tipo"] == "blocos":
        n = len(spec["blocos"])
        gap = 0.04
        alt = min(0.19, (topo - 0.15 - gap * (n - 1)) / n)
        rend = fig.canvas.get_renderer()
        for i, b in enumerate(spec["blocos"]):
            y = topo - i * (alt + gap)
            cor = OURO if b.get("atendido") else CINZA
            fig.patches.append(FancyBboxPatch((0.06, y - alt), 0.88, alt, boxstyle="round,pad=0,rounding_size=0.008",
                                              transform=fig.transFigure, facecolor=FUNDO, edgecolor=LINHA, lw=2))
            fig.patches.append(Rectangle((0.06, y - alt), 0.012, alt, transform=fig.transFigure, facecolor=cor, lw=0))
            fig.text(0.10, y - 0.035, b["rotulo"], fontsize=24, color=TINTA_SUAVE, va="top")
            valor = fig.text(0.10, y - alt + 0.03, b["valor"], fontsize=58, fontweight="bold", color=TINTA,
                             va="bottom")
            if b.get("unidade"):
                fim = fig.transFigure.inverted().transform(valor.get_window_extent(rend))[1][0]
                fig.text(fim + 0.02, y - alt + 0.042, b["unidade"], fontsize=22, color=TINTA_SUAVE, va="bottom")
            if b.get("destaque"):
                fig.text(0.91, y - alt / 2, b["destaque"], fontsize=50, fontweight="bold", color=TINTA,
                         va="center", ha="right")
    else:
        barras = spec["barras"]
        ax = fig.add_axes([0.22, 0.18, 0.70, topo - 0.2])
        nomes = [b["nome"] for b in barras][::-1]
        valores = [b["valor"] for b in barras][::-1]
        cores = [OURO if b.get("atendido") else CINZA for b in barras][::-1]
        maximo = max(valores)
        for ret, v in zip(ax.barh(nomes, valores, color=cores, height=0.62), valores):
            rotulo = spec.get("formato_valor", "{}").format(v).replace(",", "X").replace(".", ",").replace("X", ".")
            ax.text(ret.get_width() + maximo * 0.015, ret.get_y() + ret.get_height() / 2, rotulo, va="center",
                    fontsize=24, color=TINTA)
        ax.set_xlim(0, maximo * 1.18)
        ax.tick_params(axis="y", labelsize=22, colors=TINTA, length=0)
        ax.set_xticks([])
        for lado in ("top", "right", "bottom"):
            ax.spines[lado].set_visible(False)
        ax.spines["left"].set_color(LINHA)

    fonte = textwrap.fill(spec["fonte"], width=125)
    fig.text(0.06, 0.07, fonte, fontsize=15, color=TINTA_SUAVE, va="bottom", linespacing=1.5)
    fig.text(0.06, 0.035, ASSINATURA, fontsize=15, color=OURO, va="bottom")
    fig.savefig(saida, facecolor=FUNDO)
    plt.close(fig)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    pasta = ROOT / "postagens" / sys.argv[1]
    spec = json.loads((pasta / "imagem.json").read_text(encoding="utf-8"))
    erros = validar(spec)
    if erros:
        raise SystemExit("imagem.json inválido:\n- " + "\n- ".join(erros))
    desenhar(spec, pasta / "imagem-4x3.png")
    print(pasta / "imagem-4x3.png")


if __name__ == "__main__":
    main()
