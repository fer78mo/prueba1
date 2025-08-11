from typing import List, Tuple
from sentence_transformers import CrossEncoder

_model = None

def get_reranker():
    global _model
    if _model is None:
        _model = CrossEncoder("BAAI/bge-reranker-base", max_length=512)
    return _model

def rerank(query:str, candidates_texts:List[str])->List[Tuple[int,float]]:
    """
    Devuelve lista de (idx, score) ordenada desc.
    """
    if not candidates_texts:
        return []
    m = get_reranker()
    pairs = [[query, c] for c in candidates_texts]
    scores = m.predict(pairs).tolist()
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [(i, float(scores[i])) for i in order]
