import os
import re
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.vector.embeddings import embed_texts
from app.io.alias_loader import load_alias
from app.core.utils import read_text  # <— para leer ruta_origen cuando haga falta

# ---- BM25 opcional ----------------------------------------------------------
try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except Exception:
    BM25Okapi = None  # type: ignore
    _HAS_BM25 = False

USE_BM25 = (os.getenv("USE_BM25_FUSION", "true").lower() == "true") and _HAS_BM25
RRF_K = int(os.getenv("RRF_K", "60"))
FUSE_TOPK = int(os.getenv("FUSE_TOPK", "0"))  # 0 => no recortar; >0 => top-N

_WORD_RE = re.compile(r"\w+", re.UNICODE)

def _tok(text: str) -> List[str]:
    if not text:
        return []
    return _WORD_RE.findall(text.lower())

def _payload_text(p: Dict[str, Any]) -> str:
    """
    Preferencia:
      1) p['text'] / p['texto'] / p['chunk_text'] si existen en payload
      2) si es TXT y tenemos ruta_origen -> lee el archivo
    """
    t = p.get("text") or p.get("texto") or p.get("chunk_text")
    if t:
        return t
    path = p.get("ruta_origen")
    if path and path.lower().endswith(".txt") and os.path.exists(path):
        try:
            return read_text(path)
        except Exception:
            return ""
    return ""

def _bm25_order(query: str, texts: List[str], top_k: Optional[int] = None) -> List[int]:
    """Devuelve índices ordenados por score BM25 (desc). Evita división por cero si todo está vacío."""
    if not USE_BM25 or not texts:
        return list(range(len(texts)))
    tokenized = [_tok(t) for t in texts]
    # Si TODOS los documentos están vacíos, evita BM25
    if not any(len(doc) for doc in tokenized):
        return list(range(len(texts)))
    qtok = _tok(query)
    if not qtok:
        return list(range(len(texts)))
    bm = BM25Okapi(tokenized)  # type: ignore
    scores = bm.get_scores(qtok)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    if top_k is not None and top_k > 0:
        order = order[:min(top_k, len(order))]
    return order

def _rrf_fuse(rankings: List[List[int]], k: int, top_k: Optional[int] = None) -> List[int]:
    from collections import defaultdict
    agg = defaultdict(float)
    for r in rankings:
        for pos, idx in enumerate(r, start=1):
            agg[idx] += 1.0 / (k + pos)
    fused = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
    fused_idx = [i for i, _ in fused]
    if top_k is not None and top_k > 0:
        fused_idx = fused_idx[:min(top_k, len(fused_idx))]
    return fused_idx

def _apply_fusion(query: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fusión BM25 + denso preservando tamaño (o recortando si FUSE_TOPK>0).
    'hits' llega ordenado por score denso desc.
    """
    if not USE_BM25 or not hits:
        return hits
    dense_idx = list(range(len(hits)))
    texts = [_payload_text(h.get("payload") or {}) for h in hits]
    bm25_idx = _bm25_order(query, texts, top_k=None)
    if not bm25_idx:
        return hits
    top_k = FUSE_TOPK if FUSE_TOPK > 0 else None
    fused_idx = _rrf_fuse([dense_idx, bm25_idx], k=RRF_K, top_k=top_k)
    return [hits[i] for i in fused_idx]

# ---- Cliente Qdrant ---------------------------------------------------------
def _client() -> QdrantClient:
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://ia_qdrant:6333"), timeout=15.0)

def _search_collection(col: str, query_vec: List[float], limit: int = 8, flt: qm.Filter | None = None):
    qc = _client()
    return qc.search(
        collection_name=col,
        query_vector=query_vec,
        limit=limit,
        query_filter=flt,
        with_payload=True
    )

# ---- Búsquedas --------------------------------------------------------------
def search_txt_all_laws(query: str, topk_per_law: int = 8) -> List[dict]:
    alias = load_alias("/app/data/articulos/alias.txt")
    vec = embed_texts([query])[0]
    hits: List[dict] = []
    for ley_id in alias.keys():
        col = f"articulos__{ley_id}"
        try:
            rs = _search_collection(col, vec, limit=topk_per_law)
            for r in rs:
                hits.append({
                    "score": r.score,
                    "collection": col,
                    "payload": r.payload or {}
                })
        except Exception:
            continue
    hits.sort(key=lambda x: x["score"], reverse=True)
    return _apply_fusion(query, hits)

def search_txt_by_ref(ley_id: str, pieza_tipo: str, num: int | None, sufijo: str | None, limit: int = 3) -> List[dict]:
    qc = _client()
    col = f"articulos__{ley_id}"
    must = [qm.FieldCondition(key="pieza_tipo", match=qm.MatchValue(value=pieza_tipo))]
    if num is not None:
        must.append(qm.FieldCondition(key="num", match=qm.MatchValue(value=num)))
    if sufijo:
        must.append(qm.FieldCondition(key="sufijo", match=qm.MatchValue(value=sufijo)))
    flt = qm.Filter(must=must)
    res, _ = qc.scroll(collection_name=col, scroll_filter=flt, limit=limit, with_payload=True)
    return [{"score": 1.0, "collection": col, "payload": r.payload or {}} for r in res]

def search_pdf_ley(ley_id: str, query: str, limit: int = 6) -> List[dict]:
    col = f"pdf_fallback__{ley_id}"
    vec = embed_texts([query])[0]
    qc = _client()
    try:
        rs = qc.search(collection_name=col, query_vector=vec, limit=limit, with_payload=True)
        hits = [{"score": r.score, "collection": col, "payload": r.payload or {}} for r in rs]
        return _apply_fusion(query, hits)
    except Exception:
        return []

def search_pdf_temas(query: str, limit: int = 6) -> List[dict]:
    col = "pdf_temas"
    vec = embed_texts([query])[0]
    qc = _client()
    try:
        rs = qc.search(collection_name=col, query_vector=vec, limit=limit, with_payload=True)
        hits = [{"score": r.score, "collection": col, "payload": r.payload or {}} for r in rs]
        return _apply_fusion(query, hits)
    except Exception:
        return []

def search_txt_in_laws(query: str, law_ids: List[str], topk_per_law: int = 8) -> List[dict]:
    vec = embed_texts([query])[0]
    hits: List[dict] = []
    for ley_id in law_ids:
        col = f"articulos__{ley_id}"
        try:
            rs = _search_collection(col, vec, limit=topk_per_law)
            for r in rs:
                hits.append({
                    "score": r.score,
                    "collection": col,
                    "payload": r.payload or {}
                })
        except Exception:
            continue
    hits.sort(key=lambda x: x["score"], reverse=True)
    return _apply_fusion(query, hits)
