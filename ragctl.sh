#!/bin/bash

# Configuración por defecto del contenedor
RAG_CONTAINER="${RAG_CONTAINER:-app-rag}"
CONTAINER="$RAG_CONTAINER"

# Colores para output
red() { echo -e "\033[31m$*\033[0m"; }
grn() { echo -e "\033[32m$*\033[0m"; }
ylw() { echo -e "\033[33m$*\033[0m"; }
blu() { echo -e "\033[34m$*\033[0m"; }

die() {
  red "ERROR: $*" >&2
  exit 1
}

need_container_running() {
  if ! docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER}$"; then
    die "Contenedor '$CONTAINER' no está corriendo. Usa docker-compose up -d"
  fi
}

in_container() {
  docker exec -i "$CONTAINER" bash -c "$*"
}

try_cli() {
  local name="$1" cmd="$2"
  need_container_running
  grn "==> $name"
  if in_container "$cmd"; then
    grn "✅ $name completado"
  else
    red "❌ $name falló"
    return 1
  fi
}

help() {
  cat <<HLP
🚀 Gestor RAG Jurídico - v2.0 (con Anti-Sesgo)

Uso: $0 COMANDO [opciones]

Comandos principales:
  status                       Estado de servicios (Qdrant, Ollama, etc.)
  reindex [--all|--ley IDs] [--force] [--no-pdf-temas]
                               Reindexa corpus (TXT + PDF)

Procesamiento de preguntas:
  ask [--file F] [--A "texto"] [--B "texto"] [--C "texto"] [--D "texto"] [--correcta X]
                               Resuelve pregunta individual
  watch                        Vigila /app/data y reindexa cuando detecta cambios
  run-batch [--dir DIR] [--max N] [--dry-run] [--validate]
                               Procesa todos los archivos; con --validate audita Etiqueta vs Modelo

Validación robusta (NUEVO):
  configure-robust             Configura el sistema para máxima robustez anti-sesgo
  validate-robust [--dir DIR] [--max N] [--dry-run]
                               Validación con anti-sesgo y fallbacks habilitados
  validate [--dir DIR] [--max N] [--dry-run] [--advanced]
                               Validación estándar o avanzada del sistema
  validate-advanced [--verbose] [--config-only] [--system-only] [--embeddings-only]
                    [--legal-only] [--collection NAME] [--output FILE] [--sample-file FILE]
                               Sistema de validación avanzado completo

Mantenimiento:
  gc [--force]                 Limpia vectores huérfanos en Qdrant
  logs [--tail N] [--since T]  Muestra logs de la aplicación
  metrics [--json]             Estadísticas de uso y rendimiento
  show-span [--file F]         Debug de spans resaltados
  eval [--dir DIR] [--max N]   Evaluación de accuracy en lote

Configuración:
  trace on|off                 Activa/desactiva modo traza (más DEBUG y trazas por pregunta)
  reload-prompts [--file F]    Fuerza recarga de prompts externos
  verify-corpus [--ley ID]     Verifica corpus (alias, nombres mal formados, vacíos)
  versions                     Lista versiones (version_tag) activas por colección
  help                         Esta ayuda

Variables de entorno:
  RAG_CONTAINER               Nombre del contenedor (default: app-rag)
  ANTI_BIAS_MODE             Activar anti-sesgo (default: true)
  MC_VALIDATION_PASSES       Número de pasadas anti-sesgo (default: 3)
  MIN_CONFIDENCE_THRESHOLD   Umbral mínimo de confianza (default: 0.6)
  FALLBACK_RETRIEVAL         Activar fallback de retrieval (default: true)

Ejemplos:
  $0 status
  $0 reindex --all --force
  $0 configure-robust          # ← NUEVO: Configura anti-sesgo
  $0 validate-robust --max 20  # ← NUEVO: Validación robusta
  $0 ask --file data/preguntas/test.txt
  $0 run-batch --validate --max 50
  $0 trace on
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

# NUEVAS FUNCIONES PARA ROBUSTEZ
cmd_configure_robust() {
  need_container_running
  echo "🔧 Configurando sistema para máxima robustez..."

  # Crear directorio de configuración si no existe
  in_container "mkdir -p /app/config /app/scripts"

  # Aplicar configuraciones anti-sesgo via variables de entorno
  in_container "cat > /app/config/anti_bias.env << 'EOF'
# Configuración Anti-Sesgo y Robustez
export ANTI_BIAS_MODE=true
export MC_VALIDATION_PASSES=3
export MIN_CONFIDENCE_THRESHOLD=0.6
export FALLBACK_RETRIEVAL=true
export VALIDATION_DETAILED_LOGGING=true
export FALLBACK_MINLEN_SHORT=30
export FALLBACK_MINLEN_LONG=45
export STRICT_CITATION=false
export STRICT_LAW_GUARD=false
export HIGHLIGHT_IN_OUTPUT=true
EOF"

  # Cargar configuraciones
  in_container "source /app/config/anti_bias.env"

  grn "✅ Sistema configurado con:"
  echo "  • Anti-sesgo activado (múltiples pasadas)"
  echo "  • Fallback de retrieval habilitado"
  echo "  • Umbrales de confianza optimizados"
  echo "  • Logging detallado de validación"

  # Mostrar configuraciones activas
  echo ""
  blu "📊 Configuraciones activas:"
  in_container "source /app/config/anti_bias.env && echo '  ANTI_BIAS_MODE: '$ANTI_BIAS_MODE"
  in_container "source /app/config/anti_bias.env && echo '  MC_VALIDATION_PASSES: '$MC_VALIDATION_PASSES"
  in_container "source /app/config/anti_bias.env && echo '  MIN_CONFIDENCE_THRESHOLD: '$MIN_CONFIDENCE_THRESHOLD"
  in_container "source /app/config/anti_bias.env && echo '  FALLBACK_RETRIEVAL: '$FALLBACK_RETRIEVAL"
}

cmd_validate_robust() {
  local dir="data/preguntas" max="" dry=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) shift; dir="${1:-$dir}";;
      --max) shift; max="--max ${1:-}";;
      --dry-run) dry="--dry-run";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done

  echo "🧪 Ejecutando validación robusta con anti-sesgo..."

  # Configurar sistema antes de validar
  cmd_configure_robust

  echo ""
  ylw "🚀 Iniciando validación..."

  # Ejecutar validación con configuraciones robustas
  in_container "source /app/config/anti_bias.env && python -m app.cli.run_batch --dir '$dir' $max $dry --validate"

  echo ""
  grn "✅ Validación robusta completada"
  echo "📁 Revisa los resultados en:"
  echo "  • CSV: /app/output/validate/"
  echo "  • TXT: /app/output/validate_txt/"
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
    try_cli "ask-file" "python -m app.cli.run_batch --single-file '$file'"
  elif [[ -n "$text" && -n "$A" && -n "$B" && -n "$C" && -n "$D" ]]; then
    local correct_arg=""
    [[ -n "$correct" ]] && correct_arg="--correcta '$correct'"
    try_cli "ask-text" "python -m app.cli.run_batch --text '$text' --A '$A' --B '$B' --C '$C' --D '$D' $correct_arg"
  else
    die "Usa: --file ARCHIVO o --text + --A --B --C --D [--correcta X]"
  fi
}

