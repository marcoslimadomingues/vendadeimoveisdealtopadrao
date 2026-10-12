"""Domínio, modo noindex, GitHub Pages e política de segurança do repositório."""
from __future__ import annotations

import json
import os
import re
from html import unescape
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from app import CSP, CSP_META, NAO_INDEXAVEL, create_app, valor_robots  # noqa: E402

DOMINIO = "https://vendadeimoveisdealtopadrao.com.br"


def build_pages(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env_extra or {})}
    env.pop("SITE_URL", None)
    return subprocess.run([sys.executable, str(ROOT / "tools" / "build_pages.py"), *args],
                          capture_output=True, text=True, env=env)


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


def test_csp_tambem_vai_em_meta_porque_o_pages_nao_tem_cabecalhos(tmp_path):
    c = create_app(bot_log=tmp_path / "b.jsonl").test_client()
    for path in ("/", "/imoveis/", "/nao-existe/"):
        html = c.get(path).get_data(as_text=True)
        m = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html)
        assert m and unescape(m.group(1)) == CSP_META, path  # o navegador decodifica &#39; antes de aplicar
    assert "script-src 'none'" in CSP_META and "frame-ancestors" not in CSP_META and "frame-ancestors" in CSP


def test_build_para_pages_na_raiz_do_dominio(tmp_path):
    saida = tmp_path / "pages"
    r = build_pages("--dominio", DOMINIO, "--saida", str(saida), env_extra={"SITE_NOINDEX": "0"})
    assert r.returncode == 0, r.stderr
    assert (saida / "index.html").is_file() and (saida / "404.html").is_file()
    assert (saida / "CNAME").read_text().strip() == "vendadeimoveisdealtopadrao.com.br"
    assert (saida / "robots.txt").is_file() and (saida / "sitemap.xml").is_file()
    assert not (saida / "_headers").exists() and not (saida / ".htaccess").exists()
    home = (saida / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{DOMINIO}/">' in home and 'href="/imoveis/"' in home
    assert f"<loc>{DOMINIO}/milha-de-ouro-fortaleza/</loc>" in (saida / "sitemap.xml").read_text(encoding="utf-8")


def test_build_para_pages_em_subcaminho_prefixa_links(tmp_path):
    saida = tmp_path / "pages"
    url = "https://marcoslimadomingues.github.io/vendadeimoveisdealtopadrao"
    r = build_pages("--dominio", url, "--saida", str(saida))
    assert r.returncode == 0, r.stderr
    home = (saida / "index.html").read_text(encoding="utf-8")
    assert 'href="/vendadeimoveisdealtopadrao/imoveis/"' in home
    assert 'href="/vendadeimoveisdealtopadrao/static/css/style.css' in home
    assert not (saida / "CNAME").exists() and not (saida / "robots.txt").exists()


@pytest.mark.parametrize("ruim", ["http://x.com.br", "vendadeimoveis.com.br", ""])
def test_build_pages_recusa_url_invalida(tmp_path, ruim):
    assert build_pages("--dominio", ruim, "--saida", str(tmp_path / "p")).returncode != 0


def test_workflow_publica_so_na_main_e_so_com_pages_ativo():
    wf = (ROOT / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8")
    site, publicar = wf.split("\n  publicar:\n")
    assert "pull_request:" in wf
    assert "secrets." not in wf, "o site é publicado sem segredos"
    assert "github.event_name != 'pull_request'" in publicar and "pages_ativo == 'true'" in publicar
    assert "pages: write" in publicar and "pages: write" not in site
    assert "actions/deploy-pages@v4" in publicar and "actions/upload-pages-artifact@v3" in site
    assert "SITE_NOINDEX" in site and "EXIGIR_DADOS_REAIS" in publicar
    assert "permissions:\n  contents: read" in wf


def test_sem_resquicios_de_hospedagem_antiga():
    versionado = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split()
    for nome in ("tools/publicar_ftps.py", "tools/build_cpanel.py", "tools/coletar_logs.py",
                 "deploy/htaccess.template", ".ftp.env.exemplo"):
        assert nome not in versionado, nome
    wf = (ROOT / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8")
    assert "FTP" not in wf and "marcoslima.com.br/altopadrao" not in wf


def test_dependabot_e_politica_de_seguranca():
    dep = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert 'package-ecosystem: "pip"' in dep and 'package-ecosystem: "github-actions"' in dep
    seg = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Report a vulnerability" in seg and "@" not in seg, "sem e-mail pessoal na política pública"
