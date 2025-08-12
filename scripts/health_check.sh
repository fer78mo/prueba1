#!/bin/bash
# =============================================================================
# Health Check Script - RAG Jurídico
# =============================================================================
# 
# Script para verificar la salud completa del sistema RAG Jurídico
# Puede ser usado para monitoreo automático y alertas

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuración
TIMEOUT=30
VERBOSE=false
OUTPUT_JSON=false
ALERTS_FILE="/tmp/rag_alerts.log"

# Contadores
TOTAL_CHECKS=0
PASSED_CHECKS=0
WARNING_CHECKS=0
FAILED_CHECKS=0

# Array para almacenar resultados
declare -a HEALTH_RESULTS=()

# Funciones de utilidad
log() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${GREEN}[$(date +'%H:%M:%S')] $1${NC}" >&2
    fi
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}" >&2
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1" >> "$ALERTS_FILE"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1" >> "$ALERTS_FILE"
}

info() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}[INFO] $1${NC}" >&2
    fi
}

# Función para agregar resultado
add_result() {
    local check_name="$1"
    local status="$2"
    local message="$3"
    local details="${4:-}"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    case "$status" in
        "PASS")
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
            ;;
        "WARNING")
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
            ;;
        "FAIL")
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
            ;;
    esac
    
    HEALTH_RESULTS+=("$check_name|$status|$message|$details")
}

# Verificar si Docker está corriendo
check_docker() {
    log "🐳 Verificando Docker..."
    
    if ! command -v docker &> /dev/null; then
        add_result "docker_installed" "FAIL" "Docker no está instalado" ""
        return 1
    fi
    
    if ! docker info &> /dev/null 2>&1; then
        add_result "docker_running" "FAIL" "Docker no está corriendo" ""
        return 1
    fi
    
    add_result "docker_status" "PASS" "Docker está corriendo correctamente" ""
    return 0
}

# Verificar contenedores
check_containers() {
    log "📦 Verificando contenedores..."
    
    local containers=("app-rag" "ia_qdrant" "ia_ollama_1")
    local all_running=true
    
    for container in "${containers[@]}"; do
        if docker ps --format "table {{.Names}}" | grep -q "^${container}$"; then
            add_result "container_${container}" "PASS" "Contenedor $container está corriendo" ""
        else
            add_result "container_${container}" "FAIL" "Contenedor $container no está corriendo" ""
            all_running=false
        fi
    done
    
    if [ "$all_running" = true ]; then
        add_result "containers_overall" "PASS" "Todos los contenedores están corriendo" ""
        return 0
    else
        add_result "containers_overall" "FAIL" "Algunos contenedores no están corriendo" ""
        return 1
    fi
}

# Verificar servicios de red
check_network_services() {
    log "🌐 Verificando servicios de red..."
    
    # Verificar Qdrant
    if curl -s -f --max-time "$TIMEOUT" "http://localhost:6333/readyz" > /dev/null; then
        add_result "qdrant_api" "PASS" "Qdrant API responde correctamente" ""
    else
        add_result "qdrant_api" "FAIL" "Qdrant API no responde" ""
    fi
    
    # Verificar Ollama
    if curl -s -f --max-time "$TIMEOUT" "http://localhost:11434/api/tags" > /dev/null; then
        add_result "ollama_api" "PASS" "Ollama API responde correctamente" ""
    else
        add_result "ollama_api" "FAIL" "Ollama API no responde" ""
    fi
    
    # Verificar aplicación principal (si tiene endpoint de health)
    if curl -s -f --max-time "$TIMEOUT" "http://localhost:8000/health" > /dev/null 2>&1; then
        add_result "app_api" "PASS" "API de aplicación responde correctamente" ""
    else
        add_result "app_api" "WARNING" "API de aplicación no responde (puede ser normal)" ""
    fi
}

