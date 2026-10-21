"""Exporta o site como HTML5 puro pré-renderizado em dist/ (hospedagem estática / CDN).

Cada URL vira dist/<path>/index.html, com o mesmo HTML e JSON-LD servidos pelo
Flask. O 404.html é exportado para que Nginx, Cloudflare Pages ou Netlify
respondam HTTP 404 real a URLs inexistentes e a imóveis vendidos.

Uso: python tools/export_static.py [--saida dist] [--site-url https://www.dominio.com.br]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HEADERS_CDN = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Language: pt-BR
  Content-Security-Policy: {csp}
  X-Robots-Tag: {robots}
  Cache-Control: public, max-age=300, s-maxage=600

/static/*
  Cache-Control: public, max-age=86400
"""


def exportar(saida: Path) -> list[str]:
    from app import CSP, create_app, valor_robots

    app = create_app(bot_log=Path(tempfile.gettempdir()) / "export_bot_log.jsonl")
    client = app.test_client()
    repo = app.config["REPO"]

    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    gerados = []

    todas = [p for p, _ in repo.paginas_indexaveis()] + repo.paginas_redirecionadas()
    for path in todas:
        resp = client.get(path)
        if resp.status_code != 200:
            raise SystemExit(f"{path} respondeu {resp.status_code}; exportação abortada")
        destino = saida / path.strip("/") / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(resp.data)
        gerados.append(path)

    for arquivo in ("robots.txt", "sitemap.xml", "llms.txt"):
        (saida / arquivo).write_bytes(client.get(f"/{arquivo}").data)

    resp_404 = client.get("/__pagina-inexistente__/")
    assert resp_404.status_code == 404
    (saida / "404.html").write_bytes(resp_404.data)

    shutil.copytree(ROOT / "static", saida / "static")
    # raiz/: arquivos de verificação (Bing, Google, IndexNow) servidos na raiz do domínio, sem alteração
    for arq in sorted((ROOT / "raiz").glob("*")):
        if arq.is_file():
            shutil.copy(arq, saida / arq.name)
    # _headers: formato aceito por Cloudflare Pages e Netlify.
    (saida / "_headers").write_text(HEADERS_CDN.format(csp=CSP, robots=valor_robots()), encoding="utf-8")
    return gerados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saida", default=str(ROOT / "dist"))
    parser.add_argument("--site-url", help="sobrescreve base_url de data/site.json")
    args = parser.parse_args()
    if args.site_url:
        os.environ["SITE_URL"] = args.site_url
    gerados = exportar(Path(args.saida))
    print(f"{len(gerados)} páginas + robots.txt + sitemap.xml + 404.html exportados em {args.saida}")


if __name__ == "__main__":
    main()
