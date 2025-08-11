#!/usr/bin/env python3
import argparse
import os
import json
import time
import shutil
import tempfile
import csv
import random
from collections import Counter

from app.core.logging import get_logger
from app.core.utils import read_text
from app.pipeline.solver import solve_question

log = get_logger(__name__)

# Resaltado en TXT de salida (preview del span)
HIGHLIGHT = os.getenv("HIGHLIGHT_IN_OUTPUT", "true").lower() == "true"

# Configuraciones anti-sesgo
ANTI_BIAS_MODE = os.getenv("ANTI_BIAS_MODE", "true").lower() == "true"
MC_VALIDATION_PASSES = int(os.getenv("MC_VALIDATION_PASSES", "3"))
MIN_CONFIDENCE_THRESHOLD = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.6"))
FALLBACK_RETRIEVAL = os.getenv("FALLBACK_RETRIEVAL", "true").lower() == "true"

def parse_question_file(path: str) -> dict:
    """
    Formato esperado (1 archivo = 1 pregunta):
      <enunciado libre, varias líneas>

      A) Opción A
      B) Opción B
      C) Opción C
      D) Opción D

      Correcta: X                 # (opcional) letra A/B/C/D
      Modo: incorrecta|correcta   # (opcional) para solver; por defecto "correcta"
    """
    raw = read_text(path)
    lines = [l.rstrip() for l in raw.splitlines()]
    enun_lines = []
    opts = {}
    correct = None
    modo = None
    for ln in lines:
        s = ln.strip()
        if not s:
            if enun_lines:
                enun_lines.append("")
            continue
        U = s.upper()
        if U.startswith("A)"):
            opts["A"] = s[2:].strip()
        elif U.startswith("B)"):
            opts["B"] = s[2:].strip()
        elif U.startswith("C)"):
            opts["C"] = s[2:].strip()
        elif U.startswith("D)"):
            opts["D"] = s[2:].strip()
        elif "CORRECTA" in U:
            tail = s.split(":", 1)[-1].strip()
            correct = tail.replace(")", "").strip().upper()
        elif U.startswith("MODO:"):
            tail = s.split(":", 1)[-1].strip().lower()
            if tail in ("correcta", "incorrecta"):
                modo = tail
        else:
            enun_lines.append(s)
    enunciado = "\n".join([e for e in enun_lines]).strip()
    # Inferir modo a partir del enunciado si no viene explícito
    if not modo:
        t = " ".join(enun_lines).lower()
        if any(p in t for p in [
            "señala la incorrecta", "marca la incorrecta", "la incorrecta",
            "no es correcta", "no es cierto", "es falsa",
            "excepto", "salvo", "no corresponde", "no procede"
        ]):
            modo = "incorrecta"
    return {"enunciado": enunciado, "opciones": opts, "correcta": correct, "modo": (modo or "correcta")}

def _highlight_preview(text:str, start:int, end:int)->str:
    """Devuelve preview recortado alrededor del span."""
    if not text or start is None or end is None or start<0 or end>len(text) or start>=end:
        return ""
    full = text[:start] + "[[" + text[start:end] + "]]" + text[end:]
    L = max(0, start - 160)
    R = min(len(full), end + 162)  # +2 por [[
    return ("…" if L>0 else "") + full[L:R] + ("…" if R<len(full) else "")

