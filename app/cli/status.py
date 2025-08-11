import os, json, requests

def main():
    qdrant = os.getenv("QDRANT_URL", "http://ia_qdrant:6333")
    ollama = os.getenv("OLLAMA_URL", "http://ia_ollama_1:11434")
    strict = os.getenv("STRICT_CITATION", "false")
    out = {"qdrant": False, "ollama": False, "strict": strict}

    try:
        r = requests.get(f"{qdrant}/readyz", timeout=2)
        out["qdrant"] = (r.status_code == 200)
    except Exception:
        out["qdrant"] = False

    try:
        r = requests.get(f"{ollama}/api/tags", timeout=2)
        out["ollama"] = (r.status_code == 200)
    except Exception:
        out["ollama"] = False

    print(json.dumps(out))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
