import os, hashlib, requests
from typing import List

def sha256_file(path:str)->str:
    h = hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def list_files(root:str, exts:List[str])->List[str]:
    out=[]
    for base,_,files in os.walk(root):
        for fn in files:
            if any(fn.lower().endswith(e) for e in exts):
                out.append(os.path.join(base,fn))
    return sorted(out)

def read_text(path:str)->str:
    with open(path,'r',encoding='utf-8',errors='ignore') as f:
        return f.read()

def ping_qdrant(url:str)->bool:
    try:
        r = requests.get(f"{url}/readyz", timeout=3)
        return r.status_code==200
    except Exception:
        return False

def ping_ollama(url:str)->bool:
    try:
        r = requests.get(f"{url}/api/tags", timeout=3)
        return r.status_code==200
    except Exception:
        return False