def _read_src_text_from_result_fuentes(fuente: dict) -> str:
    src_text = ""
    path = (fuente or {}).get("ruta_origen")
    if path and os.path.exists(path) and path.lower().endswith(".txt"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                src_text = f.read()
        except Exception:
            src_text = ""
    elif (fuente or {}).get("source_kind") == "pdf":
        src_text = (fuente or {}).get("text_chunk", "")
    return src_text

def _score_option(info:dict)->tuple:
    """
    Ranking:
      1) tiene_cita True antes que False
      2) fuente.tipo == 'txt' antes que otras
      3) confianza mayor mejor
    """
    tiene_cita = 1 if info.get("tiene_cita") else 0
    fuente_tipo = (info.get("fuente") or {}).get("tipo")
    is_txt = 1 if fuente_tipo == "txt" else 0
    conf = float(info.get("confianza") or 0.0)
    return (tiene_cita, is_txt, conf)

def _solve_with_fallback(enunciado: str, opcion_texto: str, mode: str = "correcta"):
    """Solver con múltiples fallbacks para mejorar robustez"""

    # 1. Intento normal
    try:
        just, info = solve_question(enunciado, opcion_texto, mode=mode)
        if info.get("tiene_cita"):
            return just, info
    except Exception as e:
        log.debug(f"Primer intento falló: {e}")

    # 2. Fallback: Relajar configuraciones si está habilitado
    if FALLBACK_RETRIEVAL:
        # Guardar configuraciones originales
        orig_minlen_short = os.environ.get("MINLEN_SHORT", "60")
        orig_minlen_long = os.environ.get("MINLEN_LONG", "90")
        orig_strict_law = os.environ.get("STRICT_LAW_GUARD", "false")
        orig_strict_citation = os.environ.get("STRICT_CITATION", "false")

        try:
            # Configuraciones más permisivas
            os.environ["MINLEN_SHORT"] = "30"
            os.environ["MINLEN_LONG"] = "45"
            os.environ["STRICT_LAW_GUARD"] = "false"
            os.environ["STRICT_CITATION"] = "false"

            just, info = solve_question(enunciado, opcion_texto, mode=mode)

            # Restaurar configuraciones
            os.environ["MINLEN_SHORT"] = orig_minlen_short
            os.environ["MINLEN_LONG"] = orig_minlen_long
            os.environ["STRICT_LAW_GUARD"] = orig_strict_law
            os.environ["STRICT_CITATION"] = orig_strict_citation

            # Marcar que se usó fallback
            info["uso_fallback"] = True
            return just, info

        except Exception as e:
            # Restaurar configuraciones en caso de error
            os.environ["MINLEN_SHORT"] = orig_minlen_short
            os.environ["MINLEN_LONG"] = orig_minlen_long
            os.environ["STRICT_LAW_GUARD"] = orig_strict_law
            os.environ["STRICT_CITATION"] = orig_strict_citation

            log.debug(f"Fallback también falló: {e}")

    # 3. Última opción: respuesta sin cita
    return "", {"tiene_cita": False, "fuente": {}, "confianza": 0.0, "error": "sin_evidencia"}

def _select_best_option_robust(enunciado: str, opciones: dict, mode: str = "correcta"):
    """
    Versión robusta que mitiga sesgos posicionales usando múltiples pasadas
    """
    if not ANTI_BIAS_MODE:
        # Comportamiento original
        return _select_best_option_original(enunciado, opciones, mode)

    # Múltiples pasadas con orden aleatorio
    vote_scores = {}
    confidence_scores = {}

    for pasada in range(MC_VALIDATION_PASSES):
        # Barajar el orden de evaluación
        letters = list(opciones.keys())
        random.shuffle(letters)

        pasada_results = {}
        for L in letters:
            if L not in opciones:
                continue

            try:
                just, info = _solve_with_fallback(enunciado, opciones[L], mode=mode)
                sc = _score_option(info)
                conf = info.get("confianza", 0.0)

                pasada_results[L] = {
                    "score": sc,
                    "confidence": conf,
                    "justification": just,
                    "info": info
                }

            except Exception as e:
                log.debug(f"Error en opción {L}, pasada {pasada}: {e}")
                pasada_results[L] = {
                    "score": (0, 0, 0.0),
                    "confidence": 0.0,
                    "justification": "",
                    "info": {"tiene_cita": False, "fuente": {}, "confianza": 0.0}
                }

        # Encontrar mejor de esta pasada
        if pasada_results:
            if mode == "correcta":
                best_letter = max(pasada_results.keys(), key=lambda k: pasada_results[k]["score"])
            else:
                # Para incorrecta, buscamos la menor evidencia
                best_letter = min(pasada_results.keys(), key=lambda k: pasada_results[k]["score"])

            # Acumular votos
            vote_scores[best_letter] = vote_scores.get(best_letter, 0) + 1
            confidence_scores[best_letter] = confidence_scores.get(best_letter, 0) + pasada_results[best_letter]["confidence"]

    # Decidir por mayoría de votos
    if not vote_scores:
        raise ValueError("formato_invalido")

    winner = max(vote_scores.keys(), key=lambda k: vote_scores[k])
    avg_confidence = confidence_scores[winner] / vote_scores[winner] if vote_scores[winner] > 0 else 0.0

    # Obtener justificación final de la opción ganadora
    final_just, final_info = _solve_with_fallback(enunciado, opciones[winner], mode=mode)

    # Agregar metadatos de robustez
    final_info["anti_bias_votes"] = vote_scores
    final_info["avg_confidence"] = avg_confidence
    final_info["pasadas_realizadas"] = MC_VALIDATION_PASSES
    final_info["confianza_robusta"] = avg_confidence

    return winner, final_just, final_info

def _select_best_option_original(enunciado: str, opciones: dict, mode: str = "correcta"):
    """
    Versión original (comportamiento actual)
    """
    best = None
    best_key = None
    best_just = None
    best_info = None

    for L in ("A","B","C","D"):
        if L not in opciones:
            continue
        try:
            just, info = solve_question(enunciado, opciones[L], mode=mode)
            sc = _score_option(info)  # (tiene_cita, is_txt, conf)
        except Exception:
            # Trata como "sin evidencia"
            just, info = "", {"tiene_cita": False, "fuente": {}, "confianza": 0.0}
            sc = (0, 0, 0.0)

        # Para comparar con "max", invertimos para incorrecta
        key = sc if mode == "correcta" else (-sc[0], -sc[1], -sc[2])

        if (best_key is None) or (key > best_key):
            best = L
            best_key = key
            best_just = just
            best_info = info

    if best is None:
        raise ValueError("formato_invalido")
    return best, best_just, best_info

# Función pública que elige entre versiones
def _select_best_option(enunciado: str, opciones: dict, mode: str = "correcta"):
    """
    Selecciona la mejor opción con o sin anti-sesgo según configuración
    """
    return _select_best_option_robust(enunciado, opciones, mode)

# ================== SALIDA NORMAL (respuestas) ==================

def _write_outputs_normal(
    result: dict,
    jsonl_path: str,
    out_root_txt: str,
    base_dir: str,
    qfile: str,
    enunciado: str,
    opciones: dict,
    correcta_or_modelo: dict
):
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    rel = os.path.relpath(qfile, base_dir)
    out_txt = os.path.join(out_root_txt, rel)
    os.makedirs(os.path.dirname(out_txt), exist_ok=True)

    # JSONL
    with open(jsonl_path, "a", encoding="utf-8") as jf:
        jf.write(json.dumps(result, ensure_ascii=False) + "\n")

    # TXT
    letra = correcta_or_modelo["letra"]
    body = []
    body.append(f"{enunciado}")
    body.append("")
    for L in ("A","B","C","D"):
        if L in opciones:
            body.append(f"{L}) {opciones[L]}")
    body.append("")
    body.append(f"✅ Respuesta correcta: {letra})")
    body.append("")
    body.append("JUSTIFICACIÓN:")
    body.append("")
    body.append(f"✅ Respuesta correcta según el modelo: {letra})")
    body.append("")
    body.append(result["justificacion"])

    # preview
    fuente = (result.get("fuentes") or [{}])[0]
    span = result.get("span") or {}
    if HIGHLIGHT and span.get("start") is not None and span.get("end") is not None:
        src_text = _read_src_text_from_result_fuentes(fuente)
        if src_text:
            preview = _highlight_preview(src_text, span["start"], span["end"])
            if preview:
                body.append("")
                body.append("---")
                body.append("Fragmento con resaltado (preview):")
                body.append(preview)

    with open(out_txt, "w", encoding="utf-8") as tf:
        tf.write("\n".join(body).strip() + "\n")

def process_one(path: str, jsonl_path: str, out_root_txt: str, base_dir: str, dry_run: bool = False) -> dict:
    q = parse_question_file(path)
    if not q["enunciado"]:
        raise ValueError("formato_invalido")

    mode = q.get("modo", "correcta")

    # Modo 1: viene la correcta
    if q["correcta"] and q["correcta"] in q["opciones"]:
        letra = q["correcta"]
        correct_txt = q["opciones"][letra]
        just, info = solve_question(q["enunciado"], correct_txt, mode=mode)
        correcta_or_modelo = {"tipo":"enunciado","letra": letra}
    else:
        # Modo 2: que el modelo escoja (respetando el mode para ranking)
        letra, _just_tmp, _info_tmp = _select_best_option(q["enunciado"], q["opciones"], mode=mode)
        just, info = solve_question(q["enunciado"], q["opciones"][letra], mode=mode)
        correcta_or_modelo = {"tipo":"modelo","letra": letra}

    result = {
        "archivo": os.path.relpath(path, base_dir),
        "opcion_elegida": letra,
        "justificacion": just,
        "fuentes": [info.get("fuente")],
        "confianza": info.get("confianza", 0.0),
        "confianza_robusta": info.get("confianza_robusta", info.get("confianza", 0.0)),
        "verificacion_ok": info.get("tiene_cita", False),
        "uso_fallback_pdf": (info.get("fuente", {}) and info.get("fuente", {}).get("tipo") != "txt"),
        "uso_fallback_retrieval": info.get("uso_fallback", False),
        "anti_bias_votes": info.get("anti_bias_votes", {}),
        "span": info.get("span"),
        "motivo_no_resuelta": None,
        "modo": mode
    }

    if not dry_run:
        _write_outputs_normal(
            result,
            jsonl_path,
            out_root_txt,
            base_dir,
            path,
            q["enunciado"],
            q["opciones"],
            correcta_or_modelo
        )

    log.info({
        "event": "batch_item_ok",
        "file": result["archivo"],
        "modo": result["modo"],
        "fuente": result["fuentes"][0].get("tipo") if result["fuentes"] else "?",
        "conf": result["confianza"],
        "conf_robusta": result["confianza_robusta"],
        "anti_bias": bool(result["anti_bias_votes"])
    })
    return result

def run_batch(dir_path: str, dry_run: bool = False, max_n: int | None = None):
    out_dir_jsonl = "/app/output/respuestas"
    out_root_txt = "/app/output/respuestas_txt"
    os.makedirs(out_dir_jsonl, exist_ok=True)
    os.makedirs(out_root_txt, exist_ok=True)

    files = []
    for root, _, fns in os.walk(dir_path):
        if os.path.basename(root) == "_no_resueltas":
            continue
        for fn in fns:
            if fn.lower().endswith(".txt"):
                files.append(os.path.join(root, fn))
    files.sort()
    if max_n:
        files = files[:max_n]

    moved = 0
    okc = 0
    fails = []
    ts_batch = time.strftime("%Y%m%d_%H%M%S")
    jsonl_path = os.path.join(out_dir_jsonl, f"lote_{ts_batch}.jsonl")

    for f in files:
        try:
            process_one(f, jsonl_path, out_root_txt, dir_path, dry_run=dry_run)
            okc += 1
        except Exception as e:
            reason = str(e) or "error_desconocido"
            dst_dir = os.path.join(dir_path, "_no_resueltas")
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, os.path.basename(f))
            try:
                shutil.move(f, dst)
            except Exception:
                pass
            rel = os.path.relpath(f, dir_path)
            log.warning({"event": "moved_no_resuelta", "file": rel, "reason": reason})
            fails.append({"archivo": rel, "motivo": reason})
            moved += 1

    log.info({"event": "batch_done", "ok": okc, "moved_no_resueltas": moved})
    print(f"OK batch: {okc} resueltas; {moved} movidas a _no_resueltas")

    if fails:
        rep_dir = "/app/output/no_resueltas"
        os.makedirs(rep_dir, exist_ok=True)
        csv_path = os.path.join(rep_dir, f"no_resueltas_{ts_batch}.csv")
        json_path = os.path.join(rep_dir, f"no_resueltas_{ts_batch}.json")
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            w = csv.DictWriter(cf, fieldnames=["archivo", "motivo"])
            w.writeheader()
            w.writerows(fails)
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(fails, jf, ensure_ascii=False, indent=2)
        print(f"Reporte no resueltas → {csv_path}")

