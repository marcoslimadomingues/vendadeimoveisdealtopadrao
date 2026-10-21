"""Gera o site estático para o GitHub Pages em build/pages.

Domínio próprio na raiz:   python tools/build_pages.py --dominio https://vendadeimoveisdealtopadrao.com.br
Endereço do GitHub Pages:  python tools/build_pages.py --dominio https://<usuario>.github.io/<repositorio>

Saída: uma pasta com index.html em cada rota, 404.html (o Pages responde HTTP 404 com ele), sitemap.xml,
static/ e, se o domínio não tiver caminho, robots.txt e CNAME. O GitHub Pages não aplica .htaccess nem
cabeçalhos próprios: a política de segurança vai em <meta http-equiv>, e noindex em <meta name="robots">.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dominio", required=True, help="URL final do site, com https://")
    ap.add_argument("--saida", default=str(ROOT / "build" / "pages"))
    args = ap.parse_args()

    url = urlparse(args.dominio.rstrip("/"))
    if url.scheme != "https" or not url.netloc:
        raise SystemExit("Informe a URL com https://. Ex.: https://www.seudominio.com.br")
    prefixo = url.path.rstrip("/")
    os.environ["SITE_URL"] = f"https://{url.netloc}{prefixo}"

    from app import valor_robots
    from tools.export_static import exportar

    saida = Path(args.saida)
    paginas = exportar(saida)
    (saida / "_headers").unlink(missing_ok=True)  # formato de Netlify/Cloudflare; o Pages não usa
    if prefixo:
        (saida / "robots.txt").unlink(missing_ok=True)  # só valem na raiz do domínio
        (saida / "llms.txt").unlink(missing_ok=True)
        for arq in (ROOT / "raiz").glob("*"):  # verificação de buscadores também só vale na raiz
            (saida / arq.name).unlink(missing_ok=True)
    else:
        (saida / "CNAME").write_text(url.netloc + "\n", encoding="utf-8")

    modo = "noindex" if valor_robots().startswith("noindex") else "indexável"
    print(f"{len(paginas)} páginas · {os.environ['SITE_URL']} · {modo} · {saida}")


if __name__ == "__main__":
    main()
