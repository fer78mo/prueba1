import os, time, re
from app.io.alias_loader import load_alias
from app.ingest.articles_loader import load_articles
from app.ingest.pdf_loader import load_pdfs, extract_text_pdftotext
from app.vector.embeddings import embed_texts, get_model
from app.vector.qdrant_store import ensure_versioned_collection, switch_alias, upsert_points, delete_old_versions, list_collections
from app.core.logging import get_logger
from app.ingest.state import snapshot_dir, load_manifest, save_manifest

log = get_logger(__name__)

def _version_tag()->str:
    return time.strftime("v_%Y%m%d_%H%M%S")

def classify_pdf(path:str, text:str):
    base = os.path.basename(path)
    if base.upper().startswith("LEY-"):
        m = re.search(r"(\d{1,4})[-_/](\d{4})", base)
        if m:
            t = (text or "").lower()
            if "orgánica" in t or "organica" in t: return "ley", f"lo.{m.group(1)}-{m.group(2)}"
            if "reglamento" in t and ("ue" in t or "europe" in t): return "ley", f"r.e.{m.group(1)}-{m.group(2)}"
            return "ley", f"l.{m.group(1)}-{m.group(2)}"
        return "ley", None
    return "tema", None

def _chunk_text(text:str, target_chars:int=4000, overlap:int=600):
    import re as _re
    text = _re.sub(r'\s+', ' ', text).strip()
    if not text: return []
    chunks=[]
    i=0; n=len(text)
    while i<n:
        j=min(i+target_chars, n)
        k = text.rfind('. ', i, j)
        if k==-1 or (j-i)<1500: k = j
        else: k = k+1
        chunk = text[i:k].strip()
        if chunk: chunks.append(chunk)
        i = max(k - overlap, k)
    return chunks

def _ingest_ley(ley_id, ley_dir, ley_nombre, version, dim):
    docs = load_articles(ley_id, ley_dir, ley_nombre)
    if not docs:
        log.warning({"event":"ley_no_docs","ley_id":ley_id})
        return False
    base = f"articulos__{ley_id}"
    physical = ensure_versioned_collection(base, version, dim)
    texts = [d["text"] for d in docs]
    payloads = []
    ids = []
    for d in docs:
        d["payload"]["version_tag"] = version
        payloads.append(d["payload"]); ids.append(d["id"])
    vectors = embed_texts(texts)
    upsert_points(physical, vectors, payloads, ids)
    switch_alias(base, version)
    log.info({"event":"ingested_articulos","ley_id":ley_id,"count":len(ids),"collection":physical})
    return True

def _ingest_pdf_temas(pdfs_temas, version, dim):
    base = "pdf_temas"
    physical = ensure_versioned_collection(base, version, dim)
    all_texts=[]; payloads=[]; ids=[]
    for d in pdfs_temas:
        chunks = _chunk_text(d["text"], 4800, 800)
        for pos, ch in enumerate(chunks):
            all_texts.append(ch)
            payloads.append({
                "ley_id": "desconocida",
                "ley_nombre": None,
                "source_kind": "pdf",
                "pieza_tipo": None,
                "num": None,
                "sufijo": None,
                "ordinal": None,
                "ruta_origen": d["path"],
                "hash_contenido": d["hash"],
                "version_tag": version,
                "posicion": pos,
                "text_chunk": ch
            })
            ids.append(f"pdf_tema:{os.path.basename(d['path'])}:{pos}")
    if all_texts:
        vectors = embed_texts(all_texts)
        upsert_points(physical, vectors, payloads, ids)
    switch_alias(base, version)
    log.info({"event":"ingested_pdf_temas","chunks":len(ids),"docs":len({d['path'] for d in pdfs_temas}),"collection":physical})
    return True

