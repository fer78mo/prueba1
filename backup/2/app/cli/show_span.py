# app/cli/show_span.py
import os, sys, argparse, json
from typing import List, Optional
from app.cli.run_batch import parse_question_file
from app.retrieve.law_classifier import shortlist_laws
from app.retrieve.retriever import search_txt_in_laws, search_txt_by_ref, search_pdf_ley, search_pdf_temas
from app.io.alias_loader import load_alias
from app.verify.quote_matcher import find_best_quote, find_span_exact, option_overlap_support
from app.core.utils import read_text
from app.core.logging import get_logger

log = get_logger(__name__)

def _read_payload_text(p:dict)->str:
    path = p.get("ruta_origen")
    if path and os.path.exists(path) and path.lower().endswith(".txt"):
        try: return read_text(path)
        except Exception: return ""
    if p.get("source_kind") == "pdf":
        return p.get("text_chunk","")
    return ""

def _highlight(text:str, start:int, end:int)->str:
    if not text or start is None or end is None or start<0 or end>len(text) or start>=end:
        return ""
    full = text[:start] + "[[" + text[start:end] + "]]" + text[end:]
    L = max(0, start-160); R = min(len(full), end+162)
    return ("…" if L>0 else "") + full[L:R] + ("…" if R<len(full) else "")

def _detect_expected_law(enunciado:str)->Optional[str]:
    t = enunciado.lower()
    alias = load_alias("/app/data/articulos/alias.txt")
    for lid in alias.keys():
        if lid.lower() in t: return lid
    for lid, name in alias.items():
        if (name or "").lower() and name.lower() in t:
            return lid
    return None

def _probe(enunciado:str, opcion_txt:str):
    alias = load_alias("/app/data/articulos/alias.txt")
    expected = _detect_expected_law(enunciado)

    def dump_hit(source:str, payload:dict, quote:str, span:tuple|None, score:float):
        ley_id = payload.get("ley_id")
        ley_nombre = alias.get(ley_id) or ley_id
        pieza = f"{payload.get('pieza_tipo','?')} {payload.get('num') or payload.get('ordinal','')}".strip()
        ruta = payload.get("ruta_origen") or payload.get("pdf_path")
        print(f"\n[{source}] score={score:.3f} | ley={ley_id} ({ley_nombre}) | pieza={pieza}")
        if ruta: print(f"ruta: {ruta}")
        txt = _read_payload_text(payload)
        if txt and span:
            prev = _highlight(txt, span[0], span[1])
            if prev:
                print("--- preview ---")
                print(prev)
        if quote:
            print("--- quote ---")
            print(quote)

    # 1) TXT shortlist
    laws = [x for x,_ in shortlist_laws(enunciado, top_n=5)]
    if expected and expected not in laws:
        laws = [expected] + [x for x in laws if x!=expected]
        laws = laws[:5]
    hits = search_txt_in_laws(enunciado, laws, topk_per_law=6)
    print(f"\nTXT shortlist => {len(hits)} hits (laws={laws})")
    for h in hits[:8]:
        p = h["payload"] or {}
        t = _read_payload_text(p)
        if not t: continue
        quote = find_best_quote(t, enunciado + " " + (opcion_txt or ""), min_len=80)
        span = find_span_exact(t, quote) if quote else None
        ok = option_overlap_support(quote or "", opcion_txt or "", min_ratio=0.08)
        dump_hit("txt", p, (quote if ok else ""), (span if ok else None), h["score"])

    # 2) PDF ley (si tenemos expected)
    if expected:
        ph = search_pdf_ley(expected, enunciado, limit=6)
        print(f"\nPDF ley[{expected}] => {len(ph)} hits")
        for h in ph[:6]:
            p = h["payload"] or {}
            t = _read_payload_text(p)
            if not t: continue
            quote = find_best_quote(t, enunciado + " " + (opcion_txt or ""), min_len=80)
            span = find_span_exact(t, quote) if quote else None
            dump_hit("pdf_ley", p, quote or "", span, h["score"])

    # 3) PDF temas
    th = search_pdf_temas(enunciado, limit=6)
    print(f"\nPDF temas => {len(th)} hits")
    for h in th[:6]:
        p = h["payload"] or {}
        t = _read_payload_text(p)
        if not t: continue
        quote = find_best_quote(t, enunciado + " " + (opcion_txt or ""), min_len=80)
        span = find_span_exact(t, quote) if quote else None
        dump_hit("pdf_tema", p, quote or "", span, h["score"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="Ruta al archivo de pregunta")
    args = ap.parse_args()
    q = parse_question_file(args.file)
    if not q["enunciado"]: raise SystemExit("formato_invalido")
    letra = q["correcta"]
    if not letra or letra not in q["opciones"]:
        raise SystemExit("La pregunta no trae 'Correcta: X'.")
    opcion_txt = q["opciones"][letra]
    print(f"== ENUNCIADO ==\n{q['enunciado']}\n\n== OPCIÓN CORRECTA ==\n({letra}) {opcion_txt}")
    _probe(q["enunciado"], opcion_txt)

if __name__ == "__main__":
    main()
