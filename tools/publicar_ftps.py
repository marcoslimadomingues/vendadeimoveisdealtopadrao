"""Publica build/public_html em uma pasta da hospedagem por FTPS (FTP sobre TLS) e remove órfãos.

Segurança:
  - credenciais só por variável de ambiente (FTP_HOST, FTP_USER, FTP_PASS) ou arquivo .ftp.env
    (ignorado pelo git); nunca no código;
  - a conexão exige TLS (FTP_TLS + PROT P); não há fallback para FTP puro;
  - remoção de arquivos remotos só acontece dentro de --remoto, que deve ficar sob /public_html/;
  - --simular lista o que seria enviado/removido sem alterar nada.

Uso:
  python tools/build_cpanel.py --dominio https://marcoslima.com.br/altopadrao
  python tools/publicar_ftps.py --remoto /public_html/altopadrao [--simular]
"""
from __future__ import annotations

import argparse
import ftplib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / "build" / "public_html"


def credenciais() -> dict[str, str]:
    cfg = {"FTP_HOST": "", "FTP_USER": "", "FTP_PASS": ""}
    arquivo = ROOT / ".ftp.env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, v = linha.split("=", 1)
                cfg[k.strip()] = v.strip()
    cfg.update({k: v for k, v in os.environ.items() if k in cfg and v})
    faltando = [k for k in ("FTP_HOST", "FTP_USER", "FTP_PASS") if not cfg[k]]
    if faltando:
        raise SystemExit(f"Credenciais ausentes: {', '.join(faltando)} (ambiente ou .ftp.env)")
    return cfg


def arvore(ftp: ftplib.FTP_TLS, d: str) -> tuple[list[str], list[str]]:
    arquivos, dirs = [], []
    for nome, fatos in ftp.mlsd(d):
        if nome in (".", ".."):
            continue
        caminho = f"{d}/{nome}"
        if fatos["type"] == "dir":
            dirs.append(caminho)
            a, s = arvore(ftp, caminho)
            arquivos += a
            dirs += s
        elif fatos["type"] == "file":
            arquivos.append(caminho)
    return arquivos, dirs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--remoto", required=True, help="pasta remota, ex.: /public_html/altopadrao")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--origem", default=str(LOCAL), help="pasta local a publicar (padrão: build/public_html)")
    args = ap.parse_args()

    remoto = "/" + args.remoto.strip("/")
    if not remoto.startswith("/public_html/") or remoto.count("/") < 2:
        raise SystemExit("--remoto deve ser uma subpasta de /public_html/ (ex.: /public_html/altopadrao)")
    origem = Path(args.origem)
    if not (origem / "index.html").exists():
        raise SystemExit(f"{origem} não existe ou não tem index.html: rode a build antes")

    locais = {f"{remoto}/{p.relative_to(origem).as_posix()}": p for p in origem.rglob("*") if p.is_file()}
    cfg = credenciais()
    ftp = ftplib.FTP_TLS(cfg["FTP_HOST"], timeout=60)
    ftp.login(cfg["FTP_USER"], cfg["FTP_PASS"])
    ftp.prot_p()

    try:
        remotos, dirs = arvore(ftp, remoto)
    except ftplib.error_perm:
        remotos, dirs = [], []
    orfaos = sorted(set(remotos) - set(locais))
    print(f"{len(locais)} arquivos a enviar · {len(orfaos)} órfão(s) a remover em {remoto}")
    if args.simular:
        for o in orfaos:
            print("  removeria:", o)
        ftp.quit()
        return 0

    criadas: set[str] = set()
    for destino, origem in sorted(locais.items()):
        atual = remoto
        for parte in destino[len(remoto) + 1:].split("/")[:-1]:
            atual += "/" + parte
            if atual not in criadas:
                try:
                    ftp.mkd(atual)
                except ftplib.error_perm as e:
                    if not str(e).startswith("550"):
                        raise
                criadas.add(atual)
        with origem.open("rb") as fh:
            ftp.storbinary(f"STOR {destino}", fh)
    for o in orfaos:
        assert o.startswith(remoto + "/")
        ftp.delete(o)
        print("  removido:", o)
    for d in sorted(dirs, key=len, reverse=True):
        if not any(x.startswith(d + "/") for x in locais):
            ftp.rmd(d)
            print("  pasta removida:", d)
    ftp.quit()
    print("publicado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
