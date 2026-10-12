"""Formatação pt-BR usada nos templates (valores sempre renderizados no servidor)."""
from __future__ import annotations

from datetime import date

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


def num(valor: float | int | None, casas: int = 0) -> str:
    if valor is None:
        return "—"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def brl(valor: float | int | None) -> str:
    return "—" if valor is None else f"R$ {num(round(valor))}"


def pct(valor: float | None, sinal: bool = False) -> str:
    if valor is None:
        return "—"
    prefixo = "+" if sinal and valor > 0 else ""
    return f"{prefixo}{num(valor, 1)}%"


def data_extenso(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def duracao_iso(iso: str) -> str:
    """PT14M20S -> 14 min 20 s"""
    corpo = iso.removeprefix("PT")
    partes, atual = [], ""
    for ch in corpo:
        if ch.isdigit():
            atual += ch
        else:
            partes.append(f"{atual} {dict(H='h', M='min', S='s')[ch]}")
            atual = ""
    return " ".join(partes)


def cap(texto: str) -> str:
    """Maiúscula só na primeira letra (preserva siglas e nomes próprios)."""
    return texto[:1].upper() + texto[1:]


def tel(texto: str) -> str:
    """Telefone sem quebra de linha (espaço e hífen não separáveis)."""
    return texto.replace(" ", " ").replace("-", "‑")


def register_filters(app) -> None:
    app.jinja_env.filters.update(
        num=num, brl=brl, pct=pct, cap=cap, tel=tel, data_extenso=data_extenso, duracao=duracao_iso
    )
