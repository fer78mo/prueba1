import argparse, os, shutil, json

CACHE_DIR = "/app/output/prompts"
os.makedirs(CACHE_DIR, exist_ok=True)

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reload", action="store_true")
    ap.add_argument("--file", default="config/prompts.yaml")
    args = ap.parse_args(argv)

    if args.reload:
        src = args.file
        if not os.path.exists(src):
            print(json.dumps({"ok": False, "error": f"no existe {src}"}))
            return 1
        dst = os.path.join(CACHE_DIR, "prompts.yaml")
        shutil.copyfile(src, dst)
        print(json.dumps({"ok": True, "cache": dst}))
        return 0

    print(json.dumps({"ok": False, "error": "nada que hacer"}))
    return 2

if __name__ == "__main__":
    raise SystemExit(main())

