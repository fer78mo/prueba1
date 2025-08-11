import os
from sentence_transformers import SentenceTransformer

_model = None

def get_model():
    global _model
    if _model is None:
        name = os.getenv("EMB_MODEL","sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        _model = SentenceTransformer(name)
    return _model

def embed_texts(texts:list)->list:
    m = get_model()
    vecs = m.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
    return vecs.tolist()
