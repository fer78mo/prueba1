import argparse
import os
import json
import time
import shutil
import tempfile
import csv

from app.core.logging import get_logger
from app.core.utils import read_text
from app.pipeline.solver import solve_question

log = get_logger(__name__)

# Resaltado en TXT de salida (preview del span)
HIGHLIGHT = os.getenv("HIGHLIGHT_IN_OUTPUT", "true").lower() == "true"

def parse_question_file(path: str) -> dict:
    """
    Formato (1 archivo = 1 pregunta):
      <enunciado libre>

      A) ...
      B) ...
      C) ...
      D) ...

      Correcta: X   # o "✅ Respuesta correcta: X)"
    Detecta además si el enunciado pide “incorrecta”.
    """
    import re
    raw = read_text(path)
    lines = [l.rstrip() for l in raw.splitlines()]

    enun_lines = []
    opts = {}
    correct = None

    re_opt = re.compile(r'^([ABCD])\)\s*(.+)$', re.IGNORECASE)
    re_correct = re.compile(r'^(?:✅\s*)?(?:respuesta\s+)?correcta\s*:\s*([ABCD])\)?\s*$', re.IGNORECASE)

    for ln in lines:
        s = ln.strip()
        if not s:
            if enun_lines:
                enun_lines.append("")
            continue

        m_opt = re_opt.match(s)
        if m_opt:
            letter = m_opt.group(1).upper()
            opts[letter] = m_opt.group(2).strip()
            continue

        m_corr = re_correct.match(s)
        if m_corr:
            correct = m_corr.group(1).upper()
            continue

        # Cualquier otra línea es enunciado (evita confundir "incorrecta" con "correcta")
        enun_lines.append(s)

    enunciado = "\n".join(enun_lines).strip()
    modo = "incorrecta" if re.search(r'\bincorrecta\b', enunciado.lower()) else "correcta"
    return {"enunciado": enunciado, "opciones": opts, "correcta": correct, "modo": modo}

def _highlight_span(text: str, start: int, end: int) -> tuple[str, str]:
    """Devuelve (preview, full_marked). El preview recorta alrededor del span."""
    if not text or start is None or end is None or start < 0 or end > len(text) or start >= end:
        return "", ""
    full = text[:start] + "[[" + text[start:end] + "]]" + text[end:]
    L = max(0, start - 160)
    R = min(len(full), end + 162)  # +2 por [[
    preview = ("…" if L > 0 else "") + full[L:R] + ("…" if R < len(full) else "")
    return preview, full

