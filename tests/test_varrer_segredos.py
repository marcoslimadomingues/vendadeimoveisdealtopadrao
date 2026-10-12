"""O scanner acha segredos (inclusive no histórico), mascara valores e ignora placeholders."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import varrer_segredos as vs  # noqa: E402

# valores montados em tempo de execução: o arquivo de teste não contém nenhum literal que pareça segredo
AWS = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
GH = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
SENHA = "Xk9" + "!pQ2" + "mZ7vLw"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t.t", *args],
                   check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "config.php").write_text(f"<?php\n$aws = '{AWS}';\ndefine('DB_PASSWORD', '{SENHA}');\n", encoding="utf-8")
    (tmp_path / ".env").write_text(f"TOKEN={GH}\n", encoding="utf-8")
    (tmp_path / "clientes.txt").write_text("Maria 111.444.777-35\nFulano 111.111.111-11\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text('password = "your-password-here"\napi_key = os.environ["K"]\n', encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "inicial")
    git(tmp_path, "rm", "-q", ".env")  # apagado do disco, mas continua no histórico
    git(tmp_path, "commit", "-q", "-m", "remove env")
    return tmp_path


def test_cpf_valido():
    assert vs.cpf_valido("111", "444", "777", "35")
    assert not vs.cpf_valido("111", "111", "111", "11")


def test_acha_segredos_no_arquivo_atual_e_no_historico(repo):
    r = vs.varrer(str(repo))
    por_regra = {a["regra"]: a for a in r["achados"]}
    assert r["commits"] == 2

    assert por_regra["aws-access-key"]["atual"] is True
    assert por_regra["wp-define"]["sev"] == "media"
    assert por_regra["cpf"]["valor"] == "1 CPFs", "só o CPF com dígitos verificadores corretos conta"

    env = por_regra["arquivo-sensivel"]
    assert env["valor"] == ".env" and env["atual"] is False, ".env removido deve aparecer como 'só no histórico'"
    assert por_regra["github-token"]["atual"] is False
    assert not any("your-password" in a["valor"] for a in r["achados"]), "placeholder não é segredo"


def test_relatorio_mascara_os_valores(repo):
    texto = vs.formatar({"teste": vs.varrer(str(repo))})
    for segredo in (AWS, GH, SENHA):
        assert segredo not in texto
    assert "SÓ NO HISTÓRICO" in texto and "no arquivo atual" in texto
    assert vs.mascarar("mysql://usuario:segredo123@host/db") == "mysql://usuario:***@host/db"
