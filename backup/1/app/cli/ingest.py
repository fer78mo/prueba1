import argparse, os, sys
from app.ingest.pipeline import ingest_all, gc_versions, list_versions

def reindex_main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="reindex")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ley", default=None, help="IDs separadas por coma")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-pdf-temas", action="store_true")
    args = ap.parse_args(argv)

    data_root = os.getenv("DATA_ROOT","/app/data")
    scope = {"all": args.all, "ley_ids": args.ley.split(",") if args.ley else None}
    version = ingest_all(
        data_root=data_root,
        scope=scope,
        force=args.force,
        include_pdf_temas=(not args.no_pdf_temas)
    )
    print(f"OK reindex version={version}")
    return 0

def gc_main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=1)
    args = ap.parse_args(argv)
    gc_versions(keep=args.keep)
    print("OK gc")
    return 0

def versions_main(argv=None):
    vers = list_versions()
    for base, cols in vers.items():
        print(base, "→", ", ".join(cols))
    return 0

if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv)>1 else "reindex")
    argv = sys.argv[2:]
    if cmd=="reindex": sys.exit(reindex_main(argv))
    if cmd=="gc":      sys.exit(gc_main(argv))
    if cmd=="versions":sys.exit(versions_main(argv))
    print("Uso: python -m app.cli.ingest [reindex|gc|versions]")
    sys.exit(2)