def _ingest_pdf_ley(ley_id, docs, version, dim, alias):
    base = f"pdf_fallback__{ley_id}"
    physical = ensure_versioned_collection(base, version, dim)
    all_texts=[]; payloads=[]; ids=[]
    for d in docs:
        text = d["text"] or extract_text_pdftotext(d["path"])
        if not text: 
            continue
        chunks = _chunk_text(text, 4000, 600)
        for pos, ch in enumerate(chunks):
            all_texts.append(ch)
            payloads.append({
                "ley_id": ley_id,
                "ley_nombre": alias.get(ley_id),
                "source_kind": "pdf",
                "pieza_tipo": None,
                "num": None,
                "sufijo": None,
                "ordinal": None,
                "ruta_origen": d["path"],
                "hash_contenido": d["hash"],
                "version_tag": version,
                "posicion": pos,
                "text_chunk": ch
            })
            ids.append(f"pdf_ley:{ley_id}:{os.path.basename(d['path'])}:{pos}")
    if all_texts:
        vectors = embed_texts(all_texts)
        upsert_points(physical, vectors, payloads, ids)
    switch_alias(base, version)
    log.info({"event":"ingested_pdf_ley","ley_id":ley_id,"chunks":len(ids),"docs":len(docs),"collection":physical})
    return True

def ingest_all(data_root:str, scope:dict|None=None, force:bool=False, include_pdf_temas:bool=True):
    articulos_dir = os.path.join(data_root, "articulos")
    alias_path    = os.path.join(articulos_dir, "alias.txt")
    pdf_dir       = os.path.join(data_root, "fuentes_pdf")

    alias = load_alias(alias_path)
    version = _version_tag()
    dim = get_model().get_sentence_embedding_dimension()

    # Manifest previo y snapshots actuales
    manifest = load_manifest()
    snap_art = {}
    for ley_id in alias.keys():
        ley_dir = os.path.join(articulos_dir, ley_id)
        if os.path.isdir(ley_dir):
            snap_art[ley_id] = {"dir": ley_dir, "files": snapshot_dir(ley_dir, [".txt"])}
    snap_pdf_temas = snapshot_dir(pdf_dir, [".pdf"]) if os.path.isdir(pdf_dir) else {}

    changed_leyes = []
    for ley_id, meta in snap_art.items():
        prev = ((manifest.get("articulos") or {}).get(ley_id) or {})
        if force or prev != meta["files"]:
            changed_leyes.append(ley_id)

    pdf_changed = force or (manifest.get("pdf_temas") != snap_pdf_temas)

    # Respeta scope (si lo hay)
    if scope:
        if scope.get("ley_ids"):
            changed_leyes = [lid for lid in changed_leyes if lid in set(scope["ley_ids"])]
        elif scope.get("all"):
            pass
        else:
            # nada
            pass

    # --- Ingesta artículos por ley (solo cambiadas) ---
    for ley_id in changed_leyes:
        ley_dir = snap_art[ley_id]["dir"]
        if not os.path.isdir(ley_dir):
            log.warning({"event":"ley_dir_missing","ley_id":ley_id,"dir":ley_dir})
            continue
        _ingest_ley(ley_id, ley_dir, alias.get(ley_id), version, dim)

    # --- PDFs: cargar y clasificar (solo si cambiaron y permitidos) ---
    if include_pdf_temas and pdf_changed:
        pdfs = load_pdfs(pdf_dir, classify_pdf)
        # temas global
        tema_docs = [p for p in pdfs["tema"] if p["text"]]
        if tema_docs:
            _ingest_pdf_temas(tema_docs, version, dim)
        # ley específicas
        for ley_id, docs in pdfs["ley"].items():
            if docs:
                _ingest_pdf_ley(ley_id, docs, version, dim, alias)

    log.info({"event":"ingest_done","version":version})

    # Guarda manifest actualizado
    manifest_out = {
        "articulos": {lid: snap_art[lid]["files"] for lid in snap_art},
        "pdf_temas": snap_pdf_temas
    }
    save_manifest(manifest_out)
    return version

def gc_versions(keep:int=1):
    prefixes = set()
    for c in list_collections():
        if "__" in c:
            prefixes.add(c.split("__")[0])
    for pref in prefixes:
        delete_old_versions(keep_alias=pref, base_name=pref, keep=keep)
    log.info({"event":"gc_done","keep":keep})

def list_versions():
    out={}
    for c in list_collections():
        if "__" in c:
            base = c.split("__")[0]
            out.setdefault(base, []).append(c)
    for k in out: out[k].sort()
    return out
