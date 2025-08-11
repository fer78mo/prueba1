import os, re
from app.core.errors import AliasMissingError

def load_alias(alias_path:str)->dict:
    if not os.path.exists(alias_path):
        raise AliasMissingError(f"Falta alias.txt en {alias_path}")
    m={}
    with open(alias_path,'r',encoding='utf-8',errors='ignore') as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("#"): continue
            if "=" not in line: continue
            k,v = line.split("=",1)
            m[k.strip()] = v.strip()
    if not m:
        raise AliasMissingError("alias.txt vacío")
    return m
