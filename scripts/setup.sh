#!/bin/bash
# =============================================================================
# Script de Configuración Inicial - RAG Jurídico
# =============================================================================
# 
# Este script configura el entorno completo para el sistema RAG Jurídico
# Ejecutar después de clonar el repositorio

set -euo pipefail  # Salir en error, variables undefined, pipe errors

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Funciones de utilidad
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Variables
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"

# Función para verificar prerrequisitos
check_prerequisites() {
    log "🔍 Verificando prerrequisitos..."
    
    # Verificar Docker
    if ! command -v docker &> /dev/null; then
        error "Docker no está instalado. Instala Docker Desktop desde https://docker.com"
    fi
    
    # Verificar Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose no está instalado."
    fi
    
    # Verificar que Docker esté corriendo
    if ! docker info &> /dev/null; then
        error "Docker no está corriendo. Inicia Docker Desktop."
    fi
    
    # Verificar espacio en disco (al menos 10GB)
    available_space=$(df / | awk 'NR==2 {print $4}')
    required_space=$((10 * 1024 * 1024))  # 10GB en KB
    
    if [ "$available_space" -lt "$required_space" ]; then
        warn "Espacio en disco limitado. Recomendado: al menos 10GB libres"
    fi
    
    # Verificar RAM disponible (al menos 8GB)
    if command -v free &> /dev/null; then
        available_ram=$(free -g | awk 'NR==2{print $7}')
        if [ "$available_ram" -lt 6 ]; then
            warn "RAM limitada. Recomendado: al menos 8GB de RAM"
        fi
    fi
    
    info "✅ Prerrequisitos verificados"
}

# Función para configurar estructura de directorios
setup_directories() {
    log "📁 Configurando estructura de directorios..."
    
    # Directorios necesarios
    directories=(
        "output"
        "output/logs"
        "output/validate"
        "output/validate_txt"
        "reports"
        "cache"
        "config"
        "backup"
        "data/temp"
        "data/cache"
    )
    
    for dir in "${directories[@]}"; do
        mkdir -p "$PROJECT_ROOT/$dir"
        info "📂 Creado: $dir"
    done
    
    # Crear archivos .gitkeep para directorios que deben persistir en git
    touch "$PROJECT_ROOT/output/.gitkeep"
    touch "$PROJECT_ROOT/reports/.gitkeep"
    touch "$PROJECT_ROOT/cache/.gitkeep"
    
    info "✅ Estructura de directorios configurada"
}

# Función para configurar variables de entorno
setup_environment() {
    log "🔧 Configurando variables de entorno..."
    
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
            info "📋 Archivo .env creado desde .env.example"
        else
            error "Archivo .env.example no encontrado"
        fi
    else
        warn "Archivo .env ya existe, no se sobrescribe"
    fi
    
    # Verificar variables críticas
    if ! grep -q "QDRANT_HOST" "$ENV_FILE"; then
        echo "QDRANT_HOST=ia_qdrant" >> "$ENV_FILE"
    fi
    
    if ! grep -q "OLLAMA_HOST" "$ENV_FILE"; then
        echo "OLLAMA_HOST=ia_ollama_1" >> "$ENV_FILE"
    fi
    
    info "✅ Variables de entorno configuradas"
}

# Función para configurar permisos
setup_permissions() {
    log "🔐 Configurando permisos..."
    
    # Hacer ejecutables los scripts principales
    chmod +x "$PROJECT_ROOT/ragctl.sh"
    chmod +x "$PROJECT_ROOT/scripts/setup.sh" 2>/dev/null || true
    chmod +x "$PROJECT_ROOT/scripts/health_check.sh" 2>/dev/null || true
    
    # Configurar permisos de directorios
    chmod 755 "$PROJECT_ROOT/output"
    chmod 755 "$PROJECT_ROOT/reports"
    chmod 755 "$PROJECT_ROOT/cache"
    
    info "✅ Permisos configurados"
}

