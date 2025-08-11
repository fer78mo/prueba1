import os
import re
from typing import Tuple, List, Dict, Any, Optional

from app.retrieve.retriever import (
    search_txt_by_ref, search_txt_in_laws,
    search_pdf_ley, search_pdf_temas
)
from app.retrieve.law_classifier import shortlist_laws
from app.retrieve.reranker import rerank
from app.io.alias_loader import load_alias
from app.verify.quote_matcher import (
    find_best_quote, option_overlap_support, find_span_exact
)
from app.core.utils import read_text
from app.llm.client import generate
from app.core.logging import get_logger

log = get_logger(__name__)

# Modo estricto: si no hay cita literal válida, no se justifica (se lanza error).
STRICT = os.getenv("STRICT_CITATION", "false").lower() == "true"


# ------------------------- Utilidades internas -------------------------

_ORD_WORDS = {
    "unica": "única", "única": "única",
    "primera": "primera", "segunda": "segunda", "tercera": "tercera",
    "cuarta": "cuarta", "quinta": "quinta", "sexta": "sexta",
    "séptima": "séptima", "septima": "séptima",
    "octava": "octava", "novena": "novena",
    "décima": "décima", "decima": "décima",
}

_ROMAN = r"(?:[ivxlcdm]+)"  # en minúsculas; ya pasamos a lower()

def _detect_reference(enunciado: str) -> Optional[dict]:
    """
    Intenta detectar una referencia explícita (artículo/disposición/anexo) y la ley.
    Devuelve: {"pieza_tipo","num","sufijo","ley_id"} (cualquiera puede ser None).
    """
    t = enunciado.lower()

    pieza_tipo = "articulo"
    num: Optional[int] = None
    suf: Optional[str] = None

    # Artículo 12 / Art. 12 / Artículo 12 bis/ter/...
    m = re.search(
        r'\bart(?:[íi]culo|\.)\s+(\d+)\s*'
        r'(bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies)?\b',
        t
    )
    if m:
        num = int(m.group(1))
        suf = m.group(2)

    else:
        # Disposición adicional/transitoria/final/derogatoria + ordinal (palabra o número)
        found = False
        for tipo in ["adicional", "transitoria", "final", "derogatoria"]:
            # palabra ordinal (primera/segunda/...) o número
            m2 = re.search(
                rf'disposici[oó]n\s+{tipo}\s+(({ "|".join(_ORD_WORDS.keys()) })|\d+)\b',
                t
            )
            if m2:
                pieza_tipo = f"disposicion_{tipo}"
                ord_txt = m2.group(1)
                # guardamos tal cual; para búsqueda directa por ref no exigimos num aquí
                # (search_txt_by_ref filtra por pieza_tipo y deja num/sufijo opcionales)
                found = True
                break
        if not found:
            # Anexo I/IA/IB/1/1A...
            m3 = re.search(rf'anexo\s+(({_ROMAN})|\d+)(?:-?([a-z]))?\b', t)
            if m3:
                pieza_tipo = "anexo"
                suf = m3.group(3)  # sufijo tipo "a"/"b" si viene

    # Ley (por id corto lo./l./r.e.) o por nombre oficial del alias
    ley_id = None
    alias = load_alias("/app/data/articulos/alias.txt")

    # id corto (lo.3-2018, l.19-2013, r.e.679-2016, ...)
    for lid in alias.keys():
        if lid.lower() in t:
            ley_id = lid
            break

    # nombre oficial (substring)
    if not ley_id:
        for lid, name in alias.items():
            if (name or "").lower() and (name.lower() in t):
                ley_id = lid
                break

    # Si no detectamos nada y no hay "artículo", devuelve None para no forzar vía ref
    if num is None and pieza_tipo == "articulo":
        return {"pieza_tipo": pieza_tipo, "num": None, "sufijo": suf, "ley_id": ley_id}

    return {"pieza_tipo": pieza_tipo, "num": num, "sufijo": suf, "ley_id": ley_id}


def _read_payload_text(payload: dict) -> str:
    # TXT: ruta_origen es un .txt real
    path = payload.get("ruta_origen")
    if path and os.path.exists(path) and path.lower().endswith(".txt"):
        return read_text(path)
    # PDF: guardamos el chunk en el payload
    if payload.get("source_kind") == "pdf":
        return payload.get("text_chunk", "")
    return ""


