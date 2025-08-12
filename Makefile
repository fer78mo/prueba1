# Makefile para RAG Jurídico
# ========================================================================================

.PHONY: help build up down logs status clean install test validate docs dev prod

# Variables
COMPOSE_FILE = docker-compose.yml
CONTAINER_NAME = app-rag
PROJECT_NAME = rag-juridico

# Comandos por defecto
help: ## Mostrar esta ayuda
	@echo "RAG Jurídico - Comandos disponibles:"
	@echo "=================================="
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ========================================================================================
# COMANDOS DE DESARROLLO
# ========================================================================================

install: ## Instalar dependencias
	@echo "📦 Instalando dependencias..."
	pip install -r requirements.txt
	@echo "✅ Dependencias instaladas"

dev-install: ## Instalar dependencias de desarrollo
	@echo "📦 Instalando dependencias de desarrollo..."
	pip install -r requirements.txt
	pip install black flake8 mypy pytest pytest-cov
	@echo "✅ Dependencias de desarrollo instaladas"

setup: ## Configuración inicial del proyecto
	@echo "🚀 Configurando proyecto RAG Jurídico..."
	@if [ ! -f .env ]; then cp .env.example .env && echo "📋 Archivo .env creado desde .env.example"; fi
	@mkdir -p output/{logs,validate,validate_txt} reports cache
	@echo "📁 Directorios creados"
	@echo "✅ Configuración inicial completada"

# ========================================================================================
# COMANDOS DE DOCKER
# ========================================================================================

build: ## Construir contenedores
	@echo "🏗️  Construyendo contenedores..."
	docker-compose -f $(COMPOSE_FILE) build --no-cache
	@echo "✅ Contenedores construidos"

up: ## Levantar servicios
	@echo "🚀 Levantando servicios..."
	docker-compose -f $(COMPOSE_FILE) up -d
	@echo "✅ Servicios levantados"

up-full: ## Levantar servicios completos (con PostgreSQL, Redis, Elasticsearch)
	@echo "🚀 Levantando servicios completos..."
	docker-compose -f $(COMPOSE_FILE) --profile full up -d
	@echo "✅ Servicios completos levantados"

down: ## Bajar servicios
	@echo "⏹️  Bajando servicios..."
	docker-compose -f $(COMPOSE_FILE) down
	@echo "✅ Servicios bajados"

down-volumes: ## Bajar servicios y eliminar volúmenes
	@echo "⏹️  Bajando servicios y eliminando volúmenes..."
	docker-compose -f $(COMPOSE_FILE) down -v
	@echo "✅ Servicios bajados y volúmenes eliminados"

restart: ## Reiniciar servicios
	@echo "🔄 Reiniciando servicios..."
	docker-compose -f $(COMPOSE_FILE) restart
	@echo "✅ Servicios reiniciados"

# ========================================================================================
# COMANDOS DE MONITOREO
# ========================================================================================

status: ## Estado de servicios
	@echo "📊 Estado de servicios:"
	@docker-compose -f $(COMPOSE_FILE) ps
	@echo ""
	@echo "🔍 Validación de estado:"
	@./ragctl.sh status

logs: ## Ver logs de todos los servicios
	docker-compose -f $(COMPOSE_FILE) logs -f

logs-app: ## Ver logs de la aplicación
	docker-compose -f $(COMPOSE_FILE) logs -f $(CONTAINER_NAME)

logs-qdrant: ## Ver logs de Qdrant
	docker-compose -f $(COMPOSE_FILE) logs -f ia_qdrant

logs-ollama: ## Ver logs de Ollama
	docker-compose -f $(COMPOSE_FILE) logs -f ia_ollama_1

# ========================================================================================
# COMANDOS DE VALIDACIÓN Y TESTING
# ========================================================================================

validate: ## Ejecutar validación completa del sistema
	@echo "🔍 Ejecutando validación completa..."
	@./ragctl.sh validate-advanced --verbose
	@echo "✅ Validación completada"

validate-config: ## Validar solo configuración
	@echo "🔧 Validando configuración..."
	@./ragctl.sh validate-advanced --config-only --verbose

validate-system: ## Validar solo sistema
	@echo "🖥️  Validando sistema..."
	@./ragctl.sh validate-advanced --system-only --verbose