def _write_outputs(
    result: dict,
    jsonl_path: str,
    out_root_txt: str,
    base_dir: str,
    qfile: str,
    enunciado: str,
    opciones: dict,
    correcta_or_modelo: dict
):
    """
    correcta_or_modelo:
      - {"tipo":"enunciado","letra":"X"} si vino en el archivo
      - {"tipo":"modelo","letra":"X"} si la eligió el modelo
    """
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    rel = os.path.relpath(qfile, base_dir)
    out_txt = os.path.join(out_root_txt, rel)
    os.makedirs(os.path.dirname(out_txt), exist_ok=True)

    # JSONL (una línea por pregunta)
    with open(jsonl_path, "a", encoding="utf-8") as jf:
        jf.write(json.dumps(result, ensure_ascii=False) + "\n")

    # -------- Formato de salida en TXT EXACTO al solicitado --------
    letra = correcta_or_modelo["letra"]

    body = []
    # Enunciado
    body.append(f"{enunciado}")
    body.append("")  # línea en blanco

    # Opciones SIN marcas + encabezado
    body.append("OPCIONES:")
    for L in ("A", "B", "C", "D"):
        if L in opciones:
            body.append(f"{L}) {opciones[L]}")
    body.append("")  # línea en blanco

    # Línea "✅ Respuesta correcta: X)"
    body.append(f"✅ Respuesta correcta: {letra})")
    body.append("")  # línea en blanco

    # Bloque de justificación
    body.append("JUSTIFICACIÓN:")
    body.append("")  # línea en blanco
    # Siempre imprimimos también "según el modelo"
    body.append(f"✅ Respuesta correcta según el modelo: {letra})")
    body.append("")  # línea en blanco

    # Texto de la justificación del solver
    body.append(result["justificacion"])

    # Preview del span (si existe)
    fuente = (result.get("fuentes") or [{}])[0]
    span = result.get("span") or {}
    start, end = span.get("start"), span.get("end")

    if HIGHLIGHT and start is not None and end is not None:
        src_text = ""
        path = fuente.get("ruta_origen")
        if path and os.path.exists(path) and path.lower().endswith(".txt"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    src_text = f.read()
            except Exception:
                src_text = ""
        elif (fuente or {}).get("source_kind") == "pdf":
            src_text = fuente.get("text_chunk", "")

        if src_text:
            preview, _ = _highlight_span(src_text, start, end)
            if preview:
                body.append("")  # línea en blanco
                body.append("---")
                body.append("Fragmento con resaltado (preview):")
                body.append(preview)

    with open(out_txt, "w", encoding="utf-8") as tf:
        tf.write("\n".join(body).strip() + "\n")

def _score_option(info: dict) -> tuple:
    """
    Criterio de ranking:
      1) tiene_cita True antes que False
      2) fuente.tipo == 'txt' antes que otras
      3) confianza mayor mejor
    """
    tiene_cita = 1 if info.get("tiene_cita") else 0
    fuente_tipo = (info.get("fuente") or {}).get("tipo")
    is_txt = 1 if fuente_tipo == "txt" else 0
    conf = float(info.get("confianza") or 0.0)
    return (tiene_cita, is_txt, conf)

def _select_best_option(enunciado: str, opciones: dict):
    """Evalúa A-D y devuelve (letra, justificacion, info) con mejor score."""
    best = None
    best_tuple = None
    best_just = None
    best_info = None
    for L in ("A", "B", "C", "D"):
        if L not in opciones:  # opción ausente
            continue
        just, info = solve_question(enunciado, opciones[L])
        sc = _score_option(info)
        if (best is None) or (sc > best_tuple):
            best = L
            best_tuple = sc
            best_just = just
            best_info = info
    if best is None:
        raise ValueError("formato_invalido")  # no había opciones válidas
    return best, best_just, best_info

def process_one(path: str, jsonl_path: str, out_root_txt: str, base_dir: str, dry_run: bool = False) -> dict:
    q = parse_question_file(path)
    if not q["enunciado"]:
        raise ValueError("formato_invalido")

    # Modo 1: viene la correcta en el enunciado
    if q["correcta"] and q["correcta"] in q["opciones"]:
        letra = q["correcta"]
        correct_txt = q["opciones"][letra]
        just, info = solve_question(q["enunciado"], correct_txt)
        correcta_or_modelo = {"tipo": "enunciado", "letra": letra}
    else:
        # Modo 2: selección por el modelo
        letra, just, info = _select_best_option(q["enunciado"], q["opciones"])
        correcta_or_modelo = {"tipo": "modelo", "letra": letra}

    result = {
        "archivo": os.path.relpath(path, base_dir),
        "opcion_elegida": letra,
        "justificacion": just,
        "fuentes": [info.get("fuente")],
        "confianza": info.get("confianza", 0.0),
        "verificacion_ok": info.get("tiene_cita", False),
        "uso_fallback_pdf": (info.get("fuente", {}) and info.get("fuente", {}).get("tipo") != "txt"),
        "span": info.get("span"),
        "motivo_no_resuelta": None,
        "modo": correcta_or_modelo["tipo"]
    }

    if not dry_run:
        _write_outputs(
            result,
            jsonl_path,
            out_root_txt,
            base_dir,
            path,
            q["enunciado"],
            q["opciones"],
            correcta_or_modelo
        )

    log.info({
        "event": "batch_item_ok",
        "file": result["archivo"],
        "modo": result["modo"],
        "fuente": result["fuentes"][0].get("tipo") if result["fuentes"] else "?",
        "conf": result["confianza"]
    })
    return result

def run_batch(dir_path: str, dry_run: bool = False, max_n: int | None = None):
    out_dir_jsonl = "/app/output/respuestas"
    out_root_txt = "/app/output/respuestas_txt"
    os.makedirs(out_dir_jsonl, exist_ok=True)
    os.makedirs(out_root_txt, exist_ok=True)

    # RECURSIVO
    files = []
    for root, _, fns in os.walk(dir_path):
        if os.path.basename(root) == "_no_resueltas":
            continue
        for fn in fns:
            if fn.lower().endswith(".txt"):
                files.append(os.path.join(root, fn))
    files.sort()
    if max_n:
        files = files[:max_n]

    moved = 0
    okc = 0
    fails = []
    ts_batch = time.strftime("%Y%m%d_%H%M%S")
    jsonl_path = os.path.join(out_dir_jsonl, f"lote_{ts_batch}.jsonl")

    for f in files:
        try:
            process_one(f, jsonl_path, out_root_txt, dir_path, dry_run=dry_run)
            okc += 1
        except Exception as e:
            reason = str(e) or "error_desconocido"
            dst_dir = os.path.join(dir_path, "_no_resueltas")
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, os.path.basename(f))
            try:
                shutil.move(f, dst)
            except Exception:
                pass
            rel = os.path.relpath(f, dir_path)
            log.warning({"event": "moved_no_resuelta", "file": rel, "reason": reason})
            fails.append({"archivo": rel, "motivo": reason})
            moved += 1

    log.info({"event": "batch_done", "ok": okc, "moved_no_resueltas": moved})
    print(f"OK batch: {okc} resueltas; {moved} movidas a _no_resueltas")

    if fails:
        rep_dir = "/app/output/no_resueltas"
        os.makedirs(rep_dir, exist_ok=True)
        csv_path = os.path.join(rep_dir, f"no_resueltas_{ts_batch}.csv")
        json_path = os.path.join(rep_dir, f"no_resueltas_{ts_batch}.json")
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            w = csv.DictWriter(cf, fieldnames=["archivo", "motivo"])
            w.writeheader()
            w.writerows(fails)
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(fails, jf, ensure_ascii=False, indent=2)
        print(f"Reporte no resueltas → {csv_path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/app/data/preguntas")
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--single-file", default=None)
    ap.add_argument("--text", default=None)
    ap.add_argument("--A", default=None)
    ap.add_argument("--B", default=None)
    ap.add_argument("--C", default=None)
    ap.add_argument("--D", default=None)
    ap.add_argument("--correcta", default=None)
    args = ap.parse_args()

    if args.single_file:
        ts = time.strftime("%Y%m%d_%H%M%S")
        jsonl_path = os.path.join("/app/output/respuestas", f"lote_single_{ts}.jsonl")
        process_one(args.single_file, jsonl_path, "/app/output/respuestas_txt", os.path.dirname(args.single_file), dry_run=args.dry_run)

    elif args.text:
        if not all([args.A, args.B, args.C, args.D]):
            raise SystemExit("Faltan --A --B --C --D con --text")
        ts = time.strftime("%Y%m%d_%H%M%S")
        jsonl_path = os.path.join("/app/output/respuestas", f"lote_ask_{ts}.jsonl")
        ask_name = f"ask_{ts}.txt"
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
            if args.correcta:
                tf.write(f"{args.text}\n\nA) {args.A}\nB) {args.B}\nC) {args.C}\nD) {args.D}\n\nCorrecta: {args.correcta}\n")
            else:
                tf.write(f"{args.text}\n\nA) {args.A}\nB) {args.B}\nC) {args.C}\nD) {args.D}\n")
            temp_path = tf.name
        try:
            q = parse_question_file(temp_path)
            if q["correcta"] and q["correcta"] in q["opciones"]:
                letra = q["correcta"]
                just, info = solve_question(q["enunciado"], q["opciones"][letra])
                correcta_or_modelo = {"tipo": "enunciado", "letra": letra}
            else:
                letra, just, info = _select_best_option(q["enunciado"], q["opciones"])
                correcta_or_modelo = {"tipo": "modelo", "letra": letra}

            result = {
                "archivo": ask_name,
                "opcion_elegida": letra,
                "justificacion": just,
                "fuentes": [info.get("fuente")],
                "confianza": info.get("confianza", 0.0),
                "verificacion_ok": info.get("tiene_cita", False),
                "uso_fallback_pdf": (info.get("fuente", {}) and info.get("fuente", {}).get("tipo") != "txt"),
                "span": info.get("span"),
                "motivo_no_resuelta": None,
                "modo": correcta_or_modelo["tipo"]
            }
            if not args.dry_run:
                _write_outputs(
                    result,
                    jsonl_path,
                    "/app/output/respuestas_txt",
                    os.path.dirname(temp_path),
                    temp_path,
                    q["enunciado"],
                    q["opciones"],
                    correcta_or_modelo
                )
            print("\n=== ENUNCIADO ===")
            print(q["enunciado"])
            print("\n=== OPCIONES ===")
            for L in ("A", "B", "C", "D"):
                if L in q["opciones"]:
                    mark = "  <-- CORRECTA (según enunciado)" if (correcta_or_modelo["tipo"] == "enunciado" and L == correcta_or_modelo["letra"]) else \
                           "  <-- ELEGIDA POR EL MODELO" if (correcta_or_modelo["tipo"] == "modelo" and L == correcta_or_modelo["letra"]) else ""
                    print(f"{L}) {q['opciones'][L]}{mark}")
            print("\n=== JUSTIFICACIÓN ===")
            print(result["justificacion"])
            fuente_tipo = result['fuentes'][0].get('tipo') if result['fuentes'] else '?'
            print(f"\n[Fuente: {fuente_tipo} | Confianza: {result['confianza']:.3f} | Modo: {result['modo']}]")
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    else:
        run_batch(args.dir, dry_run=args.dry_run, max_n=args.max)
