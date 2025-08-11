import time, os, threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from app.core.logging import get_logger
from app.cli.ingest import reindex_main

log = get_logger(__name__)
DATA_ROOT = "/app/data"

class Debounce:
    def __init__(self, secs=2.0):
        self.secs=secs; self.ts=0; self.lock=threading.Lock()
    def ping(self)->bool:
        with self.lock:
            now=time.time()
            if now - self.ts >= self.secs:
                self.ts = now
                return True
            self.ts = now
            return False

class Handler(FileSystemEventHandler):
    def __init__(self):
        self.deb = Debounce(2.0)
    def on_any_event(self, event):
        # Ignora temporales
        if event.is_directory: return
        p = event.src_path.lower()
        if not (p.endswith(".txt") or p.endswith(".pdf")): return
        if self.deb.ping():
            log.info({"event":"watch_trigger","path":event.src_path,"type":event.event_type})
            try:
                reindex_main(["--all"])
            except SystemExit:
                pass
            except Exception:
                log.exception("watch_reindex_failed")

def main():
    paths = [os.path.join(DATA_ROOT, "articulos"), os.path.join(DATA_ROOT, "fuentes_pdf"), os.path.join(DATA_ROOT, "preguntas")]
    obs = Observer()
    h = Handler()
    for p in paths:
        if os.path.isdir(p):
            obs.schedule(h, p, recursive=True)
    log.info({"event":"watch_start","paths":paths})
    obs.start()
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        obs.stop(); obs.join()

if __name__ == "__main__":
    main()
