import argparse, os, glob, json
from app.core.utils import read_text

OUT_DIR = "/app/output/resaltados"
RESP_DIR = "/app/output/respuestas"

def _latest_jsonl_path()->str|None:
    files = sorted(glob.glob(os.path.join(RESP_DIR, "*.jsonl")))
    return files[-1] if files else None

def _load_records(jsonl_path:str)->list[dict]:
    out=[]
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out

def _pick_record(recs:list[dict], basename:str|None)->dict|None:
    if not recs: return None
    if not basename:
        return recs[-1]
    base = os.path.basename(basename)
    for r in reversed(recs):
        if r.get("archivo")==base:
            return r
    return None

def _get_source_text(payload:dict)->str:
    # TXT: leo el archivo original
    path = (payload or {}).get("ruta_origen")
    if path and os.path.exists(path) and path.lower().endswith(".txt"):
        return read_text(path)
    # PDF: el chunk viene en el payload
    if (payload or {}).get("source_kind")=="pdf":
        return (payload or {}).get("text_chunk","")
    return ""

def _highlight_span(text:str, start:int, end:int)->tuple[str,str]:
    """Devuelve (preview, full_marked). Preview recorta alrededor del span."""
    if not text or start is None or end is None or start<0 or end>len(text) or start>=end:
        return "", ""
    full = text[:start] + "[[" + text[start:end] + "]]" + text[end:]
    L = max(0, start-160); R = min(len(full), end+160+2)  # +2 por [[
    preview = ("…" if L>0 else "") + full[L:R] + ("…" if R<len(full) else "")
    return preview, full

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None, help="Nombre de archivo de pregunta (p.ej. data/preguntas/Test-C05.txt). Si no, usa el último resultado.")
    args = ap.parse_args()

    jsonl = _latest_jsonl_path()
    if not jsonl:
        raise SystemExit("No hay respuestas JSONL en /app/output/respuestas")

    recs = _load_records(jsonl)
    rec = _pick_record(recs, args.file)
    if not rec:
        raise SystemExit("No se encontró el registro solicitado.")

    fuente = (rec.get("fuentes") or [{}])[0]
    span = rec.get("span") or {}
    start, end = span.get("start"), span.get("end")

    text = _get_source_text(fuente)
    if not text:
        raise SystemExit("No hay texto fuente disponible para este resultado.")

    if start is None or end is None:
        raise SystemExit("Este resultado no trae span. Activa STRICT_CITATION=true y vuelve a generar.")

    preview, full = _highlight_span(text, start, end)
    if not full:
        raise SystemExit("Span inválido o fuera de rango.")

    os.makedirs(OUT_DIR, exist_ok=True)
    base = rec.get("archivo","resultado")
    out_path = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(base))[0] + "_highlight.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full)

    ley_id = fuente.get("ley_id")
    ley_nombre = fuente.get("ley_nombre")
    ruta = fuente.get("ruta_origen")

    print(f"Archivo pregunta : {base}")
    print(f"Fuente           : {fuente.get('tipo')}")
    print(f"Ley              : {ley_id} | {ley_nombre}")
    print(f"Ruta origen      : {ruta or '(chunk PDF)'}")
    print(f"Span             : [{start},{end})")
    print("\n=== PREVIEW ===")
    print(preview)
    print(f"\nGuardado resaltado completo en: {out_path}")

if __name__ == "__main__":
    main()

