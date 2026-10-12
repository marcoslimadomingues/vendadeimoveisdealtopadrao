"""Gera o pacote de redirecionamento 301 do endereço antigo para o domínio novo.

O pacote contém só um .htaccess (301 preservando caminho e query string) e um index.html de
reserva. Publique-o na pasta do endereço antigo para que links e buscas migrem para o domínio novo
sem duplicar conteúdo.

Uso:
  python tools/build_redirecionamento.py --destino https://vendadeimoveisdealtopadrao.com.br
"""
from __future__ import annotations

import argparse
import html
import shutil
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

HTACCESS = """# 301 permanente para {destino} (gerado por tools/build_redirecionamento.py)
Options -Indexes
DirectoryIndex index.html

<IfModule mod_rewrite.c>
RewriteEngine On
RewriteRule ^(.*)$ {destino}/$1 [R=301,L]
</IfModule>
"""

INDEX = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Endereço alterado</title>
<link rel="canonical" href="{destino}/">
<meta http-equiv="refresh" content="0; url={destino}/">
</head>
<body>
<p>Este endereço mudou. Acesse <a href="{destino}/">{destino_txt}</a>.</p>
</body>
</html>
"""


def validar(destino: str) -> str:
    u = urlparse(destino.rstrip("/"))
    if u.scheme != "https" or not u.netloc or u.path or u.query:
        raise SystemExit("--destino deve ser um domínio com https:// e sem caminho. Ex.: https://www.seudominio.com.br")
    return f"https://{u.netloc}"


def gerar(destino: str, saida: Path) -> Path:
    destino = validar(destino)
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    (saida / ".htaccess").write_text(HTACCESS.format(destino=destino), encoding="utf-8", newline="\n")
    (saida / "index.html").write_text(
        INDEX.format(destino=destino, destino_txt=html.escape(destino)), encoding="utf-8", newline="\n")
    return saida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--destino", required=True, help="domínio novo, com https://")
    ap.add_argument("--saida", default=str(ROOT / "build" / "redirecionamento"))
    args = ap.parse_args()
    pasta = gerar(args.destino, Path(args.saida))
    print(f"pacote de redirecionamento 301 para {validar(args.destino)} em {pasta}")


if __name__ == "__main__":
    main()
