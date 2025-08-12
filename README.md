# RAG Jurídico - Sistema de Recuperación y Generación Aumentada para Contenido Legal

## 🚀 Descripción del Proyecto

El **RAG Jurídico** es un sistema avanzado de Recuperación y Generación Aumentada (RAG) especializado en contenido legal mexicano. Utiliza técnicas de procesamiento de lenguaje natural, embeddings semánticos y modelos de lenguaje grandes para proporcionar respuestas precisas y fundamentadas a consultas jurídicas.

### ✨ Características Principales

- **🔍 Búsqueda Semántica Avanzada**: Utiliza embeddings para encontrar documentos legales relevantes
- **🧠 Generación Inteligente**: Respuestas fundamentadas con referencias legales específicas
- **⚖️ Validación Jurídica**: Sistema de validación especializado para contenido legal
- **🔒 Anti-Sesgo**: Mecanismos para reducir sesgos en respuestas de múltiple opción
- **📊 Monitoreo Completo**: Sistema integral de validación y métricas
- **🐳 Containerizado**: Fácil despliegue con Docker y orquestación
- **🔧 CLI Avanzado**: Herramientas de línea de comandos completas

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                         RAG JURÍDICO                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Ingest    │    │   Vector    │    │   Generate  │         │
│  │   Pipeline  │───▶│   Store     │───▶│   Response  │         │
│  │             │    │  (Qdrant)   │    │  (Ollama)   │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   OCR &     │    │ Embedding   │    │ Validation  │         │
│  │   PDF       │    │ Validation  │    │ System      │         │
│  │ Processing  │    │             │    │             │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    Management Layer                            │
├─────────────────────────────────────────────────────────────────┤
│              ragctl.sh - Unified CLI Interface                 │
└─────────────────────────────────────────────────────────────────┘
```

## 🛠️ Instalación y Configuración

### Prerrequisitos

- Docker y Docker Compose
- Git
- Al menos 8GB de RAM
- 20GB de espacio en disco libre

### 1. Clonar el Repositorio

```bash
git clone https://github.com/fer78mo/prueba1.git
cd prueba1
```

### 2. Configurar Variables de Entorno

```bash
cp .env.example .env
# Editar .env con tus configuraciones específicas
```

### 3. Construir y Ejecutar con Docker Compose

```bash
# Construcción y ejecución
docker-compose up -d

# Verificar estado de servicios
./ragctl.sh status
```

### 4. Configuración Inicial

```bash
# Configurar sistema para máxima robustez
./ragctl.sh configure-robust

# Ejecutar validación completa
./ragctl.sh validate-advanced --verbose

# Indexar corpus legal inicial
./ragctl.sh reindex --all
```

## 📚 Guía de Uso

### Sistema de Validación Avanzado

```bash
# Validación completa del sistema
./ragctl.sh validate-advanced --verbose

# Validación específica de configuración
./ragctl.sh validate-advanced --config-only

# Validación de calidad de embeddings
./ragctl.sh validate-advanced --embeddings-only --collection juridico

# Validación de contenido legal
./ragctl.sh validate-advanced --legal-only --sample-file data/sample.json

# Validación de performance del sistema
./ragctl.sh validate-advanced --system-only

# Guardar reporte de validación
./ragctl.sh validate-advanced --output reports/validation_$(date +%Y%m%d).json
```

### Procesamiento de Preguntas

```bash
# Pregunta individual desde archivo
./ragctl.sh ask --file data/preguntas/mi_pregunta.txt

# Procesamiento en lote con validación
./ragctl.sh run-batch --dir data/preguntas --validate --max 50

# Validación tradicional mejorada
./ragctl.sh validate --advanced --dir data/preguntas --max 100
```

### Monitoreo y Mantenimiento

```bash
# Estado de servicios
./ragctl.sh status

# Métricas del sistema
./ragctl.sh metrics --json

# Logs del sistema
./ragctl.sh logs --tail 200

# Limpiar vectores huérfanos
./ragctl.sh gc --force
```

## 🔍 Sistema de Validación Avanzado

El sistema incluye un framework completo de validación con múltiples dimensiones:

### Validación de Configuración
- ✅ Variables de entorno críticas
- ✅ Conexiones con servicios externos
- ✅ Estructura de directorios
- ✅ Espacio en disco disponible

### Validación Legal
- ⚖️ Referencias legales específicas (artículos, fracciones)
- ⚖️ Terminología jurídica apropiada
- ⚖️ Estructura argumentativa
- ⚖️ Formato de citaciones
- ⚖️ Coherencia pregunta-respuesta

### Validación de Embeddings
- 🔍 Existencia y configuración de colecciones
- 🔍 Dimensiones y calidad de vectores
- 🔍 Consistencia del retrieval
- 🔍 Salud de índices vectoriales

### Validación de Sistema
- 🖥️ Uso de CPU, memoria y disco
- 🖥️ Tiempo de respuesta y throughput
- 🖥️ Disponibilidad de servicios
- 🖥️ Salud de logs del sistema

## 🧪 Testing

```bash
# Tests del sistema de validación
python tests/validation_tests.py

# Test específico
python tests/validation_tests.py --test-class TestLegalValidator

# Validación completa desde contenedor
./ragctl.sh validate-advanced --verbose
```

## 🐳 Docker y Desarrollo

### Servicios Docker

- **app-rag**: Aplicación principal Python
- **ia_qdrant**: Base de datos vectorial
- **ia_ollama_1**: Motor de LLM

### Variables de Entorno Importantes

```env
# Configuración Anti-Sesgo
ANTI_BIAS_MODE=true
MC_VALIDATION_PASSES=3
MIN_CONFIDENCE_THRESHOLD=0.6
FALLBACK_RETRIEVAL=true

# Servicios
QDRANT_HOST=ia_qdrant
QDRANT_PORT=6333
OLLAMA_HOST=ia_ollama_1
OLLAMA_PORT=11434

# Validación
VALIDATION_DETAILED_LOGGING=true
HIGHLIGHT_IN_OUTPUT=true
```

## 📊 Métricas y Reportes

### Métricas de Calidad Legal

El sistema evalúa automáticamente:

- **Precisión Jurídica**: Referencias específicas a artículos, códigos y leyes
- **Fundamentación**: Uso de conectores argumentativos jurídicos
- **Terminología**: Empleo correcto de términos legales especializados
- **Coherencia**: Correspondencia entre pregunta y respuesta
- **Citación**: Formato apropiado de referencias legales

## 🆘 Solución de Problemas

### Problemas Comunes

**Error: "Cliente Qdrant no disponible"**
```bash
# Verificar estado de Qdrant
docker-compose ps ia_qdrant
./ragctl.sh status

# Reiniciar servicio
docker-compose restart ia_qdrant
```

**Error: "Colección no existe"**
```bash
# Verificar colecciones disponibles
./ragctl.sh validate-advanced --embeddings-only

# Reindexar corpus
./ragctl.sh reindex --all --force
```

**Performance degradada**
```bash
# Verificar recursos del sistema
./ragctl.sh validate-advanced --system-only

# Limpiar vectores huérfanos
./ragctl.sh gc --force
```

### Información del Sistema

```bash
# Versiones y configuración
./ragctl.sh versions

# Estado completo del sistema  
./ragctl.sh validate-advanced --verbose

# Generar reporte para soporte
./ragctl.sh validate-advanced --output support_report_$(date +%Y%m%d).json
```

---

## 📄 Licencia

Este proyecto está licenciado bajo los términos especificados en el archivo LICENSE.

---

*Para más información y actualizaciones, visita el [repositorio del proyecto](https://github.com/fer78mo/prueba1).*