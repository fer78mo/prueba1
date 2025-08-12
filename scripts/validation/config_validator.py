#!/usr/bin/env python3
"""
Validador de Configuración para RAG Jurídico

Valida la configuración del sistema, conexiones a servicios externos,
y variables de entorno necesarias.
"""

import os
import requests
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

@dataclass
class ConfigValidationResult:
    """Resultado de validación de configuración"""
    component: str
    status: str  # 'ok', 'warning', 'error'
    message: str
    details: Optional[Dict] = None

class ConfigValidator:
    """Validador de configuración del sistema"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.results = []
    
    def validate_environment_variables(self) -> List[ConfigValidationResult]:
        """Valida variables de entorno requeridas"""
        results = []
        
        # Variables críticas
        critical_vars = [
            'QDRANT_HOST', 'QDRANT_PORT',
            'OLLAMA_HOST', 'OLLAMA_PORT'
        ]
        
        # Variables opcionales con valores por defecto
        optional_vars = {
            'ANTI_BIAS_MODE': 'true',
            'MC_VALIDATION_PASSES': '3',
            'MIN_CONFIDENCE_THRESHOLD': '0.6',
            'FALLBACK_RETRIEVAL': 'true'
        }
        
        # Validar variables críticas
        for var in critical_vars:
            value = os.getenv(var)
            if not value:
                results.append(ConfigValidationResult(
                    component=f"env_var_{var}",
                    status='error',
                    message=f"Variable de entorno {var} no está definida",
                    details={'variable': var, 'required': True}
                ))
            else:
                results.append(ConfigValidationResult(
                    component=f"env_var_{var}",
                    status='ok',
                    message=f"Variable {var} configurada correctamente",
                    details={'variable': var, 'value': value}
                ))
        
        # Validar variables opcionales
        for var, default in optional_vars.items():
            value = os.getenv(var, default)
            results.append(ConfigValidationResult(
                component=f"env_var_{var}",
                status='ok',
                message=f"Variable {var} configurada (valor: {value})",
                details={'variable': var, 'value': value, 'default': default}
            ))
            
        return results
    
    def validate_qdrant_connection(self) -> ConfigValidationResult:
        """Valida conexión con Qdrant"""
        try:
            qdrant_host = os.getenv('QDRANT_HOST', 'ia_qdrant')
            qdrant_port = os.getenv('QDRANT_PORT', '6333')
            url = f"http://{qdrant_host}:{qdrant_port}/readyz"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                return ConfigValidationResult(
                    component='qdrant_connection',
                    status='ok',
                    message='Conexión con Qdrant exitosa',
                    details={'url': url, 'status_code': response.status_code}
                )
            else:
                return ConfigValidationResult(
                    component='qdrant_connection',
                    status='error',
                    message=f'Qdrant respondió con código {response.status_code}',
                    details={'url': url, 'status_code': response.status_code}
                )
                
        except requests.exceptions.RequestException as e:
            return ConfigValidationResult(
                component='qdrant_connection',
                status='error',
                message=f'Error conectando con Qdrant: {str(e)}',
                details={'error': str(e), 'url': url}
            )
    
    def validate_ollama_connection(self) -> ConfigValidationResult:
        """Valida conexión con Ollama"""
        try:
            ollama_host = os.getenv('OLLAMA_HOST', 'ia_ollama_1')
            ollama_port = os.getenv('OLLAMA_PORT', '11434')
            url = f"http://{ollama_host}:{ollama_port}/api/tags"
            
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                models = response.json().get('models', [])
                return ConfigValidationResult(
                    component='ollama_connection',
                    status='ok',
                    message=f'Conexión con Ollama exitosa. Modelos disponibles: {len(models)}',
                    details={'url': url, 'models_count': len(models), 'models': [m.get('name', 'unknown') for m in models[:5]]}
                )
            else:
                return ConfigValidationResult(
                    component='ollama_connection',
                    status='error',
                    message=f'Ollama respondió con código {response.status_code}',
                    details={'url': url, 'status_code': response.status_code}
                )
                
        except requests.exceptions.RequestException as e:
            return ConfigValidationResult(
                component='ollama_connection',
                status='error',
                message=f'Error conectando con Ollama: {str(e)}',
                details={'error': str(e), 'url': url}
            )
    
    def validate_directory_structure(self) -> List[ConfigValidationResult]:
        """Valida estructura de directorios requerida"""
        results = []
        
        required_dirs = [
            '/app/data',
            '/app/output',
            '/app/output/logs',
            '/app/output/validate',
            '/app/output/validate_txt'
        ]
        
        for dir_path in required_dirs:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                # Verificar permisos de escritura
                if os.access(dir_path, os.W_OK):
                    results.append(ConfigValidationResult(
                        component=f"directory_{dir_path.replace('/', '_')}",
                        status='ok',
                        message=f"Directorio {dir_path} existe y es escribible",
                        details={'path': dir_path, 'writable': True}
                    ))
                else:
                    results.append(ConfigValidationResult(
                        component=f"directory_{dir_path.replace('/', '_')}",
                        status='warning',
                        message=f"Directorio {dir_path} existe pero no es escribible",
                        details={'path': dir_path, 'writable': False}
                    ))
            else:
                results.append(ConfigValidationResult(
                    component=f"directory_{dir_path.replace('/', '_')}",
                    status='error',
                    message=f"Directorio requerido {dir_path} no existe",
                    details={'path': dir_path, 'exists': False}
                ))
        
        return results
    
    def validate_disk_space(self) -> ConfigValidationResult:
        """Valida espacio en disco disponible"""
        try:
            import shutil
            
            # Verificar espacio en /app (donde está la aplicación)
            total, used, free = shutil.disk_usage('/app')
            
            # Convertir a GB
            free_gb = free // (1024**3)
            total_gb = total // (1024**3)
            used_gb = used // (1024**3)
            
            # Considerar crítico si hay menos de 1GB libre
            if free_gb < 1:
                status = 'error'
                message = f"Espacio en disco crítico: {free_gb}GB libres de {total_gb}GB"
            elif free_gb < 5:
                status = 'warning'
                message = f"Espacio en disco bajo: {free_gb}GB libres de {total_gb}GB"
            else:
                status = 'ok'
                message = f"Espacio en disco suficiente: {free_gb}GB libres de {total_gb}GB"
            
            return ConfigValidationResult(
                component='disk_space',
                status=status,
                message=message,
                details={
                    'total_gb': total_gb,
                    'used_gb': used_gb,
                    'free_gb': free_gb,
                    'usage_percent': round((used_gb / total_gb) * 100, 2)
                }
            )
            
        except Exception as e:
            return ConfigValidationResult(
                component='disk_space',
                status='error',
                message=f"Error verificando espacio en disco: {str(e)}",
                details={'error': str(e)}
            )
    
    def run_all_validations(self) -> List[ConfigValidationResult]:
        """Ejecuta todas las validaciones de configuración"""
        all_results = []
        
        # Validar variables de entorno
        all_results.extend(self.validate_environment_variables())
        
        # Validar conexiones
        all_results.append(self.validate_qdrant_connection())
        all_results.append(self.validate_ollama_connection())
        
        # Validar estructura de directorios
        all_results.extend(self.validate_directory_structure())
        
        # Validar espacio en disco
        all_results.append(self.validate_disk_space())
        
        self.results = all_results
        return all_results
    
    def get_summary(self) -> Dict[str, int]:
        """Obtiene resumen de resultados"""
        if not self.results:
            return {'total': 0, 'ok': 0, 'warning': 0, 'error': 0}
        
        summary = {'total': len(self.results), 'ok': 0, 'warning': 0, 'error': 0}
        
        for result in self.results:
            summary[result.status] += 1
            
        return summary
    
    def print_results(self, verbose: bool = False):
        """Imprime resultados de validación"""
        if not self.results:
            print("❌ No hay resultados de validación")
            return
        
        summary = self.get_summary()
        
        print(f"\n🔧 Validación de Configuración - Resumen:")
        print(f"   Total: {summary['total']}")
        print(f"   ✅ OK: {summary['ok']}")
        print(f"   ⚠️  Advertencias: {summary['warning']}")
        print(f"   ❌ Errores: {summary['error']}")
        print()
        
        # Agrupar por estado
        for status in ['error', 'warning', 'ok']:
            results_for_status = [r for r in self.results if r.status == status]
            
            if not results_for_status:
                continue
                
            status_emoji = {'ok': '✅', 'warning': '⚠️', 'error': '❌'}[status]
            print(f"{status_emoji} {status.upper()}:")
            
            for result in results_for_status:
                print(f"   • {result.message}")
                if verbose and result.details:
                    print(f"     Detalles: {result.details}")
            print()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validador de configuración RAG Jurídico")
    parser.add_argument('--verbose', '-v', action='store_true', help='Mostrar detalles adicionales')
    
    args = parser.parse_args()
    
    validator = ConfigValidator()
    validator.run_all_validations()
    validator.print_results(verbose=args.verbose)
    
    # Exit con código de error si hay errores críticos
    summary = validator.get_summary()
    if summary['error'] > 0:
        exit(1)