def _format_ref(p: dict, ley_nombre: Optional[str]) -> str:
    if p.get("pieza_tipo") == "articulo" and p.get("num") is not None:
        suf = f" {p.get('sufijo')}" if p.get('sufijo') else ""
        return f"(Artículo {p.get('num')}{suf}, {ley_nombre})"
    if (p.get("pieza_tipo") or "").startswith("disposicion_"):
        tipo = p["pieza_tipo"].split("_", 1)[1]
        ord_txt = p.get("ordinal")
        if not ord_txt:
            # Si guardamos número, úsalo; si no, deja vacío
            ord_txt = str(p.get("num")) if p.get("num") is not None else ""
        sep = " " if ord_txt else ""
        return f"(Disposición {tipo}{sep}{ord_txt}, {ley_nombre})"
    if p.get("pieza_tipo") == "anexo":
        suf = f"-{p.get('sufijo')}" if p.get('sufijo') else ""
        num = p.get("num") or ""
        return f"(Anexo {num}{suf}, {ley_nombre})"
    return f"({ley_nombre})" if ley_nombre else ""


def _filter_hits_by_expected_law(hits: List[dict], expected_ley_id: Optional[str]) -> List[dict]:
    """Si hay ley esperada, prioriza/filtra hits a esa ley; si se queda vacío, devolvemos los originales."""
    if not expected_ley_id:
        return hits
    filtered = [h for h in hits if (h.get("payload") or {}).get("ley_id") == expected_ley_id]
    return filtered if filtered else hits


def _pick_and_quote(
    enunciado: str,
    option_txt: str,
    hits: List[dict],
    alias: dict,
    expected_ley_id: Optional[str] = None
) -> tuple[str, dict, float, dict]:
    """
    Devuelve (cita_formateada, payload, score, span_info)
      - cita_formateada: «...»
      - span_info: {"start": int, "end": int} índices del texto original
    Si STRICT y no hay span exacto + solape con la opción, devuelve ("", payload_mejor, score, {}).
    """
    if not hits:
        return "", {}, 0.0, {}

    # Si esperamos una ley concreta (mencionada en el enunciado), prioriza esa ley
    hits = _filter_hits_by_expected_law(hits, expected_ley_id)

    texts: List[str] = []
    payloads: List[dict] = []
    for h in hits:
        p = h.get("payload") or {}
        t = _read_payload_text(p)
        if not t:
            continue
        texts.append(t)
        payloads.append(p)

    if not texts:
        return "", {}, 0.0, {}

    # Reranker (cruzado) sobre textos candidatos
    order = rerank(enunciado, texts)

    # Intento en top-6 con verificación estricta
    for idx, score in order[:6]:
        p = payloads[idx]
        t = texts[idx]
        # La cita se busca con enunciado + opción para dar contexto suficiente
        quote = find_best_quote(t, enunciado + " " + (option_txt or ""), min_len=90)
        if not quote:
            continue
        span = find_span_exact(t, quote)
        ok_overlap = option_overlap_support(quote, option_txt, min_ratio=0.08)
        if span and ok_overlap:
            return f"«{quote}»", p, float(score), {"start": span[0], "end": span[1]}
        if not STRICT and ok_overlap:
            return f"«{quote}»", p, float(score), {}

    # Si no pasó verificación estricta, devuelve el mejor payload sin cita
    idx, score = order[0]
    return "", payloads[idx], float(score), {}


# ------------------------- Punto de entrada público -------------------------

