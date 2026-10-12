"""Auditoria de relevância semântica do conteúdo (espaço vetorial + densidade factual).

Para cada guia (Seção Outdoor) e cada imóvel (Seção Core), mede:
  - similaridade de cosseno entre cada parágrafo e a intenção da página (título + descrição);
  - similaridade entre cada parágrafo e o H2 da própria seção (coerência do nó conceitual);
  - densidade factual: parágrafos sem nenhum número (fatos pouco extraíveis por RAG);
  - adjetivos vagos que devem ser trocados por fatos ("incrível", "maravilhoso"...);
  - frases longas demais para extração de trechos (fraggles).

Backend padrão: TF-IDF (léxico, sem dependências). Com --modelo, usa embeddings
densos do sentence-transformers (semântico), ex.:
  pip install sentence-transformers
  python tools/semantic_audit.py --modelo sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

Uso: python tools/semantic_audit.py [--limiar 0.10] [--modelo NOME]
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from seo.content import Repo  # noqa: E402

STOPWORDS = set("""
a à ao aos as às com como da das de do dos e é em entre era essa esse esta este eu foi há isso
já mais mas na nas no nos o os ou para pela pelas pelo pelos por qual quando que se sem ser
seu sua são também tem têm um uma umas uns cada até após sobre sob pode podem está estão ter
""".split())
VAGOS = ["maravilhos", "incrível", "incriveis", "espetacular", "deslumbrante", "fantástic",
         "sensacional", "imperdível", "único", "única", "exclusivíssim", "sofisticad", "luxuos"]
MAX_PALAVRAS_FRASE = 40


def normalizar(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto)
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def tokens(texto: str) -> list[str]:
    palavras = re.findall(r"[a-z0-9]+", normalizar(texto))
    return [p.rstrip("s") if len(p) > 4 else p for p in palavras if p not in STOPWORDS and len(p) > 1]


class TfIdf:
    def __init__(self, documentos: list[str]):
        self.df = Counter()
        for doc in documentos:
            self.df.update(set(tokens(doc)))
        self.n = len(documentos)

    def vetor(self, texto: str) -> dict[str, float]:
        tf = Counter(tokens(texto))
        return {t: c * (math.log((1 + self.n) / (1 + self.df[t])) + 1) for t, c in tf.items()}

    def similaridade(self, a: str, b: str) -> float:
        va, vb = self.vetor(a), self.vetor(b)
        dot = sum(v * vb.get(t, 0.0) for t, v in va.items())
        na, nb = math.sqrt(sum(v * v for v in va.values())), math.sqrt(sum(v * v for v in vb.values()))
        return dot / (na * nb) if na and nb else 0.0


class Denso:
    def __init__(self, modelo: str):
        from sentence_transformers import SentenceTransformer, util
        self.m, self.util, self._cache = SentenceTransformer(modelo), util, {}

    def _emb(self, texto: str):
        limpo = re.sub(r"<[^>]+>", " ", texto)
        if limpo not in self._cache:
            self._cache[limpo] = self.m.encode(limpo, normalize_embeddings=True)
        return self._cache[limpo]

    def similaridade(self, a: str, b: str) -> float:
        return float(self.util.cos_sim(self._emb(a), self._emb(b)))


def unidades(repo: Repo):
    """(rótulo, intenção, [(h2, parágrafo)]) para cada página de conteúdo."""
    for a in repo.artigos_recentes():
        blocos = [("Resumo executivo", a["resumo"])]
        blocos += [(s["h2"], p) for s in a["secoes"] for p in s["paragrafos"]]
        blocos += [(f["q"], f["a"]) for f in a.get("faq", [])]
        yield a["path"], f"{a['titulo']}. {a['descricao']}", blocos
    for i in repo.ativos():
        blocos = [("Resumo", i["resumo"])] + [("Descrição", p) for p in i["paragrafos"]]
        blocos += [(f["q"], f["a"]) for f in i["faq"]]
        yield i["path"], f"{i['titulo']}. {i['resumo']}", blocos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limiar", type=float, default=0.10, help="similaridade mínima com a intenção da página")
    parser.add_argument("--modelo", help="modelo sentence-transformers para embeddings densos")
    args = parser.parse_args()

    repo = Repo()
    paginas = list(unidades(repo))
    corpus = [p for _, _, blocos in paginas for _, p in blocos]
    motor = Denso(args.modelo) if args.modelo else TfIdf(corpus)
    limiar = args.limiar if not args.modelo else max(args.limiar, 0.35)
    print(f"Backend: {'embeddings ' + args.modelo if args.modelo else 'TF-IDF'} · limiar {limiar:.2f}\n")

    alertas = 0
    for path, intencao, blocos in paginas:
        sims = [motor.similaridade(intencao, p) for _, p in blocos]
        print(f"{path}\n  similaridade média com a intenção: {sum(sims) / len(sims):.2f}")
        for (h2, p), sim in zip(blocos, sims):
            trecho = re.sub(r"<[^>]+>", "", p)[:70]
            avisos = []
            if sim < limiar:
                avisos.append(f"deriva semântica (cos={sim:.2f})")
            coesao = motor.similaridade(h2, p)
            if h2 not in ("Resumo", "Resumo executivo", "Descrição") and coesao < limiar / 2:
                avisos.append(f"parágrafo pouco ligado ao H2 (cos={coesao:.2f})")
            if not re.search(r"\d", p):
                avisos.append("sem dado numérico")
            vagos = [v for v in VAGOS if v in normalizar(p)]
            if vagos:
                avisos.append(f"adjetivo vago: {', '.join(vagos)}")
            longas = [f for f in re.split(r"(?<=[.!?])\s+", re.sub(r"<[^>]+>", "", p))
                      if len(f.split()) > MAX_PALAVRAS_FRASE]
            if longas:
                avisos.append(f"{len(longas)} frase(s) com mais de {MAX_PALAVRAS_FRASE} palavras")
            if avisos:
                alertas += 1
                print(f"  ! {trecho}…\n      {'; '.join(avisos)}")
        print()
    print(f"{len(paginas)} páginas auditadas · {alertas} parágrafo(s) com alerta")
    return 0


if __name__ == "__main__":
    sys.exit(main())
