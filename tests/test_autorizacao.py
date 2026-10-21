"""Bloqueio de publicação: imóvel sem `publicacao_autorizada: true` não vai ao ar (rascunho)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from seo.content import DATA_DIR  # noqa: E402


def montar(tmp_path: Path, editar, limpar_guias: bool = True):
    """Cópia dos dados; `editar(lista_de_imoveis)` altera os registros in loco."""
    dados = tmp_path / "data"
    shutil.copytree(DATA_DIR, dados)
    arq = dados / "imoveis.json"
    imoveis = json.loads(arq.read_text(encoding="utf-8"))
    editar(imoveis)
    arq.write_text(json.dumps(imoveis, ensure_ascii=False), encoding="utf-8")
    if limpar_guias:  # guia que cita imóvel rascunho quebra o build de propósito; só o teste dele mantém o vínculo
        guias = dados / "artigos.json"
        artigos = json.loads(guias.read_text(encoding="utf-8"))
        for a in artigos:
            a["imoveis_relacionados"] = []
        guias.write_text(json.dumps(artigos, ensure_ascii=False), encoding="utf-8")
    app = create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def primeiro_ativo() -> str:
    imoveis = json.loads((DATA_DIR / "imoveis.json").read_text(encoding="utf-8"))
    return next(i["slug"] for i in imoveis if i["status"] == "ativo")


def rascunho(slug: str, valor):
    def editar(imoveis):
        for i in imoveis:
            if i["slug"] == slug:
                if valor == "AUSENTE":
                    i.pop("publicacao_autorizada", None)
                else:
                    i["publicacao_autorizada"] = valor
    return editar


@pytest.mark.parametrize("valor", ["AUSENTE", False, "true", 1, None])
def test_sem_autorizacao_nao_vai_ao_ar(tmp_path, valor):
    slug = primeiro_ativo()
    client, repo = montar(tmp_path, rascunho(slug, valor))
    path = f"/imoveis/{slug}/"
    assert client.get(path).status_code == 404
    assert slug not in [i["slug"] for i in repo.ativos()]
    assert path not in [p for p, _ in repo.paginas_indexaveis()]
    for url in ("/", "/imoveis/", "/sitemap.xml", "/llms.txt"):
        assert path not in client.get(url).get_data(as_text=True), url
    html = client.get(path).get_data(as_text=True)
    assert "rascunho" not in html.lower() and "autoriz" not in html.lower(), "a página não revela que existe rascunho"


def test_com_autorizacao_continua_no_ar(tmp_path):
    slug = primeiro_ativo()
    client, repo = montar(tmp_path, rascunho(slug, True))
    assert client.get(f"/imoveis/{slug}/").status_code == 200
    assert slug in [i["slug"] for i in repo.ativos()]


def test_vendido_com_ficha_sem_autorizacao_volta_a_ser_404(tmp_path):
    slug = primeiro_ativo()

    def editar(imoveis):
        for i in imoveis:
            if i["slug"] == slug:
                i.update(status="vendido", data_venda="2026-10-01")
                i.pop("publicacao_autorizada", None)

    client, repo = montar(tmp_path, editar)
    assert client.get(f"/imoveis/{slug}/").status_code == 404
    assert repo.encerrados() == []


def test_guia_que_cita_rascunho_falha_o_build_com_mensagem_clara(tmp_path):
    citado = primeiro_ativo()

    def editar(imoveis):
        rascunho(citado, False)(imoveis)
        guias = tmp_path / "data" / "artigos.json"
        artigos = json.loads(guias.read_text(encoding="utf-8"))
        artigos[0]["imoveis_relacionados"] = [citado]
        guias.write_text(json.dumps(artigos, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="publicacao_autorizada"):
        montar(tmp_path, editar, limpar_guias=False)


def test_carteira_vazia_nao_quebra_o_site(tmp_path):
    def editar(imoveis):
        for i in imoveis:
            i.pop("publicacao_autorizada", None)

    client, repo = montar(tmp_path, editar)
    assert repo.ativos() == []
    for path, _ in repo.paginas_indexaveis():
        assert client.get(path).status_code == 200, path
    assert "em atualização" in client.get("/imoveis/").get_data(as_text=True)
    assert "em atualização" in client.get("/").get_data(as_text=True)
    assert client.get("/sitemap.xml").status_code == 200 and client.get("/llms.txt").status_code == 200


def test_checklist_lista_rascunhos_sem_contar_como_pendencia(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "pre_publicacao.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0
    assert "Imóveis em rascunho (fora do site)" in r.stdout
    assert 'Imóveis ilustrativos na carteira' in r.stdout


def test_site_publicado_nao_tem_imovel_ilustrativo():
    """Demonstração só em tests/dados; data/imoveis.json leva apenas imóveis reais."""
    reais = json.loads((ROOT / "data" / "imoveis.json").read_text(encoding="utf-8"))
    assert not any(i.get("ilustrativo") for i in reais)
    demo = json.loads((ROOT / "tests" / "dados" / "imoveis.json").read_text(encoding="utf-8"))
    ativos = [i for i in demo if i["status"] == "ativo"]
    assert ativos and all(i["publicacao_autorizada"] is True and i["ilustrativo"] is True for i in ativos)
