import os, re, sys, json
from typing import Dict, List
from app.io.alias_loader import load_alias

OK = "\u2705"
WARN = "\u26A0\uFE0F"
ERR = "\u274C"

ART_PAT = re.compile(
    r"""^articulo-(\d{1,3})(?:-(bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies))?\.txt$""",
    re.IGNORECASE
)
DISP_PAT = re.compile(
    r"""^disposicion-(adicional|transitoria|final|derogatoria)-(unica|\d{1,3})\.txt$""",
    re.IGNORECASE
)
ANEXO_PAT = re.compile(
    r"""^anexo([ivxlcdm]+|\d{1,3})(?:-([A-Za-z]))?\.txt$""",
    re.IGNORECASE
)
# Aceptamos errores comunes de sufijos (ej: "denogatoria")
DISP_TYPO_PAT = re.compile(
    r"""^disposicion-(adicional|transitoria|final|derogatoria|denogatoria)-(unica|\d{1,3})\.txt$""",
    re.IGNORECASE
)

def _scan_ley_dir(ley_dir:str)->Dict:
    files = [f for f in os.listdir(ley_dir) if os.path.isfile(os.path.join(ley_dir,f)) and f.lower().endswith(".txt")]
    stats = {
        "articulos": 0, "disposiciones": 0, "anexos": 0,
        "desconocidos": [], "typos": []
    }
    for fn in files:
        if ART_PAT.match(fn):
            stats["articulos"] += 1
            continue
        if DISP_PAT.match(fn):
            stats["disposiciones"] += 1
            continue
        if ANEXO_PAT.match(fn):
            stats["anexos"] += 1
            continue
        # check typos (solo report)
        if DISP_TYPO_PAT.match(fn):
            stats["typos"].append(fn)
            continue
        stats["desconocidos"].append(fn)
    return stats

def main(argv=None):
    data_root = os.getenv("DATA_ROOT","/app/data")
    articulos_dir = os.path.join(data_root, "articulos")
    alias_path = os.path.join(articulos_dir, "alias.txt")
    if not os.path.exists(alias_path):
        print(f"{ERR} Falta alias.txt en {articulos_dir}")
        sys.exit(2)
    alias = load_alias(alias_path)
    if not alias:
        print(f"{ERR} alias.txt vacío o inválido")
        sys.exit(2)

    print(f"{OK} alias.txt cargado ({len(alias)} leyes)")
    overall = {"ok":[], "warn":[], "err":[]}
    total_txt=0; total_desc=0

    for ley_id, ley_name in alias.items():
        ley_dir = os.path.join(articulos_dir, ley_id)
        if not os.path.isdir(ley_dir):
            print(f"{ERR} {ley_id}: carpeta no existe -> {ley_dir}")
            overall["err"].append(ley_id)
            continue
        s = _scan_ley_dir(ley_dir)
        total_txt += s["articulos"] + s["disposiciones"] + s["anexos"] + len(s["desconocidos"])
        line = f"{ley_id:<14} {OK} {s['articulos']:>3} art, {s['disposiciones']:>3} disp, {s['anexos']:>3} anexos"
        if s["desconocidos"]:
            line += f" | {WARN} desconocidos: {len(s['desconocidos'])}"
            overall["warn"].append(ley_id)
        else:
            overall["ok"].append(ley_id)
        if s["typos"]:
            line += f" | {WARN} typos disp: {', '.join(s['typos'][:3])}" + (" ..." if len(s["typos"])>3 else "")
            if ley_id not in overall["warn"]:
                overall["warn"].append(ley_id)
        print(line)
        # detalle desconocidos (máx 5)
        for fn in s["desconocidos"][:5]:
            print(f"   - {WARN} nombre no reconocido: {fn}")

    print("\nResumen:")
    print(f"  OK    : {len(overall['ok'])}")
    print(f"  WARN  : {len(overall['warn'])}")
    print(f"  ERR   : {len(overall['err'])}")
    print(f"  Total txt escaneados: {total_txt}")

    # dump JSON para consumo posterior
    rep_dir = "/app/output/metrics"
    os.makedirs(rep_dir, exist_ok=True)
    outp = os.path.join(rep_dir, "verify_corpus.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(overall, f, ensure_ascii=False, indent=2)
    print(f"{OK} Guardado: {outp}")

if __name__ == "__main__":
    main()
