import argparse
import os
import time
import json
import csv
from collections import Counter

from app.cli.run_batch import parse_question_file
from app.pipeline.solver import solve_question
from app.core.logging import get_logger

log = get_logger(__name__)

EVAL_DIR = "/app/output/eval"

def _list_txt(dir_path:str):
    files = [
        os.path.join(dir_path, f) for f in os.listdir(dir_path)
        if os.path.isfile(os.path.join(dir_path, f)) and f.lower().endswith(".txt")
    ]
    files.sort()
    return files

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def run_eval(dir_path:str, max_n:int|None=None):
    os.makedirs(EVAL_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(EVAL_DIR, f"eval_{ts}.json")
    csv_path  = os.path.join(EVAL_DIR, f"eval_{ts}.csv")

    files = _list_txt(dir_path)
    if max_n:
        files = files[:max_n]

    total = 0
    fuente_counter = Counter()
    cita_counter = Counter()  # con_cita/sin_cita
    confs = []
    rows = []

    for f in files:
        total += 1
        q = parse_question_file(f)
        ok = True
        motivo = None
        fuente = "?"
        conf = 0.0
        tiene_cita = False
        span_len = None
        t0 = time.time()
        try:
            correcta = q["correcta"]
            if not correcta or correcta not in q["opciones"]:
                raise ValueError("formato_invalido")
            ct = q["opciones"][correcta]
            just, info = solve_question(q["enunciado"], ct)
            fuente = (info.get("fuente") or {}).get("tipo","?")
            conf = _safe_float(info.get("confianza"), 0.0)
            tiene_cita = bool(info.get("tiene_cita", False))
            sp = info.get("span")
            if isinstance(sp, dict) and sp.get("start") is not None and sp.get("end") is not None:
                span_len = int(sp["end"] - sp["start"])
        except Exception as e:
            ok = False
            motivo = str(e) or "error_desconocido"
        dt_ms = int((time.time() - t0) * 1000)

        fuente_counter[fuente] += 1
        cita_counter["con_cita" if tiene_cita else "sin_cita"] += 1
        if ok:
            confs.append(conf)

        rows.append({
            "archivo": os.path.basename(f),
            "ok": ok,
            "motivo": motivo,
            "fuente": fuente,
            "tiene_cita": tiene_cita,
            "span_len": span_len,
            "confianza": conf,
            "tiempo_ms": dt_ms
        })

        log.info({"event":"eval_item","file":f,"ok":ok,"fuente":fuente,"cita":tiene_cita,"conf":conf,"ms":dt_ms})

    conf_media = round(sum(confs)/len(confs), 4) if confs else 0.0
    summary = {
        "total": total,
        "por_fuente": dict(fuente_counter),
        "citas": dict(cita_counter),
        "confianza_media": conf_media,
        "ts": int(time.time())
    }

    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump({"summary": summary, "items": rows}, jf, ensure_ascii=False, indent=2)

    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        w = csv.DictWriter(cf, fieldnames=["archivo","ok","motivo","fuente","tiene_cita","span_len","confianza","tiempo_ms"])
        w.writeheader()
        w.writerows(rows)

    print(json.dumps(summary, ensure_ascii=False))
    print(f"Guardado: {json_path}\n          {csv_path}")

    # DEVUELVE resumen y rutas para consumo por API
    return {"summary": summary, "json_path": json_path, "csv_path": csv_path}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/app/data/preguntas")
    ap.add_argument("--max", type=int, default=None)
    args = ap.parse_args()
    run_eval(args.dir, args.max)

if __name__ == "__main__":
    main()
