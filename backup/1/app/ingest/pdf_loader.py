import os, subprocess, tempfile, shutil, re
from pypdf import PdfReader
from PIL import Image
import pytesseract
from app.core.utils import list_files, sha256_file
from app.ingest.ocr_metrics import record_ocr  # <-- métricas OCR

def _pdf_text_pypdf(path:str)->str:
    try:
        r = PdfReader(path)
        parts=[]
        for p in r.pages:
            t = p.extract_text() or ""
            parts.append(t)
        return "\n".join(parts)
    except Exception:
        return ""

def extract_text_pdftotext(path:str)->str:
    try:
        out = subprocess.check_output(
            ["pdftotext","-layout","-q",path,"-"],
            stderr=subprocess.DEVNULL, timeout=60
        )
        return out.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def ocr_pdf_per_page(path:str, dpi:int=300, max_pages:int=100)->str:
    """OCR página a página con Tesseract (lang=spa). Usa pdftoppm -> PNGs temporales."""
    tmpdir = tempfile.mkdtemp(prefix="ocr_")
    try:
        # Genera PNGs
        cmd = ["pdftoppm","-r",str(dpi),"-png",path,os.path.join(tmpdir,"page")]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        pages = sorted([f for f in os.listdir(tmpdir) if f.endswith(".png")])
        text_parts=[]
        for i,fn in enumerate(pages):
            if i >= max_pages: break
            img_path = os.path.join(tmpdir, fn)
            try:
                img = Image.open(img_path)
                txt = pytesseract.image_to_string(img, lang="spa")
                if txt: text_parts.append(txt)
            except Exception:
                continue
        # registra métrica OCR
        try:
            record_ocr(path, min(len(pages), max_pages))
        except Exception:
            pass
        return "\n".join(text_parts)
    except Exception:
        return ""
    finally:
        try: shutil.rmtree(tmpdir)
        except Exception: pass

def classify_law_by_content(text:str, alias:dict)->str|None:
    """
    Heurística:
      - detecta 'xx/xxxx' y casa con alias por número-año
      - prioriza prefijos: 'Ley Orgánica' -> lo., 'Reglamento (UE)/Reglamento' -> r.e., 'Ley' -> l.
      - si hay varias candidatas con mismo número-año, decide por prefijo presente en texto
    Devuelve ley_id o None.
    """
    if not text: return None
    t = text.lower()
    t_norm = t.replace('ó','o').replace('í','i').replace('á','a').replace('é','e').replace('ú','u')
    m = re.search(r'(\d{1,4})\s*[/\-]\s*(\d{4})', t)
    if not m: return None
    num = int(m.group(1)); year = int(m.group(2))
    # Candidatas por número-año
    candidates = []
    for lid in alias.keys():
        m2 = re.search(r'(\d{1,4})-(\d{4})', lid)
        if not m2: continue
        n2 = int(m2.group(1)); y2 = int(m2.group(2))
        if n2 == num and y2 == year:
            candidates.append(lid)
    if not candidates:
        return None
    # Pistas por prefijo en el texto
    is_lo = ("orgánica" in t) or ("organica" in t_norm)
    is_re = ("reglamento" in t_norm) and (" ue" in t_norm or " union europea" in t_norm or "europea" in t_norm)
    # Orden por preferencia
    def pref_rank(lid:str)->int:
        if lid.startswith("lo.") and is_lo: return 0
        if lid.startswith("r.e.") and is_re: return 0
        if lid.startswith("l.") and not (is_lo or is_re): return 0
        if lid.startswith("lo."): return 1
        if lid.startswith("r.e."): return 2
        return 3
    candidates.sort(key=pref_rank)
    return candidates[0]

def load_pdfs(pdf_dir:str, classify_law)->dict:
    out = {"ley":{}, "tema":[]}
    from app.io.alias_loader import load_alias
    alias = load_alias("/app/data/articulos/alias.txt")
    for path in list_files(pdf_dir, [".pdf"]):
        base_text = _pdf_text_pypdf(path)
        if not base_text.strip():
            base_text = extract_text_pdftotext(path)
        # Si sigue pobre, dispara OCR (umbral: menos de 200 chars)
        if len((base_text or "").strip()) < 200:
            ocr = ocr_pdf_per_page(path, dpi=300, max_pages=200)
            if len(ocr.strip()) > len(base_text.strip()):
                base_text = ocr

        kind, ley_id_hint = classify_law(path, base_text)  # por nombre (LEY-*)
        if kind == "ley" and not ley_id_hint:
            ley_id_hint = classify_law_by_content(base_text, alias)

        doc = {"path": path, "text": base_text, "hash": sha256_file(path)}
        if kind=="ley" and ley_id_hint:
            out["ley"].setdefault(ley_id_hint, []).append(doc)
        else:
            out["tema"].append(doc)
    return out