def solve_question(enunciado: str, opcion_correcta_texto: str) -> Tuple[str, dict]:
    """
    Devuelve (justificacion, info)
      - justificacion: texto con «cita…» + referencia formateada
      - info: dict con
          confianza: float
          fuente: {tipo: 'txt'|'pdf_ley'|'pdf_temas'|'sin_cita', ...payload}
          tiene_cita: bool
          span: {"start":int,"end":int} | None
          ley_id: str|None
          ley_nombre: str|None
    """
    alias = load_alias("/app/data/articulos/alias.txt")
    ref = _detect_reference(enunciado) or {}

    expected_ley_id = ref.get("ley_id")

    # 1) Acceso directo por referencia (si hay ley) → TXT
    if ref.get("ley_id"):
        try:
            hits = search_txt_by_ref(ref["ley_id"], ref.get("pieza_tipo", "articulo"), ref.get("num"), ref.get("sufijo"))
        except Exception as e:
            hits = []
            log.warning({"event": "search_txt_by_ref_failed", "err": str(e)})

        if hits:
            quote, payload, s, span = _pick_and_quote(enunciado, opcion_correcta_texto, hits, alias, expected_ley_id)
            ley_nombre = payload.get("ley_nombre") or alias.get(payload.get("ley_id")) or payload.get("ley_id")
            ref_txt = _format_ref(payload, ley_nombre)
            if quote:
                return f"{quote} {ref_txt}", {
                    "confianza": max(0.82, s),
                    "fuente": {"tipo": "txt", **payload},
                    "tiene_cita": True,
                    "span": span,
                    "ley_id": payload.get("ley_id"),
                    "ley_nombre": ley_nombre
                }
            if STRICT:
                raise ValueError("cita_no_encontrada")
            # si no STRICT, continúa a búsqueda semántica

    # 2) Clasificador de ley → shortlist + búsqueda TXT (BM25+denso con fusión en retriever)
    shortlist = [x for x, _ in shortlist_laws(enunciado, top_n=5)]
    if expected_ley_id and expected_ley_id not in shortlist:
        shortlist = [expected_ley_id] + [x for x in shortlist if x != expected_ley_id]
        if len(shortlist) > 5:
            shortlist = shortlist[:5]

    try:
        hits = search_txt_in_laws(enunciado, shortlist, topk_per_law=8)
    except Exception as e:
        hits = []
        log.warning({"event": "search_txt_in_laws_failed", "err": str(e)})

    if hits:
        quote, payload, s, span = _pick_and_quote(enunciado, opcion_correcta_texto, hits[:12], alias, expected_ley_id)
        ley_nombre = payload.get("ley_nombre") or alias.get(payload.get("ley_id")) or payload.get("ley_id")
        ref_txt = _format_ref(payload, ley_nombre)
        if quote:
            return f"{quote} {ref_txt}", {
                "confianza": max(0.72, s),
                "fuente": {"tipo": "txt", **payload},
                "tiene_cita": True,
                "span": span,
                "ley_id": payload.get("ley_id"),
                "ley_nombre": ley_nombre
            }
        if STRICT:
            raise ValueError("cita_no_encontrada")

    # 3) PDF de la ley (si hay pista de ley)
    ley_id_hint = expected_ley_id or ((hits[0]["payload"].get("ley_id")) if hits else None)
    if ley_id_hint:
        try:
            pdf_hits = search_pdf_ley(ley_id_hint, enunciado, limit=8)
        except Exception as e:
            pdf_hits = []
            log.warning({"event": "search_pdf_ley_failed", "err": str(e)})

        if pdf_hits:
            quote, payload, s, span = _pick_and_quote(enunciado, opcion_correcta_texto, pdf_hits[:8], alias, expected_ley_id)
            ley_nombre = alias.get(ley_id_hint) or ley_id_hint
            ref_txt = _format_ref(payload, ley_nombre)
            if quote:
                return f"{quote} {ref_txt}", {
                    "confianza": max(0.62, s),
                    "fuente": {"tipo": "pdf_ley", **payload},
                    "tiene_cita": True,
                    "span": span,
                    "ley_id": ley_id_hint,
                    "ley_nombre": ley_nombre
                }
            if STRICT:
                raise ValueError("cita_no_encontrada")

    # 4) PDF de temas (último recurso con cita)
    try:
        pdf_hits = search_pdf_temas(enunciado, limit=8)
    except Exception as e:
        pdf_hits = []
        log.warning({"event": "search_pdf_temas_failed", "err": str(e)})

    if pdf_hits:
        quote, payload, s, span = _pick_and_quote(enunciado, opcion_correcta_texto, pdf_hits[:8], alias, expected_ley_id)
        ley_nombre = payload.get("ley_nombre") or alias.get(payload.get("ley_id")) or payload.get("ley_id")
        ref_txt = _format_ref(payload, ley_nombre)
        if quote:
            return f"{quote} {ref_txt}", {
                "confianza": max(0.55, s),
                "fuente": {"tipo": "pdf_temas", **payload},
                "tiene_cita": True,
                "span": span,
                "ley_id": payload.get("ley_id"),
                "ley_nombre": ley_nombre
            }
        if STRICT:
            raise ValueError("cita_no_encontrada")

    # 5) Sin cita literal: solo si NO es estricto, intenta LLM con aviso
    if not STRICT:
        try:
            system = "Responde en español, conciso y sin inventar. Si no hay evidencia literal disponible, dilo."
            prompt = (
                f"Enunciado: {enunciado}\n"
                f"Opción correcta (texto): {opcion_correcta_texto}\n"
                f"No hay fragmento literal disponible. Resume por qué encaja según la ley aplicable, sin inventar."
            )
            resp = generate(system, prompt, temperature=0.1, top_p=0.9, max_tokens=300)
            if resp:
                return resp, {
                    "confianza": 0.4,
                    "fuente": {"tipo": "sin_cita"},
                    "tiene_cita": False,
                    "span": None,
                    "ley_id": None,
                    "ley_nombre": None
                }
        except Exception:
            pass

    # 6) No hay evidencia
    raise ValueError("sin_evidencia")