# ================== MODO VALIDATE MEJORADO ==================

def _write_outputs_validate(
    res: dict,
    jsonl_path: str,
    out_root_txt: str,
    base_dir: str,
    qfile: str,
    enunciado: str,
    opciones: dict,
    letra_gold: str,
    letra_model: str
):
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    rel = os.path.relpath(qfile, base_dir)
    out_txt = os.path.join(out_root_txt, rel)
    os.makedirs(os.path.dirname(out_txt), exist_ok=True)

    # JSONL
    with open(jsonl_path, "a", encoding="utf-8") as jf:
        jf.write(json.dumps(res, ensure_ascii=False) + "\n")

    # TXT auditoría mejorado
    body = []
    body.append(enunciado)
    body.append("")
    for L in ("A","B","C","D"):
        if L in opciones:
            body.append(f"{L}) {opciones[L]}")
    body.append("")

    estado = "✅ ACUERDO" if letra_gold == letra_model else "❌ DESACUERDO"
    conf_model = res.get("model_confidence", 0.0)
    conf_gold = res.get("gold_confidence", 0.0)

    body.append(f"🏷️  Etiqueta: {letra_gold}) | 🤖 Modelo: {letra_model}) → {estado}")
    body.append(f"📊 Confianza - Etiqueta: {conf_gold:.3f} | Modelo: {conf_model:.3f}")

    if res.get("model_low_confidence"):
        body.append("⚠️  BAJA CONFIANZA DEL MODELO")

    if res.get("anti_bias_votes"):
        votes = res["anti_bias_votes"]
        body.append(f"🗳️  Votos anti-sesgo: {votes}")

    body.append("")

    # Justificación etiqueta
    body.append("— 🏷️ Justificación (según etiqueta):")
    if res.get("gold_just"):
        body.append(res["gold_just"])
        gold_fuente = (res.get("gold_info", {}).get("fuente") or {})
        gold_span = (res.get("gold_info", {}) or {}).get("span") or {}
        if HIGHLIGHT and gold_span.get("start") is not None and gold_span.get("end") is not None:
            src_text = _read_src_text_from_result_fuentes(gold_fuente)
            if src_text:
                prev = _highlight_preview(src_text, gold_span["start"], gold_span["end"])
                if prev:
                    body.append("")
                    body.append("   · Fragmento (etiqueta, preview):")
                    body.append("   " + prev)
    else:
        body.append("❌ Sin evidencia o error")
        if res.get("gold_error"):
            body.append(f"   Error: {res['gold_error']}")

    body.append("")
    # Justificación modelo
    body.append("— 🤖 Justificación (según modelo):")
    if res.get("model_just"):
        body.append(res["model_just"])
        model_fuente = (res.get("model_info", {}).get("fuente") or {})
        model_span = (res.get("model_info", {}) or {}).get("span") or {}
        if HIGHLIGHT and model_span.get("start") is not None and model_span.get("end") is not None:
            src_text = _read_src_text_from_result_fuentes(model_fuente)
            if src_text:
                prev = _highlight_preview(src_text, model_span["start"], model_span["end"])
                if prev:
                    body.append("")
                    body.append("   · Fragmento (modelo, preview):")
                    body.append("   " + prev)
    else:
        body.append("❌ Sin evidencia o error")

    with open(out_txt, "w", encoding="utf-8") as tf:
        tf.write("\n".join(body).strip() + "\n")