validate-embeddings: ## Validar solo embeddings
	@echo "🔍 Validando embeddings..."
	@./ragctl.sh validate-advanced --embeddings-only --verbose

validate-legal: ## Validar solo contenido legal
	@echo "⚖️  Validando contenido legal..."
	@./ragctl.sh validate-advanced --legal-only --verbose

test: ## Ejecutar tests
	@echo "🧪 Ejecutando tests..."
	@if [ -f pytest.ini ]; then \
		pytest tests/ -v; \
	else \
		python -m pytest tests/ -v; \
	fi

test-validation: ## Ejecutar tests de validación específicamente
	@echo "🧪 Ejecutando tests de validación..."
	@python tests/validation_tests.py --verbose

# ========================================================================================
# COMANDOS DE RAG
# ========================================================================================

reindex: ## Reindexar corpus completo
	@echo "📚 Reindexando corpus..."
	@./ragctl.sh reindex --all --force
	@echo "✅ Corpus reindexado"

configure-robust: ## Configurar sistema para máxima robustez
	@echo "🔧 Configurando sistema robusto..."
	@./ragctl.sh configure-robust
	@echo "✅ Sistema configurado"

process-questions: ## Procesar preguntas de prueba
	@echo "❓ Procesando preguntas..."
	@./ragctl.sh run-batch --dir data/preguntas --max 10 --validate
	@echo "✅ Preguntas procesadas"

# ========================================================================================
# COMANDOS DE MANTENIMIENTO
# ========================================================================================

clean: ## Limpiar contenedores y volúmenes no utilizados
	@echo "🧹 Limpiando Docker..."
	docker system prune -f
	docker volume prune -f
	@echo "✅ Limpieza completada"

clean-all: ## Limpiar todo (CUIDADO: elimina todos los datos)
	@echo "⚠️  CUIDADO: Esto eliminará todos los datos"
	@read -p "¿Estás seguro? (y/N): " confirm && [ "$$confirm" = "y" ]
	docker-compose -f $(COMPOSE_FILE) down -v
	docker system prune -af
	docker volume prune -f
	@echo "✅ Limpieza completa realizada"

gc: ## Limpiar vectores huérfanos
	@echo "🧹 Limpiando vectores huérfanos..."
	@./ragctl.sh gc --force
	@echo "✅ Vectores huérfanos limpiados"

backup: ## Crear backup de datos
	@echo "💾 Creando backup..."
	@mkdir -p backup/$(shell date +%Y%m%d_%H%M%S)
	@docker-compose -f $(COMPOSE_FILE) exec -T ia_qdrant tar czf - /qdrant/storage > backup/$(shell date +%Y%m%d_%H%M%S)/qdrant_backup.tar.gz
	@echo "✅ Backup creado en backup/$(shell date +%Y%m%d_%H%M%S)/"

# ========================================================================================
# COMANDOS DE DESARROLLO AVANZADO
# ========================================================================================

shell: ## Acceder al shell del contenedor principal
	docker-compose -f $(COMPOSE_FILE) exec $(CONTAINER_NAME) bash

shell-qdrant: ## Acceder al shell de Qdrant
	docker-compose -f $(COMPOSE_FILE) exec ia_qdrant sh

format: ## Formatear código con black
	@echo "🎨 Formateando código..."
	black app/ scripts/ tests/ --line-length 100
	@echo "✅ Código formateado"

lint: ## Ejecutar linter
	@echo "🔍 Ejecutando linter..."
	flake8 app/ scripts/ tests/ --max-line-length=100 --extend-ignore=E203,W503
	@echo "✅ Linting completado"

type-check: ## Verificar tipos con mypy
	@echo "🔍 Verificando tipos..."
	mypy app/ scripts/ --ignore-missing-imports
	@echo "✅ Verificación de tipos completada"

quality: format lint type-check test ## Ejecutar todas las verificaciones de calidad

# ========================================================================================
# COMANDOS DE REPORTING
# ========================================================================================

report: ## Generar reporte completo del sistema
	@echo "📊 Generando reporte completo..."
	@mkdir -p reports
	@./ragctl.sh validate-advanced --output reports/system_report_$(shell date +%Y%m%d_%H%M%S).json --verbose
	@echo "✅ Reporte generado en reports/"

