"""Gera o pacote .zip para upload em hospedagem cPanel (Apache), pronto para public_html.

Conteúdo do zip (na raiz, para extrair direto em public_html/):
  index.html e pastas das páginas, 404.html, robots.txt, sitemap.xml, static/, .htaccess

Uso: python tools/build_cpanel.py --dominio https://www.seudominio.com.br
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dominio", required=True,
                        help="URL canônica com https://, ex.: https://www.seudominio.com.br ou https://dominio.com.br/subpasta")
    parser.add_argument("--saida", default=str(ROOT / "site-cpanel.zip"))
    args = parser.parse_args()

    url = urlparse(args.dominio.rstrip("/"))
    if url.scheme != "https" or not url.netloc:
        raise SystemExit("Informe a URL com https://. Ex.: https://www.seudominio.com.br")
    prefixo = url.path.rstrip("/")
    origem = f"https://{url.netloc}{prefixo}"
    os.environ["SITE_URL"] = origem

    from app import CSP, INDEXAVEL
    from tools.export_static import exportar

    build = ROOT / "build" / "public_html"
    paginas = exportar(build)
    (build / "_headers").unlink()  # formato Cloudflare Pages/Netlify; no Apache vale o .htaccess
    if prefixo:
        # Crawlers só leem /robots.txt na raiz do domínio; o da subpasta seria ignorado.
        (build / "robots.txt").unlink()

    htaccess = (ROOT / "deploy" / "htaccess.template").read_text(encoding="utf-8").format(
        origem=origem, host=url.netloc, host_regex=re.escape(url.netloc), prefixo=prefixo,
        csp=CSP, robots=INDEXAVEL)
    (build / ".htaccess").write_text(htaccess, encoding="utf-8", newline="\n")

    saida = Path(args.saida)
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        for arquivo in sorted(build.rglob("*")):
            if arquivo.is_file():
                zf.write(arquivo, arquivo.relative_to(build).as_posix())
    print(f"{len(paginas)} páginas · domínio {origem}\nZip: {saida} ({saida.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
