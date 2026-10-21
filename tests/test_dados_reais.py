"""Só dado real: sem pessoas, sem métrica própria, sem vídeo provisório; dado técnico só com documento."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from seo.content import DATA_DIR  # noqa: E402

FICTICIOS = ("Helena Duarte", "Bruno Salles", "Marina Albuquerque", "Carolina Ribeiro", "CRECI-CE 0000",
             "CAU A000000", "OAB/CE 00", "284 transações", "R$ 1,6 bilhão", "desde 2011", "base interna",
             "Tempo médio de venda", "Desconto médio de negociação", "Valorização em 12 meses")


def grafo(html: str) -> list[dict]:
    bruto = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)[1]
    return json.loads(bruto.replace("<\\/", "</"))["@graph"]


def montar(tmp_path: Path, editar=None, origem: Path = DATA_DIR):
    dados = tmp_path / "data"
    shutil.copytree(origem, dados)
    if editar:
        editar(dados)
    app = create_app(data_dir=dados, bot_log=tmp_path / "b.jsonl")
    return app.test_client(), app.config["REPO"]


def test_site_publicado_sem_pessoa_nem_metrica_inventada(tmp_path):
    client, repo = montar(tmp_path, origem=ROOT / "data")
    assert not (ROOT / "data" / "especialistas.json").exists()
    for path, _ in repo.paginas_indexaveis():
        html = client.get(path).get_data(as_text=True)
        for ruim in FICTICIOS:
            assert ruim not in html, (path, ruim)
        assert not any(n["@type"] == "Person" for n in grafo(html)), path
        assert "SUBSTITUA" not in html, path


def test_bairro_sem_m2_do_sinduscon_falha_o_build(tmp_path):
    def editar(dados):
        arq = dados / "bairros.json"
        bairros = json.loads(arq.read_text(encoding="utf-8"))
        bairros.append({**bairros[0], "slug": "varjota", "nome": "Varjota", "em": "na Varjota", "de": "da Varjota"})
        arq.write_text(json.dumps(bairros, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="bairro 'varjota' sem preço do m²"):
        montar(tmp_path, editar)


def test_ficha_sem_dados_tecnicos_nao_inventa_medicao(tmp_path):
    """Imóvel real sem laudo (como o primeiro da carteira): a ficha só mostra o que tem documento."""
    slug = "apartamento-meireles-beira-mar-320m2"

    def editar(dados):
        arq = dados / "imoveis.json"
        imoveis = json.loads(arq.read_text(encoding="utf-8"))
        for i in imoveis:
            if i["slug"] == slug:
                for campo in ("tecnico", "amenidades", "especificacoes", "pavimentos", "videos"):
                    i.pop(campo, None)
        arq.write_text(json.dumps(imoveis, ensure_ascii=False), encoding="utf-8")

    client, repo = montar(tmp_path, editar)
    r = client.get(f"/imoveis/{slug}/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # campos estruturados (o texto livre da descrição é do anúncio e fica fora da checagem)
    dados = html.split('id="dados-principais"')[1].split('id="descricao"')[0]
    tabela_e_faq = html.split('id="ficha-tecnica"')[1].split('id="contato"')[0]
    for ausente in ("Rw ", "Blindagem", "kVA", "Medições técnicas", "Pavimentos", "Diferenciais do imóvel"):
        assert ausente not in dados and ausente not in tabela_e_faq, ausente
    nomes = {p["name"] for n in grafo(html) for p in n.get("additionalProperty", [])}
    assert not any("Rw" in n or "gerador" in n or "blindagem" in n for n in nomes)
    assert slug not in [i["slug"] for i in repo.com_dados_tecnicos()]
    # o card do catálogo também não mostra a linha técnica vazia
    catalogo = client.get("/imoveis/").get_data(as_text=True)
    card = catalogo.split(f'href="/imoveis/{slug}/"')[-1].split("</article>")[0]
    assert 'class="card__tec"' not in card


def test_home_nao_promete_especificacao_que_o_imovel_nao_tem(tmp_path):
    client, _ = montar(tmp_path)
    html = client.get("/").get_data(as_text=True)
    assert "Todos os imóveis da carteira têm" not in html
    assert "aparecem só quando há documento" in html


@pytest.mark.parametrize("n,esperado", [(0, "está em atualização"), (1, "1 imóvel à venda")])
def test_catalogo_com_zero_ou_um_imovel(tmp_path, n, esperado):
    def editar(dados):
        arq = dados / "imoveis.json"
        imoveis = [i for i in json.loads(arq.read_text(encoding="utf-8")) if i["status"] == "ativo"][:n]
        arq.write_text(json.dumps(imoveis, ensure_ascii=False), encoding="utf-8")

    client, repo = montar(tmp_path, editar)
    html = client.get("/imoveis/").get_data(as_text=True)
    assert esperado in html
    titulo = re.search(r"<title>(.*?)</title>", html)[1]
    assert titulo.endswith("Fortaleza" if n == 0 else "(1 oferta)"), titulo


def test_imovel_sem_preco_entra_com_o_que_chegou(tmp_path):
    """Decisão do dono (2026-10-21): cada imóvel entra com o material recebido; o que falta não aparece."""
    client, repo = montar(tmp_path, origem=ROOT / "data")
    sem_preco = [i for i in repo.ativos() if not i["preco"]]
    assert sem_preco, "a carteira real tem imóvel com preço sob consulta (Epic)"
    for i in sem_preco:
        html = client.get(i["path"]).get_data(as_text=True)
        corpo = html.split('<main id="conteudo"')[1].split("</main>")[0]
        assert "Sob consulta" in corpo and "None" not in corpo and "R$ 0" not in corpo
        assert "Quanto é o ITBI na compra" not in corpo  # sem preço não há ITBI calculado
        assert all(f'src="{f["src"]}"' in corpo for f in i["galeria"])
        oferta = next(n for n in grafo(html) if n["@type"] == "Offer")
        assert "price" not in oferta
        home = client.get("/").get_data(as_text=True)
        assert "Preço sob consulta" in home and i["galeria"][0]["src"] in home
