import re
from typing import List, Dict, Tuple
from app.vector.embeddings import embed_texts
from app.io.alias_loader import load_alias

_stop = set("""
de del la el los las y en para por con una uno un le lo al a o u que se su sus
""".split())

_cache = {"alias": None, "law_vecs": None, "law_tokens": None}

def _law_tokenize(name:str)->set:
    toks = re.findall(r"[a-záéíóúñ]{3,}", name.lower())
    return set(t for t in toks if t not in _stop)

def _ensure_cache():
    if _cache["alias"] is None:
        alias = load_alias("/app/data/articulos/alias.txt")
        names = [alias[k] for k in alias.keys()]
        vecs = embed_texts(names)
        toks = {k: _law_tokenize(v) for k,v in alias.items()}
        _cache.update({"alias": alias, "law_vecs": dict(zip(alias.keys(), vecs)), "law_tokens": toks})

def shortlist_laws(query:str, top_n:int=5)->List[Tuple[str, float]]:
    """
    Devuelve [(ley_id, score)] combinando similitud semántica con alias y solapamiento léxico.
    """
    _ensure_cache()
    qv = embed_texts([query])[0]
    qtoks = _law_tokenize(query)
    results=[]
    # cosine = dot porque normalizamos embeddings
    for lid, lv in _cache["law_vecs"].items():
        cos = sum(a*b for a,b in zip(qv, lv))
        lex = len(qtoks & _cache["law_tokens"][lid]) / (len(qtoks) or 1)
        score = 0.75*cos + 0.25*lex
        results.append((lid, float(score)))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]
