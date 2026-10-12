"""Checklist de pré-publicação: procura dados provisórios que não podem ir para um domínio real.

Cobre o que dá para detectar por máquina (IDs de vídeo provisórios, domínios e perfis de exemplo,
telefone/CNPJ/CRECI zerados, imagens placeholder, og:image em SVG). O que exige julgamento humano
aparece no fim, em "Revisão manual".

Uso:
  python tools/pre_publicacao.py            # relatório; sai com 0
  python tools/pre_publicacao.py --estrito  # sai com 1 se houver pendência (use no CI de produção)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (descrição, arquivos, regex, por que importa)
VERIFICACOES = [
    ("Vídeos do YouTube com ID provisório", "data/*.json", r"SUBSTITUA\d+",
     "o player mostra 'vídeo indisponível' e o VideoObject do JSON-LD aponta para um vídeo inexistente"),
    ("E-mail/domínio de exemplo (.example)", "data/site.json", r"[\w.\-]+\.example\b",
     "contato, canonical e JSON-LD apontariam para um endereço inexistente"),
    ("Perfis sociais de exemplo (LinkedIn/YouTube/Instagram)", "data/*.json", r"https://[^\"\s]*exemplo[^\"\s]*",
     "sameAs com perfis falsos desfaz o ganho de E-E-A-T"),
    ("Telefone/WhatsApp provisórios", "data/site.json", r"\"(?:telefone|telefone_link|whatsapp)\": \"[^\"]*0000[^\"]*\"",
     "a barra WhatsApp/Ligar leva o visitante a um número que não existe"),
    ("CNPJ, CRECI, CAU ou OAB provisórios", "data/*.json",
     r"00\.000\.000/0001-00|CRECI-CE J-0000|CRECI-CE 0000[01]-F|CAU A000000-0|OAB/CE 00\.000",
     "registro profissional falso em página pública é risco jurídico e de reputação"),
    ("Endereço com número fictício", "data/site.json", r"\"rua\": \"[^\"]*0000\"",
     "o endereço entra no JSON-LD e no rodapé"),
    ("Imagens placeholder em uso", "data/*.json", r"/static/img/(?:imovel|artigo|pessoa)-placeholder\.svg",
     "o desenho aparece no lugar da foto do imóvel, da pessoa e na prévia ao compartilhar"),
    ("Aviso de dados ilustrativos no site.json", "data/site.json", r"DADOS ILUSTRATIVOS",
     "marcador de que o conteúdo ainda é de demonstração"),
    ("og:image em SVG (WhatsApp, Facebook e LinkedIn não exibem)", "templates/base.html", r"og-default\.svg",
     "o link compartilhado sai sem imagem; use PNG ou JPG de 1200×630"),
]

MANUAIS = [
    "Nomes, cargos, fotos e biografias das pessoas (hoje fictícios).",
    "Métricas da empresa: 284 transações, VGV, ticket médio, prazo médio de venda, fundação.",
    "Carteira de imóveis, preços, metragens e dados técnicos (laudos acústico, de blindagem e de gerador).",
    "Indicadores internos por bairro (m², valorização, liquidez): a base interna ilustrativa destoa do Sinduscon-CE.",
    "Textos tributários (ITBI, ITCD, ganho de capital, holding): revisão por advogado antes de publicar.",
    "Vídeos: gravar/publicar no YouTube e trocar os IDs; autorização de imagem das pessoas.",
    "Empreendimentos de terceiros citados (Wave Beira-Mar, Mansão Diogo, DM 210): só com dado verificado.",
    "LGPD: política de privacidade, base legal para WhatsApp/telefone e aviso de cookies, se houver medição.",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--estrito", action="store_true", help="sai com código 1 se houver pendência")
    args = ap.parse_args()

    pendencias = 0
    print("# Checklist de pré-publicação\n")
    for descricao, padrao_arquivos, regex, motivo in VERIFICACOES:
        achados: dict[str, int] = {}
        for arq in sorted(ROOT.glob(padrao_arquivos)):
            n = len(re.findall(regex, arq.read_text(encoding="utf-8")))
            if n:
                achados[arq.relative_to(ROOT).as_posix()] = n
        if achados:
            total = sum(achados.values())
            pendencias += 1
            print(f"✗ {descricao}: {total} ocorrência(s)")
            print(f"    por quê: {motivo}")
            for arq, n in achados.items():
                print(f"    - {arq}: {n}")
        else:
            print(f"✓ {descricao}")

    print("\n## Revisão manual (não detectável por máquina)")
    for item in MANUAIS:
        print(f"  [ ] {item}")

    print(f"\n{pendencias} verificação(ões) automática(s) com pendência de {len(VERIFICACOES)}.")
    return 1 if (args.estrito and pendencias) else 0


if __name__ == "__main__":
    sys.exit(main())
