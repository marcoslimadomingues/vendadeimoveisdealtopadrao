"""Rotina diária de captura de Access Logs da hospedagem cPanel para o diretório publicado.

1. Conecta por FTPS (TLS) e baixa os arquivos mensais que o cPanel mantém em ~/logs
   (<dominio>-ssl_log-<Mês>-<Ano>.gz e <dominio>-<Mês>-<Ano>.gz), atualizados 1x por dia.
2. Extrai só as requisições ao diretório do site (padrão: o domínio inteiro), sem duplicar linhas.
3. Acumula em logs/servidor/raiz.log (formato combined) — histórico local permanente,
   mesmo depois que o cPanel descarta arquivos antigos.
4. Gera o relatório de varredura (tools/bot_report.py) em logs/servidor/relatorio-AAAA-MM-DD.md.

Credenciais (nunca no código): variáveis FTP_HOST, FTP_USER, FTP_PASS ou arquivo .ftp.env na
raiz do projeto (ignorado pelo git), uma variável por linha: FTP_PASS=...

Uso:  python tools/coletar_logs.py [--dominio vendadeimoveisdealtopadrao.com.br] [--prefixo /subpasta] [--meses 2]
Agendamento diário no Windows: deploy/agendar_coleta_logs.cmd
"""
from __future__ import annotations

import argparse
import ftplib
import gzip
import io
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DESTINO = ROOT / "logs" / "servidor"
REQUISICAO = re.compile(r'"\S+ (\S+)')


def credenciais() -> dict[str, str]:
    cfg = {"FTP_HOST": "", "FTP_USER": "", "FTP_PASS": ""}
    arquivo = ROOT / ".ftp.env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                chave, valor = linha.split("=", 1)
                cfg[chave.strip()] = valor.strip()
    cfg.update({k: v for k, v in os.environ.items() if k in cfg and v})
    faltando = [k for k in ("FTP_HOST", "FTP_USER", "FTP_PASS") if not cfg[k]]
    if faltando:
        raise SystemExit(f"Credenciais ausentes: {', '.join(faltando)} (defina no ambiente ou em .ftp.env)")
    return cfg


def meses_recentes(n: int) -> list[str]:
    hoje = date.today()
    ano, mes = hoje.year, hoje.month
    rotulos = []
    for _ in range(n):
        rotulos.append(f"{MESES[mes - 1]}-{ano}")
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    return rotulos


def baixar(cfg: dict, dominio: str, meses: list[str]) -> list[str]:
    ftp = ftplib.FTP_TLS(cfg["FTP_HOST"], timeout=120)
    ftp.login(cfg["FTP_USER"], cfg["FTP_PASS"])
    ftp.prot_p()
    disponiveis = set(ftp.nlst("/logs"))
    linhas: list[str] = []
    for mes in meses:
        for nome in (f"{dominio}-ssl_log-{mes}.gz", f"{dominio}-{mes}.gz"):
            remoto = f"/logs/{nome}"
            if remoto not in disponiveis and nome not in disponiveis:
                continue
            buf = io.BytesIO()
            ftp.retrbinary(f"RETR {remoto}", buf.write)
            texto = gzip.decompress(buf.getvalue()).decode("utf-8", "replace")
            linhas += texto.splitlines()
            print(f"  {nome}: {buf.tell() // 1024} KB")
    ftp.quit()
    return linhas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dominio", default="vendadeimoveisdealtopadrao.com.br")
    parser.add_argument("--prefixo", default="", help="subpasta publicada; vazio = raiz do domínio")
    parser.add_argument("--meses", type=int, default=2, help="meses de arquivo a baixar (padrão: atual e anterior)")
    parser.add_argument("--dias", type=int, default=30, help="janela do relatório")
    args = parser.parse_args()

    prefixo = args.prefixo.rstrip("/")
    DESTINO.mkdir(parents=True, exist_ok=True)
    acumulado = DESTINO / f"{prefixo.strip('/') or 'raiz'}.log"

    print(f"Baixando logs de {args.dominio} ({', '.join(meses_recentes(args.meses))})")
    brutas = baixar(credenciais(), args.dominio, meses_recentes(args.meses))

    def do_site(linha: str) -> bool:
        m = REQUISICAO.search(linha)
        return bool(m) and (m.group(1) == prefixo or m.group(1).startswith(prefixo + "/"))

    existentes = set(acumulado.read_text(encoding="utf-8").splitlines()) if acumulado.exists() else set()
    novas = [linha for linha in brutas if do_site(linha) and linha not in existentes]
    if novas:
        with acumulado.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(novas) + "\n")
    print(f"{len(brutas)} linhas no servidor · {len(novas)} novas de {prefixo}/ · "
          f"{len(existentes) + len(novas)} no histórico ({acumulado})")

    if not acumulado.exists():
        print("Ainda não há acessos ao diretório nos logs arquivados (o cPanel processa 1x por dia).")
        return 0
    relatorio = DESTINO / f"relatorio-{date.today():%Y-%m-%d}.md"
    return subprocess.call([sys.executable, str(ROOT / "tools" / "bot_report.py"), "--combined", str(acumulado),
                            "--prefixo", prefixo, "--dias", str(args.dias), "--saida", str(relatorio),
                            "--csv", str(DESTINO / "varredura.csv")])


if __name__ == "__main__":
    sys.exit(main())