def process_one_validate(path: str, jsonl_path: str, out_root_txt: str, base_dir: str, dry_run: bool=False) -> dict:
    q = parse_question_file(path)
    if not q["enunciado"]:
        raise ValueError("formato_invalido")
    if not (q["correcta"] and q["correcta"] in q["opciones"]):
        raise ValueError("validate_requiere_etiqueta")

    etiqueta = q["correcta"]
    enun = q["enunciado"]
    opts = q["opciones"]
    mode = q.get("modo","correcta")

    # 1) Modelo elige (con mode y anti-sesgo)
    model_letter, model_just, model_info = _select_best_option(enun, opts, mode=mode)

    # 2) Justificación de la etiqueta (solver explícito)
    gold_just, gold_info = None, {}
    gold_err = None
    try:
        gold_just, gold_info = _solve_with_fallback(enun, opts[etiqueta], mode=mode)
    except Exception as e:
        gold_err = str(e) or "error"

    agree = (etiqueta == model_letter)

    # Análisis de confianza
    model_conf = model_info.get("confianza_robusta", model_info.get("confianza", 0.0))
    gold_conf = gold_info.get("confianza", 0.0)

    model_low_conf = model_conf < MIN_CONFIDENCE_THRESHOLD
    gold_low_conf = gold_conf < MIN_CONFIDENCE_THRESHOLD

    # Motivo mejorado
    motivo = "ok" if agree else "desacuerdo"
    if not agree:
        if gold_low_conf and not (gold_info or {}).get("tiene_cita"):
            motivo = "etiqueta_sin_cita_baja_conf"
        elif not (gold_info or {}).get("tiene_cita"):
            motivo = "etiqueta_sin_cita"
        elif model_low_conf and not (model_info or {}).get("tiene_cita"):
            motivo = "modelo_sin_cita_baja_conf"
        elif not (model_info or {}).get("tiene_cita"):
            motivo = "modelo_sin_cita"
        elif model_low_conf:
            motivo = "desacuerdo_baja_confianza_modelo"
        elif gold_low_conf:
            motivo = "desacuerdo_baja_confianza_etiqueta"

    result = {
        "archivo": os.path.relpath(path, base_dir),
        "etiqueta": etiqueta,
        "modelo": model_letter,
        "acuerdo": agree,
        "motivo": motivo,
        "model_confidence": model_conf,
        "gold_confidence": gold_conf,
        "model_low_confidence": model_low_conf,
        "gold_low_confidence": gold_low_conf,
        "anti_bias_votes": model_info.get("anti_bias_votes", {}),
        "gold_just": gold_just,
        "gold_info": gold_info,
        "gold_error": gold_err,
        "model_just": model_just,
        "model_info": model_info,
        "ts": int(time.time())
    }

    if not dry_run:
        _write_outputs_validate(
            result,
            jsonl_path,
            out_root_txt,
            base_dir,
            path,
            enun,
            opts,
            etiqueta,
            model_letter
        )

    log.info({
        "event":"validate_item",
        "file":result["archivo"],
        "etiqueta":etiqueta,
        "modelo":model_letter,
        "acuerdo":agree,
        "motivo":motivo,
        "conf_modelo":model_conf,
        "conf_etiqueta":gold_conf,
        "anti_bias": bool(result["anti_bias_votes"])
    })
    return result

