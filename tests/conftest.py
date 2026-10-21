"""Os testes rodam sobre uma cópia de data/ com a carteira de demonstração de tests/dados/imoveis.json.

O site publicado só tem imóveis reais (data/imoveis.json); os de demonstração existem para exercitar
ficha, preço, JSON-LD e ciclo de vida sem ir ao ar. SITE_DATA_DIR vale também para subprocessos (build).
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_dados = Path(tempfile.mkdtemp(prefix="dados-teste-")) / "data"
shutil.copytree(ROOT / "data", _dados)
shutil.copy(ROOT / "tests" / "dados" / "imoveis.json", _dados / "imoveis.json")
os.environ["SITE_DATA_DIR"] = str(_dados)
atexit.register(shutil.rmtree, _dados.parent, ignore_errors=True)
