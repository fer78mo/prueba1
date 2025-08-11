import os, json, time

MET_DIR = "/app/output/metrics"
os.makedirs(MET_DIR, exist_ok=True)
EVT = os.path.join(MET_DIR, "ocr_events.jsonl")

def record_ocr(path:str, pages:int):
    try:
        with open(EVT, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": int(time.time()),
                "path": path,
                "pages_ocr": int(pages)
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass
