"""Prepara uma ilustração gerada por IA para um guia: recortes 16:9, 4:3 e 1:1 em JPEG, marcados como IA.

- Corta ao centro e grava static/img/guias/<slug>-16x9.jpg (1600×900), -4x3.jpg e -1x1.jpg (sem ampliar).
- Remove os metadados do arquivo de origem e grava só o XMP IPTC DigitalSourceType
  "trainedAlgorithmicMedia", a marcação que o Google lê para imagem gerada por IA.
- O texto alternativo e a legenda ficam em data/artigos.json (imagem_alt, imagem_legenda, imagem_ia: true).

Uso: python tools/ilustracao_guia.py <arquivo de origem> <slug do guia>      (requer Pillow)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAIDA = ROOT / "static" / "img" / "guias"
IA = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
XMP = (
    '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    '<rdf:Description rdf:about="" xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">'
    f"<Iptc4xmpExt:DigitalSourceType>{IA}</Iptc4xmpExt:DigitalSourceType>"
    '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>'
).encode("utf-8")
RECORTES = {"16x9": (16, 9, 1600), "4x3": (4, 3, None), "1x1": (1, 1, None)}  # None: sem redimensionar


def recortar(img, rw: int, rh: int):
    w, h = img.size
    if w / h > rw / rh:  # mais larga: corta as laterais
        nw = round(h * rw / rh)
        x = (w - nw) // 2
        return img.crop((x, 0, x + nw, h))
    nh = round(w * rh / rw)
    y = (h - nh) // 2
    return img.crop((0, y, w, y + nh))


def preparar(origem: Path, slug: str) -> list[Path]:
    from PIL import Image

    img = Image.open(origem).convert("RGB")
    gerados = []
    for nome, (rw, rh, largura) in RECORTES.items():
        r = recortar(img, rw, rh)
        if largura and r.width > largura:
            r = r.resize((largura, round(largura * rh / rw)), Image.Resampling.LANCZOS)
        destino = SAIDA / f"{slug}-{nome}.jpg"
        r.save(destino, "JPEG", quality=80, optimize=True, progressive=True, xmp=XMP)
        gerados.append(destino)
    return gerados


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    origem, slug = Path(sys.argv[1]), sys.argv[2]
    SAIDA.mkdir(parents=True, exist_ok=True)
    for arq in preparar(origem, slug):
        print(f"{arq.relative_to(ROOT).as_posix()}  {arq.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
