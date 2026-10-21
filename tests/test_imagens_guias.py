"""Gráficos dos guias de dados: batem com os números atuais, têm os 3 recortes e aparecem na página."""
from __future__ import annotations

import json
import re
import shutil
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from app import create_app  # noqa: E402
from seo.content import DATA_DIR  # noqa: E402

GUIAS = ("preco-m2-por-bairro-fortaleza", "preco-m2-beira-mar", "meireles-ou-mucuripe-investir",
         "itbi-fortaleza-imoveis-alto-padrao", "itcd-ceara-imoveis")
DIMENSOES = {"16x9": (1600, 900), "4x3": (1600, 1200), "1x1": (1200, 1200)}
PASTA = ROOT / "static" / "img" / "guias"


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    app = create_app(bot_log=tmp_path_factory.mktemp("l") / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def tamanho_png(arq: Path) -> tuple[int, int]:
    cab = arq.read_bytes()[:24]
    assert cab[:8] == b"\x89PNG\r\n\x1a\n", arq.name
    return struct.unpack(">II", cab[16:24])


def test_graficos_batem_com_os_dados_atuais(ctx):
    """Se falhar: os números mudaram (Sinduscon, ITBI, ITCD). Rode `python tools/imagens_guias.py`."""
    from imagens_guias import dados_graficos

    _, repo = ctx
    atual = json.loads(json.dumps(dados_graficos(repo), ensure_ascii=False))
    manifesto = json.loads((PASTA / "dados.json").read_text(encoding="utf-8"))
    assert manifesto == atual


@pytest.mark.parametrize("slug", GUIAS)
def test_tres_recortes_nas_dimensoes_do_google(slug):
    for recorte, esperado in DIMENSOES.items():
        assert tamanho_png(PASTA / f"{slug}-{recorte}.png") == esperado, (slug, recorte)
        assert (PASTA / f"{slug}-{recorte}.png").stat().st_size < 80_000


@pytest.mark.parametrize("slug", GUIAS)
def test_guia_mostra_o_grafico_e_declara_os_recortes(ctx, slug):
    client, repo = ctx
    a = repo.artigos[slug]
    html = client.get(a["path"]).get_data(as_text=True)
    figura = html.split('<figure class="artigo__imagem">')[1].split("</figure>")[0]
    alt = re.search(r'alt="([^"]+)"', figura)[1]
    assert f'src="/static/img/guias/{slug}-16x9.png"' in figura and "{" not in alt and "R$" in alt
    assert "<figcaption>" in figura and "Fonte" in figura
    artigo = next(n for n in grafo(html) if n["@type"] == "Article")
    assert [i["url"].rsplit("-", 1)[1] for i in artigo["image"]] == ["16x9.png", "4x3.png", "1x1.png"]
    assert re.search(rf'<meta property="og:image" content="[^"]+/{slug}-16x9\.png">', html)


def tamanho_jpeg(arq: Path) -> tuple[int, int]:
    b = arq.read_bytes()
    i = 2
    while i < len(b):
        marca, comp = b[i + 1], struct.unpack(">H", b[i + 2:i + 4])[0]
        if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC):  # SOFn
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + comp
    raise AssertionError(f"{arq.name}: sem cabeçalho SOF")


def test_todos_os_guias_tem_imagem_propria(ctx):
    _, repo = ctx
    assert not any("placeholder" in a["imagem"] for a in repo.artigos.values())


def test_ilustracoes_de_ia_marcadas_no_arquivo_na_legenda_e_no_json_ld(ctx):
    client, repo = ctx
    ilustrados = [a for a in repo.artigos.values() if a.get("imagem_ia")]
    assert len(ilustrados) == 7
    for a in ilustrados:
        jpg = PASTA / f"{a['slug']}-16x9.jpg"
        assert tamanho_jpeg(jpg) == (1600, 900), a["slug"]
        for recorte, (rw, rh) in (("4x3", (4, 3)), ("1x1", (1, 1))):
            w, h = tamanho_jpeg(PASTA / f"{a['slug']}-{recorte}.jpg")
            assert abs(w / h - rw / rh) < 0.01 and w >= 900, (a["slug"], recorte)
        for recorte in ("16x9", "4x3", "1x1"):
            arq = PASTA / f"{a['slug']}-{recorte}.jpg"
            assert b"trainedAlgorithmicMedia" in arq.read_bytes(), arq.name
            assert arq.stat().st_size < 400_000, arq.name
        html = client.get(a["path"]).get_data(as_text=True)
        figura = html.split('<figure class="artigo__imagem">')[1].split("</figure>")[0]
        assert "gerada por inteligência artificial" in figura and 'alt="Ilustração de ' in figura
        artigo = next(n for n in grafo(html) if n["@type"] == "Article")
        assert all(i["creditText"] == "Ilustração gerada por inteligência artificial" for i in artigo["image"])


def test_indexacao_so_com_liberacao_do_responsavel():
    """Checklist zerado não basta: o noindex só sai com indexacao_liberada: true no site.json."""
    import subprocess

    site = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "pre_publicacao.py"), "--estrito"],
                       capture_output=True, text=True, encoding="utf-8")
    if site["indexacao_liberada"] is not True:
        assert r.returncode == 1 and "✗ Indexação ainda não liberada pelo responsável" in r.stdout


def test_imagem_inexistente_falha_o_build(tmp_path):
    dados = tmp_path / "data"
    shutil.copytree(DATA_DIR, dados)
    arq = dados / "artigos.json"
    artigos = json.loads(arq.read_text(encoding="utf-8"))
    artigos[0]["imagem"] = "/static/img/guias/nao-existe-16x9.png"
    arq.write_text(json.dumps(artigos, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="não existe em static/"):
        create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")