# Función para verificar archivos de configuración
verify_config_files() {
    log "📋 Verificando archivos de configuración..."
    
    required_files=(
        "docker-compose.yml"
        "ragctl.sh"
        ".env"
        "requirements.txt"
        ".gitignore"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$PROJECT_ROOT/$file" ]; then
            error "Archivo requerido no encontrado: $file"
        else
            info "✅ $file encontrado"
        fi
    done
}

# Función para construir contenedores
build_containers() {
    log "🏗️  Construyendo contenedores Docker..."
    
    cd "$PROJECT_ROOT"
    
    # Construir contenedores
    if docker-compose -f "$COMPOSE_FILE" build --no-cache; then
        info "✅ Contenedores construidos exitosamente"
    else
        error "Fallo al construir contenedores"
    fi
}

# Función para levantar servicios
start_services() {
    log "🚀 Levantando servicios..."
    
    cd "$PROJECT_ROOT"
    
    # Levantar servicios básicos
    if docker-compose -f "$COMPOSE_FILE" up -d; then
        info "✅ Servicios levantados"
    else
        error "Fallo al levantar servicios"
    fi
    
    # Esperar a que los servicios estén listos
    info "⏳ Esperando a que los servicios estén listos..."
    sleep 30
    
    # Verificar estado de servicios
    if docker-compose -f "$COMPOSE_FILE" ps; then
        info "📊 Estado de servicios mostrado"
    fi
}

# Función para configuración inicial de la aplicación
initial_app_config() {
    log "⚙️  Configuración inicial de la aplicación..."
    
    cd "$PROJECT_ROOT"
    
    # Configurar sistema robusto
    info "🔧 Configurando sistema para máxima robustez..."
    if ./ragctl.sh configure-robust; then
        info "✅ Sistema robusto configurado"
    else
        warn "Advertencia: No se pudo configurar sistema robusto (normal si es la primera vez)"
    fi
    
    # Ejecutar validación inicial
    info "🔍 Ejecutando validación inicial..."
    if ./ragctl.sh validate-advanced --config-only; then
        info "✅ Validación de configuración exitosa"
    else
        warn "Advertencia: Validación inicial con problemas"
    fi
}

# Función para mostrar información final
show_final_info() {
    log "🎉 Configuración completada!"
    
    echo -e "${CYAN}"
    echo "========================================"
    echo "  RAG JURÍDICO - CONFIGURACIÓN COMPLETA"
    echo "========================================"
    echo -e "${NC}"
    
    echo -e "${GREEN}✅ El sistema está configurado y listo para usar${NC}"
    echo ""
    echo -e "${YELLOW}Próximos pasos:${NC}"
    echo "1. Verificar estado: ${BLUE}./ragctl.sh status${NC}"
    echo "2. Validar sistema: ${BLUE}./ragctl.sh validate-advanced --verbose${NC}"
    echo "3. Indexar corpus: ${BLUE}./ragctl.sh reindex --all${NC}"
    echo "4. Procesar preguntas: ${BLUE}./ragctl.sh run-batch --dir data/preguntas --max 10${NC}"
    echo ""
    echo -e "${YELLOW}Comandos útiles:${NC}"
    echo "• ${BLUE}make help${NC} - Ver todos los comandos disponibles"
    echo "• ${BLUE}make dev${NC} - Configuración completa de desarrollo"
    echo "• ${BLUE}make validate${NC} - Validación completa del sistema"
    echo "• ${BLUE}make status${NC} - Estado de servicios"
    echo ""
    echo -e "${YELLOW}Documentación:${NC}"
    echo "• README.md - Documentación completa"
    echo "• .env.example - Variables de entorno disponibles"
    echo "• Makefile - Comandos de desarrollo y producción"
    echo ""
    echo -e "${CYAN}¡El sistema RAG Jurídico está listo para usar!${NC}"
}

# Función principal
main() {
    echo -e "${PURPLE}"
    echo "========================================"
    echo "  RAG JURÍDICO - SETUP INICIAL"
    echo "========================================"
    echo -e "${NC}"
    
    log "🚀 Iniciando configuración del sistema RAG Jurídico..."
    
    # Cambiar al directorio del proyecto
    cd "$PROJECT_ROOT"
    
    # Ejecutar pasos de configuración
    check_prerequisites
    setup_directories
    setup_environment
    setup_permissions
    verify_config_files
    
    # Preguntar si construir y levantar servicios
    echo ""
    read -p "¿Deseas construir y levantar los servicios Docker ahora? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        build_containers
        start_services
        initial_app_config
    else
        info "⏭️  Construcción de servicios omitida"
        echo "Para construir y levantar servicios más tarde:"
        echo "  make dev    # Configuración completa"
        echo "  make up     # Solo levantar servicios"
    fi
    
    show_final_info
}

# Manejo de errores
trap 'error "Script interrumpido"' INT TERM

# Verificar que se ejecute desde el directorio correcto
if [ ! -f "$(dirname "${BASH_SOURCE[0]}")/../ragctl.sh" ]; then
    error "Este script debe ejecutarse desde el directorio del proyecto"
fi

# Ejecutar función principal
main "$@"