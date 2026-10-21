"""Postagens do Perfil da Empresa (postagens/<edição>/): cada uma pertence a uma edição do radar, cabe no
limite do Google, não tem telefone e tem a imagem descrita num imagem.json válido."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.postagem_radar import validar  # noqa: E402

PASTAS = sorted(p for p in (ROOT / "postagens").glob("*") if p.is_dir())
EDICOES = {e["slug"] for e in json.loads((ROOT / "data" / "radar.json").read_text(encoding="utf-8"))}


@pytest.mark.parametrize("pasta", PASTAS, ids=lambda p: p.name)
def test_postagem_valida(pasta):
    assert pasta.name in EDICOES, f"{pasta.name} não é edição do radar"
    texto = (pasta / "postagem.md").read_text(encoding="utf-8")
    corpo = texto.split("\n\n", 1)[1]  # depois do cabeçalho Tipo/Botão/Imagem
    assert len(corpo) <= 1500, "o Google aceita até 1.500 caracteres"
    assert not re.search(r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}", corpo), "o Google reprova postagem com telefone"
    assert f"/radar/{pasta.name}/" in texto
    assert validar(json.loads((pasta / "imagem.json").read_text(encoding="utf-8"))) == []


def test_validar_aponta_spec_incompleta():
    assert "falta 'fonte'" in validar({"tipo": "blocos", "titulo": "t", "subtitulo": "s", "blocos": [
        {"rotulo": "r", "valor": "1"}]})
    assert any("1 a 3" in e for e in validar({"tipo": "blocos", "titulo": "t", "subtitulo": "s", "fonte": "f",
                                              "blocos": []}))
    assert any("numérico" in e for e in validar({"tipo": "barras", "titulo": "t", "subtitulo": "s", "fonte": "f",
                                                 "barras": [{"nome": "a", "valor": "1"}, {"nome": "b", "valor": 2}]}))
