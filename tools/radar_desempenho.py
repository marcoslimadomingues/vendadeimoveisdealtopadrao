"""Desempenho das edições do radar no Google: quais podem sair do índice.

No Search Console: Desempenho > Resultados da pesquisa > últimos 3 meses > Exportar > CSV. O zip traz
"Páginas.csv" (ou "Pages.csv"). Passe esse arquivo:

    python tools/radar_desempenho.py Páginas.csv [--semanas 8] [--min-impressoes 1] [--hoje AAAA-MM-DD]

Edição com pelo menos --semanas de idade e menos de --min-impressoes no período é candidata a sair do
índice: marque "indexar": false no data/radar.json. A página continua no ar (noindex, follow) e no
índice do radar; só sai do sitemap e da busca. Edição nova não entra na conta: o Google ainda nem a
avaliou.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COLUNA_PAGINA = ("Páginas principais", "Top pages", "Página", "Page")
COLUNA_IMPRESSOES = ("Impressões", "Impressions")
COLUNA_CLIQUES = ("Cliques", "Clicks")


def _coluna(cabecalho: list[str], nomes: tuple[str, ...]) -> str:
    for nome in nomes:
        if nome in cabecalho:
            return nome
    raise SystemExit(f"CSV sem a coluna {nomes[0]!r}: exporte o relatório de páginas do Search Console")


def _numero(texto: str) -> int:
    return int(texto.replace(".", "").replace(",", "").strip() or 0)


def ler_csv(arquivo: Path) -> dict[str, tuple[int, int]]:
    """path → (impressões, cliques). Aceita o CSV em português ou inglês."""
    with arquivo.open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        cab = leitor.fieldnames or []
        pag, imp, cli = (_coluna(cab, COLUNA_PAGINA), _coluna(cab, COLUNA_IMPRESSOES),
                         _coluna(cab, COLUNA_CLIQUES))
        return {urlparse(linha[pag]).path: (_numero(linha[imp]), _numero(linha[cli])) for linha in leitor}


def avaliar(repo, dados: dict[str, tuple[int, int]], hoje: date, semanas: int, min_impressoes: int) -> list[dict]:
    linhas = []
    for e in repo.radar_edicoes():
        idade = (hoje - date.fromisoformat(e["publicado"])).days // 7
        impressoes, cliques = dados.get(e["path"], (0, 0))
        if e.get("indexar") is False:
            situacao = "fora do índice"
        elif idade < semanas:
            situacao = "nova demais para avaliar"
        elif impressoes < min_impressoes:
            situacao = "candidata a sair do índice"
        else:
            situacao = "manter"
        linhas.append({"slug": e["slug"], "idade": idade, "impressoes": impressoes, "cliques": cliques,
                       "situacao": situacao})
    return linhas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--semanas", type=int, default=8)
    ap.add_argument("--min-impressoes", type=int, default=1)
    ap.add_argument("--hoje", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()

    from seo.content import Repo

    linhas = avaliar(Repo(), ler_csv(args.csv), args.hoje, args.semanas, args.min_impressoes)
    print(f"{'edição':<12} {'semanas':>7} {'impressões':>10} {'cliques':>7}  situação")
    for l in linhas:
        print(f"{l['slug']:<12} {l['idade']:>7} {l['impressoes']:>10} {l['cliques']:>7}  {l['situacao']}")
    candidatas = [l["slug"] for l in linhas if l["situacao"] == "candidata a sair do índice"]
    if candidatas:
        print(f"\nPara tirar do índice, acrescente \"indexar\": false em: {', '.join(candidatas)}")


if __name__ == "__main__":
    main()
