import re

def normalize_spaces(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()

def normalize_quotes(s: str) -> str:
    return s.replace("“", "\"").replace("”", "\"").replace("’", "'").replace("‘", "'")

def canonical(s: str) -> str:
    return normalize_spaces(normalize_quotes(s))

def find_best_quote(context: str, query: str, min_len: int = 120) -> str | None:
    ctx = canonical(context)
    if not ctx:
        return None
    sentences = re.split(r'(?<=[\.\;\:])\s+', ctx)
    key = set(w.lower() for w in re.findall(r'\w{4,}', query))
    best, best_score = None, 0.0
    for s in sentences:
        if len(s) < min_len:
            continue
        sw = set(w.lower() for w in re.findall(r'\w{4,}', s))
        if not sw:
            continue
        j = len(key & sw) / (len(key) or 1)
        if j > best_score:
            best_score, best = j, s
    if not best and sentences:
        best = max(sentences, key=len)
    return best

def _canonical_with_map(s: str):
    """
    Devuelve (canon, map_idx) donde map_idx[i_canon] = índice en original.
    Colapsa espacios a uno y normaliza comillas.
    """
    s = normalize_quotes(s)
    out = []
    map_idx = []
    prev_space = False
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            if not prev_space:
                out.append(' ')
                map_idx.append(i)
                prev_space = True
            # si hay múltiples espacios, se colapsan y no se añaden más mapas
        else:
            out.append(ch)
            map_idx.append(i)
            prev_space = False
        i += 1
    canon = ''.join(out).strip()
    # arreglar mapa por strip: recalcula desplazamiento de trim izquierdo
    if canon:
        # posición en map_idx del primer carácter no-espacio de canon
        # ya está trim, así que no hay espacios al inicio/fin
        pass
    return canon, map_idx

def find_span_exact(context: str, quote: str) -> tuple[int, int] | None:
    """
    Busca la cita EXACTA (tras canonical) en el contexto y devuelve (start, end)
    en índices del texto original (no canonical). Si no encuentra, None.
    """
    if not context or not quote:
        return None
    c_can, c_map = _canonical_with_map(context)
    q_can, _ = _canonical_with_map(quote)
    if not c_can or not q_can:
        return None
    pos = c_can.find(q_can)
    if pos == -1:
        return None
    # mapear a índices del original usando el mapa del contexto
    # cuidado: c_map es 1:1 con c_can salvo los trims, que ya están colapsados antes
    try:
        start_orig = c_map[pos]
        end_orig = c_map[pos + len(q_can) - 1] + 1  # end exclusivo
        return (start_orig, end_orig)
    except Exception:
        return None

def quote_exists_exact(context: str, quote: str) -> bool:
    """Compat: verificación exacta simple (canónica)."""
    if not context or not quote:
        return False
    return canonical(quote) in canonical(context)

def option_overlap_support(quote: str, option_text: str, min_ratio: float = 0.08) -> bool:
    """Check rápido: la cita comparte algo con el texto de la opción correcta."""
    if not quote or not option_text:
        return False
    q = set(re.findall(r'\w{4,}', quote.lower()))
    o = set(re.findall(r'\w{4,}', option_text.lower()))
    if not o:
        return True
    return (len(q & o) / len(o)) >= min_ratio
