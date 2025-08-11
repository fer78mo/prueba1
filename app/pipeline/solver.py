import os
import re
from typing import Tuple, List, Optional

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

# Modo estricto de cita literal
STRICT = os.getenv("STRICT_CITATION", "false").lower() == "true"
# Bloqueo por ley (si el enunciado/opción cita una ley y la mejor evidencia es de otra → descartar)
STRICT_LAW_GUARD = os.getenv("STRICT_LAW_GUARD", "false").lower() == "true"
# Longitud adaptativa para la cita
ADAPTIVE_MINLEN = os.getenv("ADAPTIVE_MINLEN", "true").lower() == "true"
MINLEN_SHORT = int(os.getenv("MINLEN_SHORT", "60"))
MINLEN_LONG = int(os.getenv("MINLEN_LONG", "90"))
SHORT_ARTICLE_THRESHOLD = int(os.getenv("SHORT_ARTICLE_THRESHOLD", "800"))  # chars

# ----------------- utilidades de parsing -----------------
_ORD_WORDS = {
    "unica": "única", "única": "única",
    "primera": "primera", "segunda": "segunda", "tercera": "tercera",
    "cuarta": "cuarta", "quinta": "quinta", "sexta": "sexta",
    "séptima": "séptima", "septima": "séptima",
    "octava": "octava", "novena": "novena",
    "décima": "décima", "decima": "décima",
}
_ROMAN = r"(?:[ivxlcdm]+)"


def _detect_reference(texto: str) -> Optional[dict]:
    """Detecta referencia directa a artículo/disposición/anexo y pista de ley en un texto."""
    if not (texto or "").strip():
        return {}
    t = texto.lower()
    pieza_tipo = "articulo"
    num: Optional[int] = None
    suf: Optional[str] = None

    # Artículo N [bis/ter/...]
    m = re.search(
        r"\bart(?:[íi]culo|\.)\s+(\d+)\s*"
        r"(bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies)?\b", t
    )
    if m:
        num = int(m.group(1))
        suf = m.group(2)
    else:
        found = False
        # Disposición adicional/transitoria/final/derogatoria + ordinal|número
        for tipo in ["adicional", "transitoria", "final", "derogatoria"]:
            m2 = re.search(
                rf"disposici[oó]n\s+{tipo}\s+(({ '|'.join(_ORD_WORDS.keys()) })|\d+)\b",
                t,
            )
            if m2:
                pieza_tipo = f"disposicion_{tipo}"
                found = True
                break
        if not found:
            # Anexo I/II/1/2/-a...
            m3 = re.search(rf"anexo\s+(({_ROMAN})|\d+)(?:-?([a-z]))?\b", t)
            if m3:
                pieza_tipo = "anexo"
                suf = m3.group(3)

    # Ley por id corto (lo., l., r.e.) o por nombre oficial
    ley_id = None
    alias = load_alias("/app/data/articulos/alias.txt")
    for lid in alias.keys():
        if lid.lower() in t:
            ley_id = lid
            break
    if not ley_id:
        for lid, name in alias.items():
            if (name or "").lower() and (name.lower() in t):
                ley_id = lid
                break

    if num is None and pieza_tipo == "articulo":
        return {"pieza_tipo": pieza_tipo, "num": None, "sufijo": suf, "ley_id": ley_id}
    return {"pieza_tipo": pieza_tipo, "num": num, "sufijo": suf, "ley_id": ley_id}


def _read_payload_text(payload: dict) -> str:
    """Devuelve el texto original de la pieza (TXT: lee ruta; PDF: usa chunk del payload)."""
    path = payload.get("ruta_origen")
    if path and os.path.exists(path) and path.lower().endswith(".txt"):
        return read_text(path)
    if payload.get("source_kind") == "pdf":
        return payload.get("text_chunk", "")
    return ""