# Verificar recursos del sistema
check_system_resources() {
    log "💻 Verificando recursos del sistema..."
    
    # Verificar memoria
    if command -v free &> /dev/null; then
        local mem_usage=$(free | grep '^Mem:' | awk '{printf "%.1f", ($3/$2) * 100.0}')
        local mem_usage_int=${mem_usage%.*}
        
        if [ "$mem_usage_int" -lt 80 ]; then
            add_result "memory_usage" "PASS" "Uso de memoria: ${mem_usage}%" "$mem_usage"
        elif [ "$mem_usage_int" -lt 90 ]; then
            add_result "memory_usage" "WARNING" "Uso de memoria alto: ${mem_usage}%" "$mem_usage"
        else
            add_result "memory_usage" "FAIL" "Uso de memoria crítico: ${mem_usage}%" "$mem_usage"
        fi
    else
        add_result "memory_usage" "WARNING" "No se puede verificar uso de memoria" ""
    fi
    
    # Verificar disco
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ "$disk_usage" -lt 80 ]; then
        add_result "disk_usage" "PASS" "Uso de disco: ${disk_usage}%" "$disk_usage"
    elif [ "$disk_usage" -lt 90 ]; then
        add_result "disk_usage" "WARNING" "Uso de disco alto: ${disk_usage}%" "$disk_usage"
    else
        add_result "disk_usage" "FAIL" "Uso de disco crítico: ${disk_usage}%" "$disk_usage"
    fi
    
    # Verificar carga del sistema
    if command -v uptime &> /dev/null; then
        local load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
        local load_avg_int=${load_avg%.*}
        local cpu_count=$(nproc 2>/dev/null || echo "1")
        
        # Calcular porcentaje de carga basado en número de CPUs
        local load_percent=$(echo "scale=0; ($load_avg * 100) / $cpu_count" | bc -l 2>/dev/null || echo "0")
        
        if [ "$load_percent" -lt 70 ]; then
            add_result "system_load" "PASS" "Carga del sistema: ${load_avg} (${load_percent}%)" "$load_avg"
        elif [ "$load_percent" -lt 90 ]; then
            add_result "system_load" "WARNING" "Carga del sistema alta: ${load_avg} (${load_percent}%)" "$load_avg"
        else
            add_result "system_load" "FAIL" "Carga del sistema crítica: ${load_avg} (${load_percent}%)" "$load_avg"
        fi
    else
        add_result "system_load" "WARNING" "No se puede verificar carga del sistema" ""
    fi
}

# Verificar archivos y directorios importantes
check_file_structure() {
    log "📁 Verificando estructura de archivos..."
    
    local important_files=(
        "ragctl.sh"
        ".env"
        "docker-compose.yml"
        "requirements.txt"
    )
    
    local important_dirs=(
        "output"
        "output/logs"
        "scripts/validation"
        "tests"
    )
    
    # Verificar archivos
    for file in "${important_files[@]}"; do
        if [ -f "$file" ]; then
            add_result "file_${file//\//_}" "PASS" "Archivo $file existe" ""
        else
            add_result "file_${file//\//_}" "FAIL" "Archivo $file no existe" ""
        fi
    done
    
    # Verificar directorios
    for dir in "${important_dirs[@]}"; do
        if [ -d "$dir" ]; then
            add_result "dir_${dir//\//_}" "PASS" "Directorio $dir existe" ""
        else
            add_result "dir_${dir//\//_}" "WARNING" "Directorio $dir no existe" ""
        fi
    done
}

# Verificar logs recientes
check_logs() {
    log "📋 Verificando logs..."
    
    local log_file="output/logs/app.log"
    
    if [ -f "$log_file" ]; then
        local log_age=$(stat -c %Y "$log_file" 2>/dev/null || echo "0")
        local current_time=$(date +%s)
        local age_hours=$(( (current_time - log_age) / 3600 ))
        
        if [ "$age_hours" -lt 1 ]; then
            add_result "log_freshness" "PASS" "Logs recientes (hace ${age_hours}h)" "$age_hours"
        elif [ "$age_hours" -lt 24 ]; then
            add_result "log_freshness" "WARNING" "Logs antiguos (hace ${age_hours}h)" "$age_hours"
        else
            add_result "log_freshness" "FAIL" "Logs muy antiguos (hace ${age_hours}h)" "$age_hours"
        fi
        
        # Verificar errores recientes en logs
        local recent_errors=$(tail -n 100 "$log_file" 2>/dev/null | grep -i error | wc -l)
        
        if [ "$recent_errors" -eq 0 ]; then
            add_result "log_errors" "PASS" "Sin errores recientes en logs" "$recent_errors"
        elif [ "$recent_errors" -lt 5 ]; then
            add_result "log_errors" "WARNING" "$recent_errors errores recientes en logs" "$recent_errors"
        else
            add_result "log_errors" "FAIL" "$recent_errors errores recientes en logs" "$recent_errors"
        fi
    else
        add_result "log_file" "WARNING" "Archivo de log no encontrado" ""
    fi
}

