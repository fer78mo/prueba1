import os, sys

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("on","off"):
        print("uso: python -m app.cli.trace on|off", file=sys.stderr)
        sys.exit(2)
    mode = sys.argv[1]
    path = "/app/config/trace.flag"
    if mode == "on":
        with open(path, "w") as f: f.write("1")
        print("TRACE=ON")
    else:
        try: os.remove(path)
        except FileNotFoundError: pass
        print("TRACE=OFF")
    # Nota: tu logger puede leer este flag para subir a DEBUG.
    # Si ya usas LOG_LEVEL, puedes además exportar en runtime:
    #   os.environ["LOG_LEVEL"]="DEBUG"
if __name__ == "__main__":
    main()