cmd_gc() {
  local force=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force) force="--force";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "gc" "python -m app.cli.gc $force"
}

cmd_logs() {
  local tail="100" since=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tail) shift; tail="${1:-$tail}";;
      --since) shift; since="--since ${1:-}";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  need_container_running
  grn "==> logs (tail=$tail)"
  in_container "tail -n $tail /app/output/logs/app.log"
}

cmd_metrics() {
  local json=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --json) json="--json";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "metrics" "python -m app.cli.metrics $json"
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
      --ley) shift; ley="--ley ${1:-}";;
      *) die "Opción no reconocida: $1";;
    esac
    shift || true
  done
  try_cli "verify-corpus" "python -m app.cli.verify_corpus $ley"
}

cmd_versions() {
  try_cli "versions" "python -m app.cli.ingest versions"
}

# Función de validación mejorada
cmd_validate() {
  local advanced="" dir="data/preguntas" max="" dry=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --advanced) advanced="--advanced";;
      --dir) shift; dir="${1:-$dir}";;
      --max) shift; max="--max ${1:-}";;
      --dry-run) dry="--dry-run";;
      *) # Pasar argumentos desconocidos al comando original
         break;;
    esac
    shift || true
  done

  if [[ -n "$advanced" ]]; then
    cmd_validate_advanced "$@"
  else
    cmd_run_batch --validate --dir "$dir" $max $dry "$@"
  fi
}

# Nueva función de validación avanzada
cmd_validate_advanced() {
  local verbose="" config_only="" output="" collection="juridico" sample=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --verbose|-v) verbose="--verbose";;
      --config-only) config_only="--config-only";;
      --system-only) system_only="--system-only";;
      --embeddings-only) embeddings_only="--embeddings-only";;
      --legal-only) legal_only="--legal-only";;
      --collection|-c) shift; collection="${1:-$collection}";;
      --output|-o) shift; output="--output ${1:-}";;
      --sample-file|-s) shift; sample="--sample-file ${1:-}";;
      --quiet|-q) quiet="--quiet";;
      *) die "Opción no reconocida para validación avanzada: $1";;
    esac
    shift || true
  done

  need_container_running
  grn "🚀 Ejecutando Validación Avanzada RAG Jurídico..."
  
  local cmd_args="$verbose $config_only $system_only $embeddings_only $legal_only"
  cmd_args="$cmd_args --collection $collection $output $sample $quiet"
  
  if in_container "cd /app && python scripts/validation/advanced_validator.py $cmd_args"; then
    grn "✅ Validación avanzada completada"
  else
    red "❌ Validación avanzada falló"
    return 1
  fi
}

# FUNCIÓN PRINCIPAL
main() {
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    help|-h|--help)    help ;;
    status)            cmd_status "$@" ;;
    reindex)           cmd_reindex "$@" ;;
    run-batch)         cmd_run_batch "$@" ;;
    ask)               cmd_ask "$@" ;;
    gc)                cmd_gc "$@" ;;
    logs)              cmd_logs "$@" ;;
    metrics)           cmd_metrics "$@" ;;
    show-span)         cmd_show_span "$@" ;;
    validate)          cmd_validate "$@" ;;
    eval)              cmd_eval "$@" ;;
    watch)             cmd_watch "$@" ;;
    trace)             cmd_trace "$@" ;;
    reload-prompts)    cmd_reload_prompts "$@" ;;
    verify-corpus)     cmd_verify_corpus "$@" ;;
    versions)          cmd_versions "$@" ;;
    # NUEVOS COMANDOS ROBUSTOS
    configure-robust)  cmd_configure_robust "$@" ;;
    validate-robust)   cmd_validate_robust "$@" ;;
    validate-advanced) cmd_validate_advanced "$@" ;;
    *) die "Comando no reconocido: $cmd (usa 'ragctl.sh help')" ;;
  esac
}

main "$@"