def _format_ref(p: dict, ley_nombre: Optional[str]) -> str:
    """Formatea la referencia corta al final de la cita."""
    if p.get("pieza_tipo") == "articulo" and p.get("num") is not None:
        suf = f" {p.get('sufijo')}" if p.get('sufijo') else ""
        return f"(Artículo {p.get('num')}{suf}, {ley_nombre})"
    if (p.get("pieza_tipo") or "").startswith("disposicion_"):
        tipo = p["pieza_tipo"].split("_", 1)[1]
        ord_txt = p.get("ordinal") or (str(p.get("num")) if p.get("num") is not None else "")
        sep = " " if ord_txt else ""
        return f"(Disposición {tipo}{sep}{ord_txt}, {ley_nombre})"
    if p.get("pieza_tipo") == "anexo":
        suf = f"-{p.get('sufijo')}" if p.get('sufijo') else ""
        num = p.get("num") or ""
        return f"(Anexo {num}{suf}, {ley_nombre})"
    return f"({ley_nombre})" if ley_nombre else ""


def _guard_match(expected_ley_id: Optional[str], payload_ley_id: Optional[str]) -> bool:
    """Evalúa el guard de ley."""
    if not STRICT_LAW_GUARD:
        return True
    if not expected_ley_id:
        return True
    return (payload_ley_id == expected_ley_id)


def _min_quote_len(text: str, mode: str) -> int:
    """Calcula min_len adaptativo para citas."""
    if not ADAPTIVE_MINLEN:
        return MINLEN_LONG if mode != "incorrecta" else MINLEN_SHORT
    L = len(text or "")
    base = MINLEN_LONG if mode != "incorrecta" else MINLEN_SHORT
    return MINLEN_SHORT if L < SHORT_ARTICLE_THRESHOLD else base


def _first_fallback_idx(order: List[tuple], payloads: List[dict], expected_ley_id: Optional[str]) -> int:
    """Devuelve el primer índice en 'order' cuyo payload pasa el guard de ley; si ninguno, 0."""
    if not STRICT_LAW_GUARD or not expected_ley_id:
        return order[0][0]
    for idx, _score in order:
        if _guard_match(expected_ley_id, (payloads[idx] or {}).get("ley_id")):
            return idx
    return order[0][0]


def _pick_and_quote(
    enunciado: str,
    option_txt: str,
    hits: List[dict],
    alias: dict,
    expected_ley_id: Optional[str] = None,
    mode: str = "correcta",
) -> tuple[str, dict, float, dict]:
    """
    Selecciona mejor payload y produce cita literal verificada.
    Devuelve (cita_formateada, payload, score, span_dict).
    """
    if not hits:
        return "", {}, 0.0, {}

    # Cargamos textos/payloads válidos
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

    order = rerank(enunciado, texts)

    if mode != "incorrecta":
        # Buscamos apoyo literal de la opción (enunciado + opción)
        for idx, score in order[:6]:
            p = payloads[idx]
            # Ley-guard
            if not _guard_match(expected_ley_id, p.get("ley_id")):
                continue
            t = texts[idx]
            minlen = _min_quote_len(t, mode)
            quote = find_best_quote(t, enunciado + " " + (option_txt or ""), min_len=minlen)
            if not quote:
                continue
            span = find_span_exact(t, quote)
            ok_overlap = option_overlap_support(quote, option_txt, min_ratio=0.08)
            if span and ok_overlap:
                return f"«{quote}»", p, float(score), {"start": span[0], "end": span[1]}
            if not STRICT and ok_overlap:
                return f"«{quote}»", p, float(score), {}
        # sin cita válida → fallback con guard por ley
        fb_idx = _first_fallback_idx(order, payloads, expected_ley_id)
        return "", payloads[fb_idx], float(order[0][1]), {}

    # Modo "incorrecta": base normativa relevante al enunciado (para refutar opción)
    for idx, score in order[:8]:
        p = payloads[idx]
        if not _guard_match(expected_ley_id, p.get("ley_id")):
            continue
        t = texts[idx]
        minlen = _min_quote_len(t, mode)  # típicamente 60 para párrafos cortos
        quote = find_best_quote(t, enunciado, min_len=minlen)
        if not quote:
            continue
        span = find_span_exact(t, quote)
        if span:
            return f"«{quote}»", p, float(score), {"start": span[0], "end": span[1]}
        if not STRICT:
            return f"«{quote}»", p, float(score), {}
    fb_idx = _first_fallback_idx(order, payloads, expected_ley_id)
    return "", payloads[fb_idx], float(order[0][1]), {}


