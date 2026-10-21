"""IndexNow: chave publicada na raiz e aviso só das URLs que mudaram desde a última publicação."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from tools.indexnow import chave, ler_sitemap, mudancas, payload  # noqa: E402

BASE = "https://vendadeimoveisdealtopadrao.com.br"


def sitemap(urls: dict[str, str]) -> str:
    itens = "".join(f"<url><loc>{BASE}{p}</loc><lastmod>{d}</lastmod></url>" for p, d in urls.items())
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{itens}</urlset>'


def test_chave_publicada_na_raiz_do_dominio(tmp_path):
    k = chave()
    r = create_app(bot_log=tmp_path / "b.jsonl").test_client().get(f"/{k}.txt")
    assert r.status_code == 200 and r.get_data(as_text=True).strip() == k


def test_avisa_novas_alteradas_e_removidas_e_ignora_iguais():
    anterior = ler_sitemap(sitemap({"/": "2026-10-12", "/guias/": "2026-10-12", "/radar/2026-10-01/": "2026-10-01"}))
    novo = ler_sitemap(sitemap({"/": "2026-10-21", "/guias/": "2026-10-12", "/radar/2026-10-19/": "2026-10-19"}))
    assert sorted(mudancas(novo, anterior)) == sorted(
        [f"{BASE}/", f"{BASE}/radar/2026-10-19/", f"{BASE}/radar/2026-10-01/"])
    assert mudancas(novo, None) == list(novo)  # primeira vez: tudo


def test_payload_aponta_a_chave_no_mesmo_host():
    p = payload([f"{BASE}/"], "a" * 32)
    assert p == {"host": "vendadeimoveisdealtopadrao.com.br", "key": "a" * 32,
                 "keyLocation": f"{BASE}/{'a' * 32}.txt", "urlList": [f"{BASE}/"]}


def test_cli_em_noindex_nao_avisa_nada(tmp_path):
    arq = tmp_path / "sitemap.xml"
    arq.write_text(sitemap({"/": "2026-10-21"}), encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "tools" / "indexnow.py"), "--novo", str(arq)]
    fora = subprocess.run(cmd, capture_output=True, text=True, env={"SITE_NOINDEX": "1", "SYSTEMROOT": "C:\\Windows"})
    assert fora.returncode == 0 and fora.stdout == ""
    dentro = subprocess.run(cmd, capture_output=True, text=True, env={"SITE_NOINDEX": "0", "SYSTEMROOT": "C:\\Windows"})
    assert json.loads(dentro.stdout)["urlList"] == [f"{BASE}/"]
