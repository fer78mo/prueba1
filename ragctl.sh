#!/usr/bin/env bash
set -Eeuo pipefail

# ragctl.sh — Control externo del contenedor app-rag
# Requiere Docker y el contenedor "app-rag" en marcha (o define RAG_CONTAINER).
# Subcomandos: status | reindex | run-batch | ask | gc | logs | metrics | show-span | eval | watch | trace | reload-prompts | verify-corpus | versions | help

CONTAINER="${RAG_CONTAINER:-app-rag}"

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[33m%s\033[0m\n' "$*"; }
inf()  { printf '[%s] %s\n' "$(date -Is)" "$*"; }
die()  { red "ERROR: $*"; exit 1; }

need_container_running() {
  local running
  running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)"
  [[ "$running" == "true" ]] || die "El contenedor \"$CONTAINER\" no está corriendo. Arráncalo y reintenta."
}

in_container() { docker exec -i "$CONTAINER" bash -lc "$*"; }

try_cli() {
  # Ejecuta un módulo CLI dentro del contenedor.
  # $1 = comando legible para logs
  # $2... = python -m ...
  local label="$1"; shift
  need_container_running
  set +e
  in_container "$*"; local rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    ylw "CLI interno aún no implementado o falló: $label"
    ylw "Comando intentado dentro del contenedor:"
    echo "    $*"
    ylw "Pega el código correspondiente en app/cli/… y vuelve a ejecutar."
    return $rc
  fi
}

help() {
cat <<'HLP'
Uso: ragctl.sh <comando> [opciones]

Comandos:
  status                       Muestra salud (Qdrant/Ollama) y estado del servicio
  reindex [--all|--ley IDS] [--force] [--no-pdf-temas]
                               Reindexa incremental; --force fuerza rebuild
  run-batch [--dir DIR] [--max N] [--dry-run]
                               Procesa todos los archivos de preguntas del DIR (1 archivo = 1 pregunta)
  ask --file FICH              Lanza una pregunta suelta desde archivo
  ask --text "..." --A "..." --B "..." --C "..." --D "..." --correcta "X"
                               Lanza pregunta suelta por texto/opciones
  gc [--keep N]                Limpia versiones antiguas en Qdrant (retención N)
  logs [--follow] [--since T] [--grep STR]
                               Muestra logs del contenedor; follow opcional
  metrics [--today|--summary]  Muestra métricas básicas (si existen)
  show-span [--file RUTA]      Muestra la cita resaltada (usa el último resultado si no pasas --file)
  eval [--dir DIR] [--max N]   Evalúa preguntas y genera /output/eval/{json,csv}
  watch                        Vigila /app/data y reindexa cuando detecta cambios
  run-batch [--dir DIR] [--max N] [--dry-run] [--validate]
                               Procesa todos los archivos; con --validate audita Etiqueta vs Modelo
  validate [--dir DIR] [--max N] [--dry-run]
                               Atajo de run-batch --validate
  trace on|off                 Activa/desactiva modo traza (más DEBUG y trazas por pregunta)
  reload-prompts [--file F]    Fuerza recarga de prompts externos
  verify-corpus [--ley ID]     Verifica corpus (alias, nombres mal formados, vacíos)
  versions                     Lista versiones (version_tag) activas por colección
  help                         Esta ayuda

Variables de entorno:
  RAG_CONTAINER   Nombre del contenedor (default: app-rag)
HLP
}

cmd_status() {
  need_container_running
  echo "==> Contenedor: $CONTAINER"
  echo "==> Servicios internos:"
  # Intento de CLI status; si no existe, hago pings mínimos
  if ! try_cli "status" "python -m app.cli.status"; then
    ylw "Haciendo checks básicos via curl..."
    in_container "which curl >/dev/null 2>&1 || apt-get update && apt-get install -y curl >/dev/null 2>&1 || true"
    echo -n "Qdrant /readyz: "
    in_container "curl -sS -m 3 -o /dev/null -w '%{http_code}\n' http://ia_qdrant:6333/readyz || echo fail"
    echo -n "Ollama /api/tags: "
    in_container "curl -sS -m 3 -o /dev/null -w '%{http_code}\n' http://ia_ollama_1:11434/api/tags || echo fail"
  fi
}

cmd_reindex() {
  local scope="--all" force="" npdf=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --all) scope="--all";;
      --ley) shift; [[ -z "${1:-}" ]] && die "Falta lista de IDs tras --ley"; scope="--ley $1";;
      --force) force="--force";;
      --no-pdf-temas) npdf="--no-pdf-temas";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "reindex" "python -m app.cli.ingest reindex $scope $force $npdf"
}

