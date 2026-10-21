"""Prepara as fotos de um imóvel para o site: nome descritivo, metadados removidos e tamanho de web.

Cada imóvel chega com o material que a construtora ou a imobiliária parceira mandar. Descreva as fotos
num JSON (a primeira é a capa, usada no cartão da home):

    {"slug": "apartamento-396m2-epic-condominium-meireles", "origem": "epic",
     "fotos": [{"arquivo": "Epic Condominium2.jpeg", "nome": "torre-epic-condominium-meireles",
                "alt": "Torre do Epic Condominium entre os prédios do Meireles"}]}

    python tools/fotos_imovel.py fotos.json        (requer Pillow)

Grava static/img/imoveis/<slug>/<nome>.jpg (no máximo 1600 px de largura, JPEG qualidade 82, sem EXIF/GPS)
e imprime a lista "galeria" pronta para colar no data/imoveis.json, com largura e altura de cada foto.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LARGURA_MAX = 1600


def main() -> None:
    from PIL import Image, ImageOps

    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    origem = (ROOT / spec["origem"]) if not Path(spec["origem"]).is_absolute() else Path(spec["origem"])
    destino = ROOT / "static" / "img" / "imoveis" / spec["slug"]
    destino.mkdir(parents=True, exist_ok=True)
    galeria = []
    for f in spec["fotos"]:
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", f["nome"]):
            raise SystemExit(f"nome '{f['nome']}': use só minúsculas, números e hífens")
        with Image.open(origem / f["arquivo"]) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")  # gira pela orientação e descarta EXIF/GPS
            if img.width > LARGURA_MAX:
                img = img.resize((LARGURA_MAX, round(img.height * LARGURA_MAX / img.width)), Image.LANCZOS)
            saida = destino / f"{f['nome']}.jpg"
            img.save(saida, "JPEG", quality=82, optimize=True, progressive=True)
            galeria.append({"src": f"/static/img/imoveis/{spec['slug']}/{saida.name}", "alt": f["alt"],
                            "w": img.width, "h": img.height})
    print(json.dumps(galeria, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
