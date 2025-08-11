import os, json, glob, time
from collections import Counter

MET_DIR = "/app/output/metrics"
RESP_DIR = "/app/output/respuestas"

def _collect_jsonl(paths):
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue

def summary():
    os.makedirs(MET_DIR, exist_ok=True)
    paths = sorted(glob.glob(os.path.join(RESP_DIR, "*.jsonl")))
    c_fuente = Counter()
    c_cita = Counter()
    confs = []
    total = 0
    for row in _collect_jsonl(paths):
        total += 1
        f = (row.get("fuentes") or [{}])[0]
        c_fuente[f.get("tipo","?")] += 1
        c_cita["con_cita" if row.get("verificacion_ok") else "sin_cita"] += 1
        if "confianza" in row: confs.append(float(row["confianza"]))
    avg_conf = sum(confs)/len(confs) if confs else 0.0
    out = {
        "total": total,
        "por_fuente": dict(c_fuente),
        "citas": dict(c_cita),
        "confianza_media": round(avg_conf, 4),
        "ts": int(time.time())
    }
    path = os.path.join(MET_DIR, "summary.json")
    with open(path,"w",encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False))

def today():
    # Simple: usa los últimos 24h (por timestamp en nombre de archivo)
    summary()

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    if args.today: today()
    else: summary()
