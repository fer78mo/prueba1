import os, json, hashlib
from typing import Dict, List

MANIFEST_PATH = "/app/output/state/index_manifest.json"

def _sha256_file(path:str)->str:
    h = hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

def snapshot_dir(root:str, exts:List[str])->Dict[str,str]:
    out={}
    for base, _, files in os.walk(root):
        for fn in files:
            p = os.path.join(base, fn)
            if exts and not any(fn.lower().endswith(e) for e in exts):
                continue
            out[os.path.relpath(p, root)] = _sha256_file(p)
    return out

def load_manifest()->dict:
    try:
        with open(MANIFEST_PATH,"r",encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_manifest(data:dict)->None:
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH,"w",encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