cmd_run_batch() {
  local dir="data/preguntas" max="" dry="" validate=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) shift; dir="${1:-$dir}";;
      --max) shift; max="--max ${1:-}";;
      --dry-run) dry="--dry-run";;
      --validate) validate="--validate";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "run-batch" "python -m app.cli.run_batch --dir '$dir' $max $dry $validate"
}

cmd_ask() {
  local file="" text="" A="" B="" C="" D="" correct=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --file) shift; file="${1:-}";;
      --text) shift; text="${1:-}";;
      --A) shift; A="${1:-}";;
      --B) shift; B="${1:-}";;
      --C) shift; C="${1:-}";;
      --D) shift; D="${1:-}";;
      --correcta) shift; correct="${1:-}";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  if [[ -n "$file" ]]; then
    try_cli "ask(file)" "python -m app.cli.run_batch --single-file '$file'"
  else
    [[ -n "$text" && -n "$A" && -n "$B" && -n "$C" && -n "$D" && -n "$correct" ]] \
      || die "Faltan parámetros para --text (necesita --A --B --C --D --correcta)."
    try_cli "ask(text)" "python -m app.cli.run_batch --text \"$text\" --A \"$A\" --B \"$B\" --C \"$C\" --D \"$D\" --correcta \"$correct\""
  fi
}

cmd_gc() {
  local keep="--keep 1"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep) shift; keep="--keep ${1:-1}";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "gc" "python -m app.cli.ingest gc $keep"
}

cmd_logs() {
  local follow="" since="" grep=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --follow) follow="--follow";;
      --since) shift; since="--since ${1:-1h}";;
      --grep) shift; grep="${1:-}";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  need_container_running
  if [[ -n "$grep" ]]; then
    docker logs $follow $since "$CONTAINER" 2>&1 | command grep -E --color=never "$grep" || true
  else
    docker logs $follow $since "$CONTAINER" 2>&1 || true
  fi
}

cmd_metrics() {
  local mode="--summary"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --today) mode="--today";;
      --summary) mode="--summary";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  if ! try_cli "metrics" "python -m app.cli.metrics $mode"; then
    ylw "Mostrando métricas locales si existen:"
    in_container "ls -1 output/metrics/*.json 2>/dev/null || true"
  fi
}

cmd_show_span() {
  local file=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --file) shift; file="${1:-}";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  if [[ -n "$file" ]]; then
    try_cli "show-span" "python -m app.cli.show_span --file '$file'"
  else
    try_cli "show-span" "python -m app.cli.show_span"
  fi
}

cmd_eval() {
  local dir="data/preguntas" max=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) shift; dir="${1:-$dir}";;
      --max) shift; max="--max ${1:-}";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "eval" "python -m app.cli.eval --dir '$dir' $max"
}

cmd_watch() {
  try_cli "watch" "python -m app.cli.watch"
}

cmd_trace() {
  [[ $# -ge 1 ]] || die "Usa: ragctl.sh trace on|off"
  case "$1" in
    on)  try_cli "trace on"  "python -m app.cli.trace on"  ;;
    off) try_cli "trace off" "python -m app.cli.trace off" ;;
    *) die "Usa: ragctl.sh trace on|off" ;;
  esac
}

cmd_reload_prompts() {
  local file="config/prompts.yaml"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --file) shift; file="${1:-$file}";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "reload-prompts" "python -m app.cli.prompts --reload --file '$file'"
}

cmd_verify_corpus() {
  local ley=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --ley) shift; ley="--ley ${1:-}";;  # (nota) el verificador actual ignora --ley; se mantiene por compatibilidad
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "verify-corpus" "python -m app.cli.verify_corpus $ley"
}

cmd_versions() {
  try_cli "versions" "python -m app.cli.ingest versions"
}

cmd_validate() {
  cmd_run_batch --validate "$@"
}

main() {
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    help|-h|--help) help ;;
    status)         cmd_status "$@" ;;
    reindex)        cmd_reindex "$@" ;;
    run-batch)      cmd_run_batch "$@" ;;
    ask)            cmd_ask "$@" ;;
    gc)             cmd_gc "$@" ;;
    logs)           cmd_logs "$@" ;;
    metrics)        cmd_metrics "$@" ;;
    show-span)      cmd_show_span "$@" ;;
    validate)       cmd_validate "$@" ;;
    eval)           cmd_eval "$@" ;;
    watch)          cmd_watch "$@" ;;
    trace)          cmd_trace "$@" ;;
    reload-prompts) cmd_reload_prompts "$@" ;;
    verify-corpus)  cmd_verify_corpus "$@" ;;
    versions)       cmd_versions "$@" ;;
    *) die "Comando no reconocido: $cmd (usa 'ragctl.sh help')" ;;
  esac
}

main "$@"
