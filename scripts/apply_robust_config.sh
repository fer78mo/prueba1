#!/bin/bash

# Script para aplicar configuraciones de robustez
echo "🔧 Aplicando configuraciones de robustez..."

# Cargar configuraciones anti-sesgo
if [ -f "/app/config/anti_bias.env" ]; then
    source /app/config/anti_bias.env
    echo "✅ Configuraciones anti-sesgo cargadas"
else
    echo "⚠️  Archivo de configuración no encontrado, usando valores por defecto"
    export ANTI_BIAS_MODE=true
    export MC_VALIDATION_PASSES=3
    export MIN_CONFIDENCE_THRESHOLD=0.6
    export FALLBACK_RETRIEVAL=true
fi

# Crear backup de configuración actual
timestamp=$(date +%Y%m%d_%H%M%S)
mkdir -p /app/backup/configs
env | grep -E "(ANTI_BIAS|MC_VALIDATION|MIN_CONFIDENCE|FALLBACK)" > "/app/backup/configs/config_${timestamp}.env"

echo "📊 Configuraciones activas:"
echo "  ANTI_BIAS_MODE: $ANTI_BIAS_MODE"
echo "  MC_VALIDATION_PASSES: $MC_VALIDATION_PASSES"
echo "  MIN_CONFIDENCE_THRESHOLD: $MIN_CONFIDENCE_THRESHOLD"
echo "  FALLBACK_RETRIEVAL: $FALLBACK_RETRIEVAL"

echo "🚀 Sistema configurado para máxima robustez"