metrics: ## Mostrar métricas del sistema
	@echo "📈 Métricas del sistema:"
	@./ragctl.sh metrics --json

health: ## Verificar salud completa del sistema
	@echo "🏥 Verificando salud del sistema..."
	@./ragctl.sh validate-advanced --quiet
	@if [ $$? -eq 0 ]; then \
		echo "✅ Sistema saludable"; \
	else \
		echo "❌ Sistema con problemas"; \
		exit 1; \
	fi

# ========================================================================================
# COMANDOS DE DOCUMENTACIÓN
# ========================================================================================

docs: ## Generar documentación
	@echo "📚 Generando documentación..."
	@if command -v sphinx-build >/dev/null 2>&1; then \
		sphinx-build -b html docs/ docs/_build/html; \
		echo "✅ Documentación generada en docs/_build/html/"; \
	else \
		echo "⚠️  Sphinx no instalado. Instalando..."; \
		pip install sphinx sphinx-rtd-theme; \
		echo "📚 Documentación básica disponible en README.md"; \
	fi

# ========================================================================================
# COMANDOS DE PRODUCCIÓN
# ========================================================================================

prod-build: ## Construir para producción
	@echo "🏭 Construyendo para producción..."
	docker-compose -f $(COMPOSE_FILE) build --no-cache
	@echo "✅ Build de producción completado"

prod-deploy: ## Desplegar en producción
	@echo "🚀 Desplegando en producción..."
	docker-compose -f $(COMPOSE_FILE) up -d --remove-orphans
	@sleep 10
	@$(MAKE) health
	@echo "✅ Despliegue de producción completado"

prod-update: ## Actualizar sistema en producción
	@echo "🔄 Actualizando sistema..."
	docker-compose -f $(COMPOSE_FILE) pull
	docker-compose -f $(COMPOSE_FILE) up -d --remove-orphans
	@sleep 10
	@$(MAKE) health
	@echo "✅ Sistema actualizado"

# ========================================================================================
# COMANDOS DE INFORMACIÓN
# ========================================================================================

info: ## Mostrar información del sistema
	@echo "ℹ️  Información del Sistema RAG Jurídico"
	@echo "========================================"
	@echo "Proyecto: $(PROJECT_NAME)"
	@echo "Compose: $(COMPOSE_FILE)"
	@echo "Contenedor: $(CONTAINER_NAME)"
	@echo ""
	@echo "Servicios configurados:"
	@docker-compose -f $(COMPOSE_FILE) config --services
	@echo ""
	@echo "Volúmenes:"
	@docker volume ls --filter name=$(PROJECT_NAME) --format "table {{.Name}}\t{{.Driver}}\t{{.Labels}}"

version: ## Mostrar versiones
	@echo "📋 Versiones del sistema:"
	@echo "Docker: $$(docker --version)"
	@echo "Docker Compose: $$(docker-compose --version)"
	@echo "Python: $$(python --version 2>&1)"
	@if [ -f ragctl.sh ]; then \
		echo "RAG Jurídico: $$(grep 'v[0-9]' ragctl.sh | head -1 | sed 's/.*v\([0-9.]*\).*/\1/')"; \
	fi

# ========================================================================================
# Comandos de desarrollo rápido
# ========================================================================================

dev: setup build up configure-robust validate ## Configuración completa de desarrollo
	@echo "✅ Entorno de desarrollo listo"

quick: up validate-config ## Inicio rápido para desarrollo
	@echo "✅ Inicio rápido completado"

# ========================================================================================
# REGLAS ESPECIALES
# ========================================================================================

# Prevenir ejecución accidental de clean-all
.PHONY: confirm-clean-all
confirm-clean-all:
	@echo "⚠️  CUIDADO: Esto eliminará TODOS los datos del proyecto"
	@echo "Esto incluye:"
	@echo "  - Todos los contenedores Docker"
	@echo "  - Todos los volúmenes de datos"
	@echo "  - Todos los vectores en Qdrant"
	@echo "  - Todos los modelos en Ollama"
	@read -p "Escribe 'DELETE_ALL' para confirmar: " confirm && [ "$$confirm" = "DELETE_ALL" ]