def run_validate(dir_path: str, dry_run: bool = False, max_n: int | None = None):
    out_dir_jsonl = "/app/output/validate"
    out_root_txt = "/app/output/validate_txt"
    os.makedirs(out_dir_jsonl, exist_ok=True)
    os.makedirs(out_root_txt, exist_ok=True)

    files = []
    for root, _, fns in os.walk(dir_path):
        if os.path.basename(root) == "_no_resueltas":
            continue
        for fn in fns:
            if fn.lower().endswith(".txt"):
                files.append(os.path.join(root, fn))
    files.sort()
    if max_n: files = files[:max_n]

    ts_batch = time.strftime("%Y%m%d_%H%M%S")
    jsonl_path = os.path.join(out_dir_jsonl, f"validate_{ts_batch}.jsonl")
    csv_rows = []
    motivo_counter = Counter()
    total, acuerdos = 0, 0

    # Contadores mejorados
    baja_conf_modelo = 0
    baja_conf_etiqueta = 0
    con_anti_bias = 0

    for f in files:
        try:
            r = process_one_validate(f, jsonl_path, out_root_txt, dir_path, dry_run=dry_run)
            total += 1
            acuerdos += 1 if r["acuerdo"] else 0
            motivo_counter[r["motivo"]] += 1

            if r["model_low_confidence"]:
                baja_conf_modelo += 1
            if r["gold_low_confidence"]:
                baja_conf_etiqueta += 1
            if r["anti_bias_votes"]:
                con_anti_bias += 1

            csv_rows.append({
                "archivo": r["archivo"],
                "etiqueta": r["etiqueta"],
                "modelo": r["modelo"],
                "acuerdo": r["acuerdo"],
                "motivo": r["motivo"],
                "conf_modelo": r["model_confidence"],
                "conf_etiqueta": r["gold_confidence"],
                "anti_bias": bool(r["anti_bias_votes"])
            })
        except Exception as e:
            log.warning({"event":"validate_skip","file":os.path.relpath(f,dir_path),"reason":str(e)})

    # CSV resumen mejorado
    csv_path = os.path.join(out_dir_jsonl, f"validate_{ts_batch}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        w = csv.DictWriter(cf, fieldnames=["archivo","etiqueta","modelo","acuerdo","motivo","conf_modelo","conf_etiqueta","anti_bias"])
        w.writeheader()
        w.writerows(csv_rows)

    # Resumen global mejorado
    acc = (acuerdos / total) if total else 0.0
    resumen = {
        "total": total,
        "acuerdos": acuerdos,
        "accuracy": round(acc, 4),
        "por_motivo": dict(motivo_counter),
        "baja_confianza_modelo": baja_conf_modelo,
        "baja_confianza_etiqueta": baja_conf_etiqueta,
        "con_anti_bias": con_anti_bias,
        "csv": csv_path,
    }
    log.info({"event":"validate_done", **resumen})

    print(f"VALIDATE MEJORADO: {total} evaluadas | accuracy={acc:.3%}")
    print(f"Motivos: {dict(motivo_counter)}")
    print(f"Baja confianza - Modelo: {baja_conf_modelo}, Etiqueta: {baja_conf_etiqueta}")
    print(f"Con anti-sesgo: {con_anti_bias}")
    print(f"CSV → {csv_path}")

# ================== MAIN ==================

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/app/data/preguntas")
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--single-file", default=None)
    ap.add_argument("--text", default=None)
    ap.add_argument("--A", default=None)
    ap.add_argument("--B", default=None)
    ap.add_argument("--C", default=None)
    ap.add_argument("--D", default=None)
    ap.add_argument("--correcta", default=None)
    ap.add_argument("--validate", action="store_true", help="Audita preguntas con 'Correcta: X' (Etiqueta vs Modelo)")
    args = ap.parse_args()

    if args.single_file and args.validate:
        raise SystemExit("No combine --single-file con --validate")
    if args.text and args.validate:
        raise SystemExit("No combine --text con --validate")

    if args.single_file:
        ts = time.strftime("%Y%m%d_%H%M%S")
        jsonl_path = os.path.join("/app/output/respuestas", f"lote_single_{ts}.jsonl")
        process_one(args.single_file, jsonl_path, "/app/output/respuestas_txt", os.path.dirname(args.single_file), dry_run=args.dry_run)

    elif args.text:
        if not all([args.A, args.B, args.C, args.D]):
            raise SystemExit("Faltan --A --B --C --D con --text")
        ts = time.strftime("%Y%m%d_%H%M%S")
        jsonl_path = os.path.join("/app/output/respuestas", f"lote_ask_{ts}.jsonl")
        ask_name = f"ask_{ts}.txt"
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
            if args.correcta:
                tf.write(f"{args.text}\n\nA) {args.A}\nB) {args.B}\nC) {args.C}\nD) {args.D}\n\nCorrecta: {args.correcta}\n")
            else:
                tf.write(f"{args.text}\n\nA) {args.A}\nB) {args.B}\nC) {args.C}\nD) {args.D}\n")
            temp_path = tf.name
        try:
            q = parse_question_file(temp_path)
            mode = q.get("modo","correcta")
            if q["correcta"] and q["correcta"] in q["opciones"]:
                letra = q["correcta"]
                just, info = solve_question(q["enunciado"], q["opciones"][letra], mode=mode)
                correcta_or_modelo = {"tipo":"enunciado","letra": letra}
            else:
                letra, just, info = _select_best_option(q["enunciado"], q["opciones"], mode=mode)
                correcta_or_modelo = {"tipo":"modelo","letra": letra}

            result = {
                "archivo": ask_name,
                "opcion_elegida": letra,
                "justificacion": just,
                "fuentes": [info.get("fuente")],
                "confianza": info.get("confianza", 0.0),
                "verificacion_ok": info.get("tiene_cita", False),
                "uso_fallback_pdf": (info.get("fuente", {}) and info.get("fuente", {}).get("tipo") != "txt"),
                "span": info.get("span"),
                "motivo_no_resuelta": None,
                "modo": mode
            }
            if not args.dry_run:
                _write_outputs_normal(
                    result,
                    jsonl_path,
                    "/app/output/respuestas_txt",
                    os.path.dirname(temp_path),
                    temp_path,
                    q["enunciado"],
                    q["opciones"],
                    correcta_or_modelo
                )
            print("\n=== ENUNCIADO ===")
            print(q["enunciado"])
            print("\n=== OPCIONES ===")
            for L in ("A","B","C","D"):
                if L in q["opciones"]:
                    mark = "  <-- CORRECTA (según enunciado)" if (correcta_or_modelo["tipo"]=="enunciado" and L==correcta_or_modelo["letra"]) else \
                           "  <-- ELEGIDA POR EL MODELO" if (correcta_or_modelo["tipo"]=="modelo" and L==correcta_or_modelo["letra"]) else ""
                    print(f"{L}) {q['opciones'][L]}{mark}")
            print("\n=== JUSTIFICACIÓN ===")
            print(result["justificacion"])
            fuente_tipo = result['fuentes'][0].get('tipo') if result['fuentes'] else '?'
            print(f"\n[Fuente: {fuente_tipo} | Confianza: {result['confianza']:.3f} | Modo: {result['modo']}]")
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    else:
        if args.validate:
            run_validate(args.dir, dry_run=args.dry_run, max_n=args.max)
        else:
            run_batch(args.dir, dry_run=args.dry_run, max_n=args.max)