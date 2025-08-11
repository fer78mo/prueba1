import logging, json, os, sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

LEVEL = os.getenv("LOG_LEVEL","INFO").upper()
LOG_DIR = "/app/output/logs"
os.makedirs(LOG_DIR, exist_ok=True)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        base = {
            "ts": datetime.utcnow().isoformat()+"Z",
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)

def get_logger(name:str)->logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(LEVEL)

    # Archivo JSON
    fh = RotatingFileHandler(f"{LOG_DIR}/app.log", maxBytes=50_000_000, backupCount=14)
    fh.setLevel(LEVEL)
    fh.setFormatter(JsonFormatter())
    logger.addHandler(fh)

    # Consola humana
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(LEVEL)
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(ch)
    logger.propagate = False
    return logger
