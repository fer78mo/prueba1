import re
from typing import Optional, Tuple

ROMAN = {"i":1,"ii":2,"iii":3,"iv":4,"v":5,"vi":6,"vii":7,"viii":8,"ix":9,"x":10,"xi":11,"xii":12,"xiii":13,"xiv":14,"xv":15}

def roman_to_int(s:str)->Optional[int]:
    s=s.lower()
    return ROMAN.get(s)

def parse_piece(filename:str)->dict:
    # nombre sin extensión
    name = filename.rsplit(".",1)[0].lower()
    name = name.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    name = name.replace("denogatoria","derogatoria").replace("única","unica")

    # Artículo
    m = re.match(r"^articulo-(\d+)(?:-(bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies))?$", name)
    if m:
        num = int(m.group(1).lstrip("0") or "0")
        return {"pieza_tipo":"articulo","num":num,"sufijo":m.group(2),"ordinal":None}

    # Disposiciones
    for tipo in ["adicional","transitoria","derogatoria","final"]:
        pat = rf"^disposicion-{tipo}-(unica|\d+)$"
        m = re.match(pat, name)
        if m:
            num = None if m.group(1)=="unica" else int(m.group(1).lstrip("0") or "0")
            return {"pieza_tipo":f"disposicion_{tipo}","num":num,"sufijo":None,"ordinal":"unica" if num is None else None}

    # Anexo (num romano/arábigo + letra opcional)
    m = re.match(r"^anexo-(\d+|[ivxlcdm]+)(?:-([a-z]))?$", name)
    if m:
        raw = m.group(1)
        num = int(raw) if raw.isdigit() else roman_to_int(raw)
        letra = m.group(2)
        return {"pieza_tipo":"anexo","num":num,"sufijo":letra,"ordinal":None}

    # Título/Capítulo/Sección
    for tipo in ["titulo","capitulo","seccion"]:
        m = re.match(rf"^{tipo}-(\d+|[ivxlcdm]+)(?:-(bis))?$", name)
        if m:
            raw=m.group(1)
            num = int(raw) if raw.isdigit() else roman_to_int(raw)
            suf = m.group(2)
            return {"pieza_tipo":tipo,"num":num,"sufijo":suf,"ordinal":None}

    # Preambulo / Exposicion de motivos
    if name in ("preambulo","exposicion-de-motivos","exposicion_de_motivos","exposiciondemotivos"):
        return {"pieza_tipo":"exposicion_motivos" if "exposicion" in name else "preambulo","num":None,"sufijo":None,"ordinal":None}

    raise ValueError(f"Nombre no reconocido: {filename}")