# Ejecutar validación avanzada si está disponible
check_advanced_validation() {
    log "🔍 Ejecutando validación avanzada..."
    
    if [ -f "ragctl.sh" ] && [ -x "ragctl.sh" ]; then
        if timeout "$TIMEOUT" ./ragctl.sh validate-advanced --quiet > /dev/null 2>&1; then
            add_result "advanced_validation" "PASS" "Validación avanzada exitosa" ""
        else
            add_result "advanced_validation" "WARNING" "Validación avanzada con problemas" ""
        fi
    else
        add_result "advanced_validation" "WARNING" "Script ragctl.sh no disponible" ""
    fi
}

# Generar reporte en formato JSON
generate_json_report() {
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local overall_status="HEALTHY"
    
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        overall_status="CRITICAL"
    elif [ "$WARNING_CHECKS" -gt 0 ]; then
        overall_status="WARNING"
    fi
    
    cat << EOF
{
  "timestamp": "$timestamp",
  "overall_status": "$overall_status",
  "summary": {
    "total_checks": $TOTAL_CHECKS,
    "passed": $PASSED_CHECKS,
    "warnings": $WARNING_CHECKS,
    "failed": $FAILED_CHECKS
  },
  "checks": [
EOF

    local first=true
    for result in "${HEALTH_RESULTS[@]}"; do
        IFS='|' read -r name status message details <<< "$result"
        
        if [ "$first" = true ]; then
            first=false
        else
            echo ","
        fi
        
        cat << EOF
    {
      "name": "$name",
      "status": "$status",
      "message": "$message",
      "details": "$details"
    }
EOF
    done
    
    echo ""
    echo "  ]"
    echo "}"
}

# Generar reporte en formato texto
generate_text_report() {
    local timestamp=$(date)
    
    echo "RAG Jurídico - Health Check Report"
    echo "=================================="
    echo "Timestamp: $timestamp"
    echo ""
    
    # Resumen
    echo "📊 RESUMEN:"
    echo "  Total de verificaciones: $TOTAL_CHECKS"
    echo "  ✅ Exitosas: $PASSED_CHECKS"
    echo "  ⚠️  Advertencias: $WARNING_CHECKS"
    echo "  ❌ Fallos: $FAILED_CHECKS"
    echo ""
    
    # Estado general
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        echo -e "🔴 Estado general: ${RED}CRÍTICO${NC}"
    elif [ "$WARNING_CHECKS" -gt 0 ]; then
        echo -e "🟡 Estado general: ${YELLOW}ADVERTENCIA${NC}"
    else
        echo -e "🟢 Estado general: ${GREEN}SALUDABLE${NC}"
    fi
    echo ""
    
    # Detalles de verificaciones
    echo "📋 DETALLES:"
    for result in "${HEALTH_RESULTS[@]}"; do
        IFS='|' read -r name status message details <<< "$result"
        
        case "$status" in
            "PASS")
                echo -e "  ✅ $name: $message"
                ;;
            "WARNING")
                echo -e "  ⚠️  $name: $message"
                ;;
            "FAIL")
                echo -e "  ❌ $name: $message"
                ;;
        esac
    done
}

# Función principal
main() {
    # Procesar argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -j|--json)
                OUTPUT_JSON=true
                shift
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            -h|--help)
                echo "Health Check Script - RAG Jurídico"
                echo ""
                echo "Uso: $0 [opciones]"
                echo ""
                echo "Opciones:"
                echo "  -v, --verbose    Output detallado"
                echo "  -j, --json       Output en formato JSON"
                echo "  -t, --timeout N  Timeout para verificaciones (default: 30s)"
                echo "  -h, --help       Mostrar esta ayuda"
                exit 0
                ;;
            *)
                error "Opción desconocida: $1"
                exit 1
                ;;
        esac
    done
    
    # Crear directorio para alertas si no existe
    mkdir -p "$(dirname "$ALERTS_FILE")"
    
    if [ "$VERBOSE" = true ] && [ "$OUTPUT_JSON" = false ]; then
        echo "🏥 Iniciando verificación de salud del sistema RAG Jurídico..."
        echo ""
    fi
    
    # Ejecutar todas las verificaciones
    check_docker
    check_containers
    check_network_services
    check_system_resources
    check_file_structure
    check_logs
    check_advanced_validation
    
    # Generar reporte
    if [ "$OUTPUT_JSON" = true ]; then
        generate_json_report
    else
        generate_text_report
    fi
    
    # Determinar código de salida
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        exit 2  # Crítico
    elif [ "$WARNING_CHECKS" -gt 0 ]; then
        exit 1  # Advertencias
    else
        exit 0  # Saludable
    fi
}

# Verificar que tenemos las herramientas básicas
if ! command -v curl &> /dev/null; then
    error "curl no está instalado, necesario para verificaciones de red"
    exit 1
fi

# Ejecutar función principal
main "$@"