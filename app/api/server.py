import os
import threading
from typing import Optional, Dict

from fastapi import FastAPI, Body, Header, HTTPException, Depends
from pydantic import BaseModel, Field

from app.cli.ingest import reindex_main  # reutilizamos el CLI
from app.pipeline.solver import solve_question
from app.core.logging import get_logger

log = get_logger(__name__)
app = FastAPI(title="RAG Jurídico", version="1.1")

AUTO_INGEST = os.getenv("AUTO_INGEST_ON_START", "false").lower() == "true"
DATA_ROOT = "/app/data"
API_KEY = os.getenv("API_KEY", None)

# ---------- Auth por cabecera X-API-Key (si no se define API_KEY, queda desactivada) ----------
def require_key(x_api_key: Optional[str] = Header(None)):
    if API_KEY is None:
        return True
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
    return True

# ---------- Modelos ----------
class Opciones(BaseModel):
    A: str
    B: str
    C: str
    D: str

class AskPayload(BaseModel):
    enunciado: str = Field(..., description="Texto del enunciado")
    opciones: Opciones
    correcta: str = Field(..., pattern=r"^[ABCD]$", description="Letra correcta")

class BatchPayload(BaseModel):
    dir: Optional[str] = Field(default="/app/data/preguntas", description="Directorio con preguntas")

# ---------- Endpoints ----------
@app.get("/status")
def status():
    # Pings mínimos (no importamos clientes pesados aquí)
    qdrant_url = os.getenv("QDRANT_URL", "http://ia_qdrant:6333")
    ollama_url = os.getenv("OLLAMA_URL", "http://ia_ollama_1:11434")
    return {
        "ok": True,
        "qdrant": qdrant_url,
        "ollama": ollama_url,
        "strict": os.getenv("STRICT_CITATION", "false"),
        "auth": ("on" if API_KEY else "off"),
    }

@app.post("/ask", dependencies=[Depends(require_key)])
def ask(payload: AskPayload):
    enun = payload.enunciado.strip()
    correcta = payload.correcta.strip().upper()
    op_text = getattr(payload.opciones, correcta)
    just, info = solve_question(enun, op_text)
    return {
        "enunciado": enun,
        "correcta": correcta,
        "justificacion": just,
        "fuente": info.get("fuente"),
        "confianza": info.get("confianza"),
        "tiene_cita": info.get("tiene_cita"),
        "span": info.get("span"),
        "ley_id": info.get("ley_id"),
        "ley_nombre": info.get("ley_nombre"),
    }

@app.post("/batch", dependencies=[Depends(require_key)])
def batch(payload: BatchPayload):
    # Ejecuta el mismo runner que el CLI
    from app.cli.run_batch import run_batch
    run_batch(payload.dir, dry_run=False, max_n=None)
    return {"ok": True, "dir": payload.dir}

@app.post("/reindex", dependencies=[Depends(require_key)])
def reindex(body: Dict = Body(default={"scope": "all"})):
    scope = (body or {}).get("scope", "all")
    args = []
    if scope == "all":
        args = ["--all"]
    elif scope == "ley":
        ids = (body or {}).get("ids")
        if not ids:
            raise HTTPException(status_code=400, detail="faltan ids")
        args = ["--ley", ",".join(ids)]
    else:
        raise HTTPException(status_code=400, detail="scope inválido (all|ley)")
    reindex_main(args)
    return {"ok": True, "scope": scope}

@app.get("/metrics/summary")
def metrics_summary():
    import json, glob
    path = sorted(glob.glob("/app/output/metrics/*.json"))[-1:]  # último si existe
    if not path:
        return {"ok": False, "error": "no hay métricas"}
    with open(path[0], "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"ok": True, "data": data}

# ---------- Auto-ingest al arrancar ----------
def _auto_ingest():
    try:
        log.info({"event": "auto_ingest_start"})
        reindex_main(["--all"])
        log.info({"event": "auto_ingest_done"})
    except Exception:
        log.exception("auto_ingest_failed")

if AUTO_INGEST:
    t = threading.Thread(target=_auto_ingest, daemon=True)
    t.start()
