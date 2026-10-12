"""Dados geográficos e mapa SVG da "Milha de ouro" (Beira Mar entre Meireles e Mucuripe).

Fonte única: OpenStreetMap (© colaboradores do OpenStreetMap, licença ODbL).
  baixar   consulta a API Overpass e grava os arquivos brutos em data/geo/raw/
  gerar    processa os brutos (offline) e grava data/geo/milha_de_ouro.json e
           static/img/mapa-milha-de-ouro.svg

Nada é estimado "de cabeça": extensão da faixa, posição ao longo da avenida, distâncias e
classificação das ruas são calculadas a partir da geometria do OpenStreetMap.

Uso:  python tools/mapa_milha_de_ouro.py gerar
"""
from __future__ import annotations

import argparse
import html
import json
import math
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "geo" / "raw"
EXTRATO = ROOT / "data" / "geo" / "milha_de_ouro.json"
SVG = ROOT / "static" / "img" / "mapa-milha-de-ouro.svg"
CONSULTA = "2026-10-12"

AREA = "(area(3605522152);area(3605522158);)->.a;"  # relações OSM: Meireles (5522152) e Mucuripe (5522158)
CONSULTAS = {
    "avenida": '[out:json][timeout:60];way["name"="Avenida Beira Mar"]["highway"](-3.745,-38.525,-3.700,-38.450);out geom;',
    "bairros": '[out:json][timeout:60];(relation["boundary"="administrative"]["name"~"^(Meireles|Mucuripe)$"]'
               '(-3.80,-38.60,-3.65,-38.40););out geom;',
    "costa": '[out:json][timeout:50];way["natural"="coastline"](-3.742,-38.520,-3.712,-38.472);out geom;',
    "pontos": f'[out:json][timeout:50];{AREA}(nwr["man_made"="lighthouse"](area.a);nwr["amenity"="marketplace"](area.a);'
              'nwr["leisure"~"^(marina|park|garden|stadium|fitness_station)$"]["name"](area.a);'
              'nwr["tourism"~"^(attraction|viewpoint|museum|gallery|artwork)$"]["name"](area.a);'
              'nwr["historic"]["name"](area.a);'
              'nwr["name"~"Feirinha|Iate|Mercado dos Peixes|Farol|Aterro|Beira Mar|Praia"]["highway"!~"."](area.a););out center;',
    "ruas": f'[out:json][timeout:60];{AREA}way["highway"~"^(primary|secondary|tertiary|residential|unclassified)$"]'
            '["name"](area.a);out geom;',
    "vizinhos": '[out:json][timeout:60];relation["boundary"="administrative"]["name"="Praia de Iracema"]'
                '(-3.76,-38.54,-3.70,-38.48);out geom;',
    "extras": '[out:json][timeout:50];(nwr["name"~"^(Iate Clube de Fortaleza|Farol do Mucuripe|Mercado dos Peixes|'
              'Porto do Mucuripe|Mercado de Peixes)"](-3.742,-38.520,-3.708,-38.462););out center;',
}
ENDPOINTS = ["https://z.overpass-api.de/api/interpreter", "https://lz4.overpass-api.de/api/interpreter"]

# Marcos de referência (nome no OpenStreetMap -> rótulo e tipo exibidos). Só entra o que existe no OSM.
MARCOS = {
    "Polo de Artesanato da Beira-Mar": ("Polo de Artesanato da Beira Mar (Feirinha)", "Feira de artesanato"),
    "Interceptor Oceânico": ("Interceptor Oceânico", "Monumento"),
    "Almirante Tamandaré": ("Memorial Almirante Tamandaré", "Memorial"),
    "Jardim Japonês Jusaku Fujita": ("Jardim Japonês Jusaku Fujita", "Parque"),
    "Anfiteatro da Beira Mar Flávio Ponte": ("Anfiteatro da Beira Mar Flávio Ponte", "Anfiteatro"),
    "Monumento ao Jangadeiro": ("Monumento ao Jangadeiro", "Monumento"),
    "Parque Bisão": ("Parque Bisão", "Parque"),
    "Praia do Meireles": ("Praia do Meireles", "Praia"),
    "Praia do Mucuripe": ("Praia do Mucuripe", "Praia"),
    "Mercado dos Peixes": ("Mercado dos Peixes", "Mercado"),
    "Iate Clube de Fortaleza": ("Iate Clube de Fortaleza", "Clube náutico"),
    "Acervo Mucuripe": ("Acervo Mucuripe", "Museu"),
}
# Ruas que sempre entram na lista (nome OSM), além das que cumprem o critério de extensão/classe.
BAIRROS_FAIXA = ("Meireles", "Mucuripe")  # a faixa só conta o que está nesses dois polígonos
ORDEM_BAIRROS = ("Praia de Iracema", "Meireles", "Mucuripe")  # vizinho primeiro: o polígono do Meireles o sobrepõe
VIEWPORT = {"lat0": -3.7300, "lat1": -3.7165, "lon0": -38.5135, "lon1": -38.4770, "largura": 1200}


# ------------------------------------------------------------------ download
def baixar() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for nome, consulta in CONSULTAS.items():
        dados = urllib.parse.urlencode({"data": consulta}).encode()
        resultado = None
        for ep in ENDPOINTS:
            for _ in range(2):
                try:
                    req = urllib.request.Request(ep, data=dados, headers={
                        "User-Agent": "altopadrao-mapa/1.0 (+https://marcoslima.com.br/altopadrao/)"})
                    with urllib.request.urlopen(req, timeout=70) as r:
                        resultado = json.loads(r.read().decode("utf-8"))
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"  {nome}: falhou {ep.split('/')[2]}: {exc!r:.80}")
                    time.sleep(3)
            if resultado:
                break
        if resultado is None:
            raise SystemExit(f"Sem dados para '{nome}'. Tente novamente mais tarde.")
        (RAW / f"{nome}.json").write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
        print(f"{nome}: {len(resultado.get('elements', []))} elementos")


# ------------------------------------------------------------------ geometria
def _k(lat: float) -> float:
    return math.cos(math.radians(lat))


def metros(p, q) -> float:
    """distância (m) entre dois pontos (lat, lon), projeção equiretangular local."""
    k = _k((p[0] + q[0]) / 2)
    return math.hypot((q[1] - p[1]) * k * 111320.0, (q[0] - p[0]) * 110540.0)


def dist_segmento(p, a, b) -> tuple[float, float]:
    """(distância em m de p ao segmento ab, parâmetro t em [0,1] do ponto mais próximo)."""
    k = _k(p[0])
    px, py = p[1] * k * 111320.0, p[0] * 110540.0
    ax, ay = a[1] * k * 111320.0, a[0] * 110540.0
    bx, by = b[1] * k * 111320.0, b[0] * 110540.0
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


