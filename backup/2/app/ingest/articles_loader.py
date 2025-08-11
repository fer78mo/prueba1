import os
from app.core.utils import list_files, read_text, sha256_file
from app.normalize.filename_parser import parse_piece

def load_articles(ley_id:str, ley_dir:str, ley_nombre:str)->list:
    docs=[]
    for path in list_files(ley_dir, [".txt"]):
        fn = os.path.basename(path)
        if fn.lower()=="alias.txt": continue
        try:
            meta = parse_piece(fn)
        except Exception:
            # se deja a _invalid fuera, aquí solo ignoramos y seguimos
            continue
        texto = read_text(path).strip()
        if not texto: continue
        docs.append({
            "id": f"{ley_id}:{fn}",
            "text": texto,
            "payload": {
                "ley_id": ley_id,
                "ley_nombre": ley_nombre,
                "source_kind": "articulo",
                **meta,
                "ruta_origen": path,
                "hash_contenido": sha256_file(path),
                "version_tag": "",  # lo pone pipeline
                "posicion": None
            }
        })
    return docs