# ----------------- pipeline principal -----------------
def solve_question(enunciado: str, opcion_correcta_texto: str, mode: str = "correcta") -> Tuple[str, dict]:
    """
    mode: "correcta" | "incorrecta"
    Devuelve (justificación, info_dict).
    Ahora es "option-aware": si la opción cita artículo/ley, se prioriza esa referencia.
    """
    alias = load_alias("/app/data/articulos/alias.txt")
    ref_q = _detect_reference(enunciado) or {}
    ref_opt = _detect_reference(opcion_correcta_texto) or {}

    # Ley esperada: preferimos la que aparezca en la opción; si no, la del enunciado
    expected_ley_id = ref_opt.get("ley_id") or ref_q.get("ley_id")

    # 0) PRIORIDAD: referencia explícita en la OPCIÓN (ley + pieza) -> TXT by_ref
    if ref_opt.get("num") is not None and (ref_opt.get("ley_id") or expected_ley_id):
        ley_for_ref = ref_opt.get("ley_id") or expected_ley_id
        try:
            hits = search_txt_by_ref(
                ley_for_ref,
                ref_opt.get("pieza_tipo", "articulo"),
                ref_opt.get("num"),
                ref_opt.get("sufijo"),
            )
        except Exception as e:
            hits = []
            log.warning({"event": "search_txt_by_ref_opt_failed", "err": str(e)})
        if hits:
            quote, payload, s, span = _pick_and_quote(
                enunciado, opcion_correcta_texto, hits, alias, ley_for_ref, mode
            )
            ley_nombre = payload.get("ley_nombre") or alias.get(payload.get("ley_id")) or ley_for_ref
            ref_txt = _format_ref(payload, ley_nombre)
            if quote:
                pre = "" if mode == "correcta" else "La opción es INCORRECTA porque "
                return f"{pre}{quote} {ref_txt}", {
                    "confianza": max(0.84, s),
                    "fuente": {"tipo": "txt", **payload},
                    "tiene_cita": True,
                    "span": span,
                    "ley_id": ley_for_ref,
                    "ley_nombre": ley_nombre,
                }
            if STRICT:
                raise ValueError("cita_no_encontrada")

    # 1) Directo por referencia en ENUNCIADO (TXT)
    if ref_q.get("ley_id") and (ref_q.get("num") is not None):
        try:
            hits = search_txt_by_ref(
                ref_q["ley_id"],
                ref_q.get("pieza_tipo", "articulo"),
                ref_q.get("num"),
                ref_q.get("sufijo"),
            )
        except Exception as e:
            hits = []
            log.warning({"event": "search_txt_by_ref_q_failed", "err": str(e)})
        if hits:
            quote, payload, s, span = _pick_and_quote(
                enunciado, opcion_correcta_texto, hits, alias, ref_q["ley_id"], mode
            )
            ley_nombre = payload.get("ley_nombre") or alias.get(payload.get("ley_id")) or ref_q["ley_id"]
            ref_txt = _format_ref(payload, ley_nombre)
            if quote:
                pre = "" if mode == "correcta" else "La opción es INCORRECTA porque "
                return f"{pre}{quote} {ref_txt}", {
                    "confianza": max(0.82, s),
                    "fuente": {"tipo": "txt", **payload},
                    "tiene_cita": True,
                    "span": span,
                    "ley_id": payload.get("ley_id"),
                    "ley_nombre": ley_nombre,
                }
            if STRICT:
                raise ValueError("cita_no_encontrada")

    # 2) Shortlist de leyes (TXT, con posible fusión BM25 ya en retriever)
    shortlist = [x for x, _ in shortlist_laws(enunciado, top_n=5)]
    # Prioriza expected_ley_id dentro de la shortlist
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
        quote, payload, s, span = _pick_and_quote(
            enunciado, opcion_correcta_texto, hits[:12], alias, expected_ley_id, mode
        )
        ley_nombre = payload.get("ley_nombre") or alias.get(payload.get("ley_id")) or payload.get("ley_id")
        ref_txt = _format_ref(payload, ley_nombre)
        if quote:
            pre = "" if mode == "correcta" else "La opción es INCORRECTA porque "
            return f"{pre}{quote} {ref_txt}", {
                "confianza": max(0.72, s),
                "fuente": {"tipo": "txt", **payload},
                "tiene_cita": True,
                "span": span,
                "ley_id": payload.get("ley_id"),
                "ley_nombre": ley_nombre,
            }
        if STRICT:
            raise ValueError("cita_no_encontrada")

    # 3) PDF de la ley (si hay pista)
    ley_id_hint = expected_ley_id or ((hits[0]["payload"].get("ley_id")) if hits else None)
    if ley_id_hint:
        try:
            pdf_hits = search_pdf_ley(ley_id_hint, enunciado, limit=8)
        except Exception as e:
            pdf_hits = []
            log.warning({"event": "search_pdf_ley_failed", "err": str(e)})
        if pdf_hits:
            quote, payload, s, span = _pick_and_quote(
                enunciado, opcion_correcta_texto, pdf_hits[:8], alias, expected_ley_id, mode
            )
            ley_nombre = alias.get(ley_id_hint) or ley_id_hint
            ref_txt = _format_ref(payload, ley_nombre)
            if quote:
                pre = "" if mode == "correcta" else "La opción es INCORRECTA porque "
                return f"{pre}{quote} {ref_txt}", {
                    "confianza": max(0.62, s),
                    "fuente": {"tipo": "pdf_ley", **payload},
                    "tiene_cita": True,
                    "span": span,
                    "ley_id": ley_id_hint,
                    "ley_nombre": ley_nombre,
                }
            if STRICT:
                raise ValueError("cita_no_encontrada")

    # 4) PDF de temas
    try:
        pdf_hits = search_pdf_temas(enunciado, limit=8)
    except Exception as e:
        pdf_hits = []
        log.warning({"event": "search_pdf_temas_failed", "err": str(e)})

    if pdf_hits:
        quote, payload, s, span = _pick_and_quote(
            enunciado, opcion_correcta_texto, pdf_hits[:8], alias, expected_ley_id, mode
        )
        ley_nombre = payload.get("ley_nombre") or alias.get(payload.get("ley_id")) or payload.get("ley_id")
        ref_txt = _format_ref(payload, ley_nombre)
        if quote:
            pre = "" if mode == "correcta" else "La opción es INCORRECTA porque "
            return f"{pre}{quote} {ref_txt}", {
                "confianza": max(0.55, s),
                "fuente": {"tipo": "pdf_temas", **payload},
                "tiene_cita": True,
                "span": span,
                "ley_id": payload.get("ley_id"),
                "ley_nombre": ley_nombre,
            }
        if STRICT:
            raise ValueError("cita_no_encontrada")

    # 5) Sin cita literal (solo NO estricto)
    if not STRICT:
        try:
            if mode == "incorrecta":
                system = "Explica por qué la opción dada es incorrecta citando la norma aplicable, sin inventar."
                prompt = (
                    f"Enunciado: {enunciado}\n"
                    f"Opción (a refutar): {opcion_correcta_texto}\n"
                    f"No hay fragmento literal disponible. Explica por qué es incorrecta de forma breve."
                )
            else:
                system = "Responde en español, conciso y sin inventar."
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
                    "ley_nombre": None,
                }
        except Exception:
            pass

    raise ValueError("sin_evidencia")