def dentro(p, anel) -> bool:
    """ponto em polígono (ray casting)."""
    y, x = p
    d = False
    n = len(anel)
    for i in range(n):
        y1, x1 = anel[i]
        y2, x2 = anel[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            d = not d
    return d


def encadear(linhas):
    """junta polilinhas que compartilham extremidades (nós OSM compartilhados têm coordenada idêntica)."""
    restantes = [list(l) for l in linhas if len(l) > 1]
    cadeias = []
    while restantes:
        c = restantes.pop(0)
        mudou = True
        while mudou:
            mudou = False
            for i, l in enumerate(restantes):
                if l[0] == c[-1]:
                    c += l[1:]
                elif l[-1] == c[-1]:
                    c += l[::-1][1:]
                elif l[-1] == c[0]:
                    c = l[:-1] + c
                elif l[0] == c[0]:
                    c = l[::-1][:-1] + c
                else:
                    continue
                restantes.pop(i)
                mudou = True
                break
        cadeias.append(c)
    return sorted(cadeias, key=len, reverse=True)


def _geom(way) -> list[tuple[float, float]]:
    return [(p["lat"], p["lon"]) for p in way["geometry"]]


def _centro(e) -> tuple[float, float]:
    return (e["lat"], e["lon"]) if "lat" in e else (e["center"]["lat"], e["center"]["lon"])


def _carregar(nome: str) -> list[dict]:
    return json.loads((RAW / f"{nome}.json").read_text(encoding="utf-8")).get("elements", [])


# ------------------------------------------------------------------ processamento
def processar() -> dict:
    # polígonos dos bairros
    aneis: dict[str, list[tuple[float, float]]] = {}
    for rel in _carregar("bairros") + _carregar("vizinhos"):
        pedacos = [_geom(m) for m in rel["members"] if m.get("role") == "outer" and m.get("geometry")]
        cadeias = encadear(pedacos)
        fechados = [c for c in cadeias if c[0] == c[-1]]
        aneis[rel["tags"]["name"]] = max(fechados or cadeias, key=len)

    def bairro_de(p) -> str | None:
        return next((n for n in ORDEM_BAIRROS if n in aneis and dentro(p, aneis[n])), None)

    def na_faixa(p) -> bool:
        return bairro_de(p) in BAIRROS_FAIXA

    # eixo da Beira Mar (oeste -> leste)
    vias = [_geom(w) for w in _carregar("avenida") if w["tags"].get("highway") in ("primary", "tertiary")]
    cadeias = encadear(vias)
    eixo: list[tuple[float, float]] = []
    for c in sorted(cadeias, key=lambda c: min(p[1] for p in c)):
        c = c if c[0][1] <= c[-1][1] else c[::-1]
        eixo += c
    cum = [0.0]
    for i in range(1, len(eixo)):
        cum.append(cum[-1] + metros(eixo[i - 1], eixo[i]))

    def posicao(p) -> tuple[float, float]:
        """(distância m até o eixo, posição m ao longo do eixo)."""
        melhor = (1e12, 0.0)
        for i in range(len(eixo) - 1):
            d, t = dist_segmento(p, eixo[i], eixo[i + 1])
            if d < melhor[0]:
                melhor = (d, cum[i] + t * (cum[i + 1] - cum[i]))
        return melhor

    # faixa = trecho do eixo dentro de Meireles ∪ Mucuripe
    idx = [i for i, p in enumerate(eixo) if na_faixa(p)]
    i0, i1 = idx[0], idx[-1]
    inicio_m = cum[i0]
    extensao_m = cum[i1] - cum[i0]

    # ruas: extensão dentro da faixa de bairros, distância ao eixo, toque na avenida
    ruas: dict[str, dict] = {}
    for w in _carregar("ruas"):
        g = _geom(w)
        nome = w["tags"]["name"]
        if nome == "Avenida Beira Mar":
            continue
        r = ruas.setdefault(nome, {"classes": set(), "len": 0.0, "dmin": 1e12, "ds": [], "pt": None})
        r["classes"].add(w["tags"]["highway"])
        for a, b in zip(g, g[1:]):
            meio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if na_faixa(meio):
                r["len"] += metros(a, b)
        for p in g:
            if not na_faixa(p):
                continue
            d, pos = posicao(p)
            r["ds"].append(d)
            if d < r["dmin"]:
                r["dmin"], r["pt"] = d, (p, pos)
    rotulo_classe = {"primary": "via arterial", "secondary": "via coletora", "tertiary": "via coletora",
                     "residential": "via local", "unclassified": "via local"}
    ordem = ["primary", "secondary", "tertiary", "residential", "unclassified"]
    transversais, paralelas = [], []
    for nome, r in ruas.items():
        if r["pt"] is None or r["len"] < 250:
            continue
        classe = rotulo_classe[min(r["classes"], key=ordem.index)]
        principal = min(r["classes"], key=ordem.index) in ("primary", "secondary", "tertiary")
        item = {"nome": nome, "classe": classe, "extensao_m": round(r["len"] / 10) * 10,
                "distancia_m": round(r["dmin"] / 10) * 10}
        mediana = sorted(r["ds"])[len(r["ds"]) // 2]
        if r["dmin"] <= 15 and r["len"] <= 2000:
            (p, pos) = r["pt"]
            if principal or r["len"] >= 700:
                item.update(km=round((pos - inicio_m) / 1000, 1), bairro=bairro_de(p))
                transversais.append(item)
        elif mediana <= 450 and (principal or r["len"] >= 1200):
            item["distancia_m"] = round(mediana / 10) * 10  # distância típica (mediana dos nós na faixa)
            paralelas.append(item)
    transversais.sort(key=lambda x: x["km"])
    paralelas.sort(key=lambda x: (x["distancia_m"], -x["extensao_m"]))

    # marcos de referência
    candidatos = {}
    for e in _carregar("pontos") + _carregar("extras"):
        nome = e.get("tags", {}).get("name")
        if nome in MARCOS:
            p = _centro(e)
            d, pos = posicao(p)
            # prefere o ponto mais próximo da avenida quando há homônimos
            if nome not in candidatos or d < candidatos[nome][0]:
                candidatos[nome] = (d, pos, p)
    pontos = []
    for nome, (d, pos, p) in candidatos.items():
        rotulo, tipo = MARCOS[nome]
        proximo = min(eixo[i0:i1 + 1], key=lambda q: metros(p, q))  # trecho da faixa mais próximo
        pontos.append({"nome": rotulo, "tipo": tipo, "km": round((pos - inicio_m) / 1000, 1),
                       "distancia_m": round(d / 10) * 10, "bairro": bairro_de(p) or bairro_de(proximo),
                       "_p": p, "_pos": pos})
    pontos.sort(key=lambda x: x["_pos"])
    for n, p in enumerate(pontos, start=1):
        p["n"] = n

    centro = (sum(p[0] for p in eixo[i0:i1 + 1]) / (i1 - i0 + 1), sum(p[1] for p in eixo[i0:i1 + 1]) / (i1 - i0 + 1))
    dados = {
        "fonte": "OpenStreetMap", "licenca": "ODbL", "consulta": CONSULTA,
        "extensao_km": round(extensao_m / 1000, 1),
        "inicio": {"bairro": bairro_de(eixo[i0]), "lat": round(eixo[i0][0], 4), "lon": round(eixo[i0][1], 4)},
        "fim": {"bairro": bairro_de(eixo[i1]), "lat": round(eixo[i1][0], 4), "lon": round(eixo[i1][1], 4)},
        "centro_aprox": {"lat": round(centro[0], 3), "lon": round(centro[1], 3)},
        "transversais": transversais, "paralelas": paralelas,
        "pontos": [{k: v for k, v in p.items() if not k.startswith("_")} for p in pontos],
        "mapa": {"largura": dimensoes()[0], "altura": dimensoes()[1]},
    }
    return {"dados": dados, "aneis": aneis, "eixo": eixo, "pontos": pontos, "i0": i0, "i1": i1}


# ------------------------------------------------------------------ mapa SVG
def dimensoes() -> tuple[int, int]:
    v = VIEWPORT
    largura_m = (v["lon1"] - v["lon0"]) * 111320.0 * _k((v["lat0"] + v["lat1"]) / 2)
    s = v["largura"] / largura_m
    return v["largura"], round((v["lat1"] - v["lat0"]) * 110540.0 * s)


def desenhar(ctx: dict) -> str:
    v = VIEWPORT
    largura_m = (v["lon1"] - v["lon0"]) * 111320.0 * _k((v["lat0"] + v["lat1"]) / 2)
    s = v["largura"] / largura_m
    H = round((v["lat1"] - v["lat0"]) * 110540.0 * s)
    W = v["largura"]
    kk = _k((v["lat0"] + v["lat1"]) / 2)

    def xy(p):
        return ((p[1] - v["lon0"]) * 111320.0 * kk * s, (v["lat1"] - p[0]) * 110540.0 * s)

    def d_path(linha, fechar=False):
        pts = [xy(p) for p in linha]
        txt = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        return txt + ("Z" if fechar else "")

    # mar: costa encadeada + cantos ao norte
    costa = encadear([_geom(w) for w in _carregar("costa")])[0]
    if costa[0][1] > costa[-1][1]:
        costa = costa[::-1]
    mar = costa + [(v["lat1"] + 0.01, costa[-1][1]), (v["lat1"] + 0.01, costa[0][1])]

    partes = []
    partes.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
                  f'aria-labelledby="t d" font-family="system-ui,Segoe UI,Roboto,Arial,sans-serif">')
    partes.append("<title id=\"t\">Mapa da milha de ouro de Fortaleza: Avenida Beira Mar entre o Meireles e o Mucuripe</title>")
    partes.append(f'<desc id="d">Mapa esquemático com os bairros Meireles e Mucuripe, a Avenida Beira Mar '
                  f'({ctx["dados"]["extensao_km"]} km na faixa), as ruas e os marcos numerados. '
                  f'Dados do OpenStreetMap, consulta em {CONSULTA}.</desc>')
    partes.append(f'<defs><clipPath id="c"><rect width="{W}" height="{H}"/></clipPath>'
                  f'<path id="eixo" d="{d_path(ctx["eixo"])}"/></defs>')
    partes.append(f'<rect width="{W}" height="{H}" fill="#f7f4ee"/>')
    partes.append('<g clip-path="url(#c)">')
    partes.append(f'<path d="{d_path(mar, True)}" fill="#cfdde3"/>')
    cores = {"Meireles": "#efe6d6", "Mucuripe": "#e4d4b4", "Praia de Iracema": "#ebe9e4"}
    for nome, anel in ctx["aneis"].items():
        partes.append(f'<path d="{d_path(anel, True)}" fill="{cores.get(nome, "#eee")}" stroke="#b9a57f" '
                      f'stroke-width="1.2" stroke-dasharray="5 4"/>')
    # ruas (traço fino) e eixo
    ruas_d = []
    for w in _carregar("ruas"):
        if w["tags"]["name"] == "Avenida Beira Mar":
            continue
        ruas_d.append(d_path(_geom(w)))
    partes.append(f'<path d="{" ".join(ruas_d)}" fill="none" stroke="#cdc4b2" stroke-width="1"/>')
    partes.append('<use href="#eixo" fill="none" stroke="#ffffff" stroke-width="8" stroke-linecap="round"/>')
    partes.append('<use href="#eixo" fill="none" stroke="#8a6a3b" stroke-width="4.5" stroke-linecap="round"/>')
    partes.append('</g>')

    # rótulos
    def centroide(anel):
        xs = [xy(p) for p in anel]
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(xs, xs[1:] + xs[:1]):
            f = x0 * y1 - x1 * y0
            a += f
            cx += (x0 + x1) * f
            cy += (y0 + y1) * f
        return (cx / (3 * a), cy / (3 * a)) if a else xs[0]

    for nome, anel in ctx["aneis"].items():
        x, _ = centroide(anel)
        y = H * 0.76  # dentro do recorte, abaixo da orla
        if nome in BAIRROS_FAIXA:
            partes.append(f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="middle" font-size="26" font-weight="700" '
                          f'letter-spacing="3" fill="#8a6a3b" opacity=".8">{html.escape(nome.upper())}</text>')
        else:  # bairro vizinho, só contexto
            partes.append(f'<text x="10" y="{y:.0f}" text-anchor="start" font-size="14" '
                          f'letter-spacing="1" fill="#8a8578">{html.escape(nome.upper())}</text>')
    partes.append(f'<text x="{W * 0.5:.0f}" y="38" text-anchor="middle" font-size="20" letter-spacing="4" '
                  f'fill="#6e8794">OCEANO ATLÂNTICO</text>')
    partes.append('<text font-size="17" font-weight="700" fill="#5f4a26" stroke="#fff" stroke-width="4" '
                  'paint-order="stroke"><textPath href="#eixo" startOffset="9%">Avenida Beira Mar</textPath></text>')

    # marcos numerados (desloca verticalmente quando se sobrepõem)
    ocupados: list[tuple[float, float]] = []
    for p in ctx["pontos"]:
        x, y = xy(p["_p"])
        while any(abs(x - ox) < 31 and abs(y - oy) < 31 for ox, oy in ocupados):
            y += 31
        ocupados.append((x, y))
        partes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="#1c1a17" stroke="#fff" stroke-width="3"/>'
                      f'<text x="{x:.1f}" y="{y + 5.8:.1f}" text-anchor="middle" font-size="17" font-weight="700" '
                      f'fill="#fff">{p["n"]}</text>')

    # escala (500 m), norte e atribuição
    barra = 500 * s
    partes.append(f'<g transform="translate(24 {H - 52})"><rect width="{barra:.0f}" height="6" fill="#1c1a17"/>'
                  f'<text y="22" font-size="12" fill="#1c1a17">500 m</text></g>')
    partes.append(f'<g transform="translate({W - 40} 60)"><path d="M0 0 L8 22 L0 17 L-8 22Z" fill="#1c1a17"/>'
                  f'<text y="40" text-anchor="middle" font-size="13" font-weight="700" fill="#1c1a17">N</text></g>')
    partes.append(f'<text x="{W - 12}" y="{H - 12}" text-anchor="end" font-size="11" fill="#5f584e">'
                  f'Dados: © colaboradores do OpenStreetMap (ODbL) · consulta em 12/10/2026</text>')
    partes.append("</svg>")
    return "\n".join(partes)


def gerar() -> None:
    ctx = processar()
    EXTRATO.write_text(json.dumps(ctx["dados"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SVG.parent.mkdir(parents=True, exist_ok=True)
    SVG.write_text(desenhar(ctx), encoding="utf-8")
    d = ctx["dados"]
    print(f"faixa: {d['extensao_km']} km de {d['inicio']['bairro']} a {d['fim']['bairro']}")
    print(f"transversais: {len(d['transversais'])} · paralelas: {len(d['paralelas'])} · marcos: {len(d['pontos'])}")
    print(f"mapa: {SVG} ({SVG.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=["baixar", "gerar"])
    args = ap.parse_args()
    baixar() if args.acao == "baixar" else gerar()
