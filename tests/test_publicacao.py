"""Domínio, modo noindex e pacote de redirecionamento."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from app import NAO_INDEXAVEL, create_app, valor_robots  # noqa: E402

DOMINIO = "https://vendadeimoveisdealtopadrao.com.br"


def test_dominio_padrao_do_site():
    base = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))["base_url"]
    assert base == DOMINIO


def test_indexavel_por_padrao(tmp_path, monkeypatch):
    monkeypatch.delenv("SITE_NOINDEX", raising=False)
    monkeypatch.delenv("SITE_URL", raising=False)
    c = create_app(bot_log=tmp_path / "b.jsonl").test_client()
    r = c.get("/")
    html = r.get_data(as_text=True)
    assert f'<link rel="canonical" href="{DOMINIO}/">' in html
    assert re.search(r'<meta name="robots" content="index, follow', html)
    assert r.headers["X-Robots-Tag"].startswith("index, follow")
    assert f"Sitemap: {DOMINIO}/sitemap.xml" in c.get("/robots.txt").get_data(as_text=True)


def test_modo_noindex_cobre_meta_e_cabecalho(tmp_path, monkeypatch):
    monkeypatch.setenv("SITE_NOINDEX", "1")
    c = create_app(bot_log=tmp_path / "b.jsonl").test_client()
    for path in ("/", "/imoveis/", "/milha-de-ouro-fortaleza/", "/imoveis/cobertura-duplex-mucuripe-480m2/"):
        r = c.get(path)
        assert r.status_code == 200
        assert f'<meta name="robots" content="{NAO_INDEXAVEL}">' in r.get_data(as_text=True), path
        assert r.headers["X-Robots-Tag"] == NAO_INDEXAVEL, path
    assert valor_robots() == NAO_INDEXAVEL


def test_htaccess_do_build_segue_o_modo(monkeypatch):
    monkeypatch.setenv("SITE_NOINDEX", "1")
    assert valor_robots() == "noindex, nofollow"
    monkeypatch.setenv("SITE_NOINDEX", "0")
    assert valor_robots().startswith("index, follow")


def test_pacote_de_redirecionamento(tmp_path):
    import build_redirecionamento as br

    pasta = br.gerar(DOMINIO + "/", tmp_path / "redir")
    ht = (pasta / ".htaccess").read_text(encoding="utf-8")
    assert f"RewriteRule ^(.*)$ {DOMINIO}/$1 [R=301,L]" in ht
    idx = (pasta / "index.html").read_text(encoding="utf-8")
    assert f'rel="canonical" href="{DOMINIO}/"' in idx and f'url={DOMINIO}/' in idx
    assert sorted(p.name for p in pasta.iterdir()) == [".htaccess", "index.html"]


@pytest.mark.parametrize("ruim", ["http://x.com.br", "vendadeimoveis.com.br", "https://x.com.br/pasta", ""])
def test_redirecionamento_recusa_destino_invalido(ruim):
    import build_redirecionamento as br

    with pytest.raises(SystemExit):
        br.validar(ruim)


def test_workflow_nao_adivinha_pasta_nem_publica_sem_segredos():
    wf = (ROOT / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8")
    assert "FTP_REMOTO: ${{ vars.FTP_REMOTO }}" in wf, "pasta de destino vem só da variável, sem valor padrão"
    assert "publicação ignorada" in wf
    assert "SITE_NOINDEX" in wf and "EXIGIR_DADOS_REAIS" in wf
    assert "Marcote" not in wf and "FTP_PASS: ${{ secrets.FTP_PASS }}" in wf
