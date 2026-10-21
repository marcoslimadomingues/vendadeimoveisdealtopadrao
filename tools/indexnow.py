"""Monta o aviso IndexNow (Bing, Yandex, Seznam...) com as URLs que mudaram desde a última publicação.

Compara o sitemap recém-compilado com o que estava no ar: entram URLs novas, URLs com lastmod diferente e
URLs que saíram do sitemap (removidas ou fora do índice, para o buscador ver o 404/noindex logo).
Com --tudo, ou sem sitemap anterior, avisa todas as URLs (primeira publicação com a chave).

    python tools/indexnow.py --novo build/pages/sitemap.xml [--anterior sitemap-no-ar.xml] [--tudo]

Imprime o JSON do POST para https://api.indexnow.org/indexnow, ou nada quando não há o que avisar ou o
site está em noindex (SITE_NOINDEX=1). A chave é o arquivo raiz/<chave>.txt, publicado na raiz do domínio.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
LIMITE = 10_000  # máximo de URLs por POST no protocolo


def chave(raiz: Path = ROOT / "raiz") -> str:
    """A chave IndexNow: raiz/<32 hex>.txt cujo conteúdo é o próprio nome."""
    achadas = [a for a in raiz.glob("*.txt")
               if re.fullmatch(r"[0-9a-f]{32}", a.stem) and a.read_text(encoding="utf-8").strip() == a.stem]
    if len(achadas) != 1:
        raise SystemExit(f"raiz/ deve ter exatamente um arquivo de chave IndexNow; achei {len(achadas)}")
    return achadas[0].stem


def ler_sitemap(texto: str) -> dict[str, str]:
    """loc → lastmod ('' quando ausente)."""
    raiz = ET.fromstring(texto)
    return {u.findtext("s:loc", namespaces=NS).strip(): (u.findtext("s:lastmod", namespaces=NS) or "").strip()
            for u in raiz.findall("s:url", NS)}


def mudancas(novo: dict[str, str], anterior: dict[str, str] | None) -> list[str]:
    if anterior is None:
        return list(novo)
    alteradas = [loc for loc, lastmod in novo.items() if anterior.get(loc) != lastmod]
    removidas = [loc for loc in anterior if loc not in novo]
    return alteradas + removidas


def payload(urls: list[str], k: str) -> dict:
    host = urlparse(urls[0]).netloc
    return {"host": host, "key": k, "keyLocation": f"https://{host}/{k}.txt", "urlList": urls[:LIMITE]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--novo", type=Path, required=True)
    ap.add_argument("--anterior", type=Path)
    ap.add_argument("--tudo", action="store_true")
    args = ap.parse_args()
    if os.environ.get("SITE_NOINDEX") == "1":
        return  # site em noindex: não chama o buscador para páginas que ele não pode indexar
    novo = ler_sitemap(args.novo.read_text(encoding="utf-8"))
    anterior = None
    if not args.tudo and args.anterior and args.anterior.is_file() and args.anterior.stat().st_size:
        try:
            anterior = ler_sitemap(args.anterior.read_text(encoding="utf-8"))
        except ET.ParseError:
            print("sitemap anterior ilegível: aviso todas as URLs", file=sys.stderr)
    urls = mudancas(novo, anterior)
    if urls:
        print(json.dumps(payload(urls, chave()), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
