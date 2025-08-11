# app/retrieve/lexical.py
import re
from rank_bm25 import BM25Okapi

_word = re.compile(r"\w+", re.UNICODE)

def _tokenize(text:str):
    if not text:
        return []
    return _word.findall(text.lower())

class BM25Lexical:
    def __init__(self, texts:list[str]):
        self.texts = texts
        self.corpus = [_tokenize(t) for t in texts]
        self.model = BM25Okapi(self.corpus)

    def rank(self, query:str, top_k:int=20):
        q = _tokenize(query)
        scores = self.model.get_scores(q)
        # devuelve índices ordenados + puntuaciones
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return order, [scores[i] for i in order]

def rrf_fuse(rankings:list[list[int]], k:int=60, top_k:int=20):
    """
    rankings: lista de listas de índices (posición en la lista candidata).
    Implementa Reciprocal Rank Fusion sobre una *misma* lista de candidatos.
    """
    from collections import defaultdict
    agg = defaultdict(float)
    for r in rankings:
        for rank, idx in enumerate(r, start=1):
            agg[idx] += 1.0 / (k + rank)
    fused = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
    return [idx for idx, _ in fused][:top_k]
