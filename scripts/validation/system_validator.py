#!/usr/bin/env python3
"""
Validador de Sistema y Performance para RAG Jurídico

Valida métricas de performance, uso de recursos y throughput
del sistema RAG.
"""

import os
import time
import psutil
import json
import requests
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

@dataclass
class SystemValidationResult:
    """Resultado de validación de sistema"""
    component: str
    validation_type: str
    status: str  # 'pass', 'warning', 'fail'
    message: str
    value: float
    threshold: float
    unit: str
    details: Optional[Dict] = None

class SystemValidator:
    """Validador de sistema y performance"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Umbrales de performance
        self.thresholds = {
            'response_time_ms': 5000,  # 5 segundos máximo
            'memory_usage_percent': 80,  # 80% máximo
            'cpu_usage_percent': 85,    # 85% máximo
            'disk_usage_percent': 90,   # 90% máximo
            'throughput_qps': 1.0,      # 1 query por segundo mínimo
            'error_rate_percent': 5,    # 5% máximo de errores
        }
    
    def validate_memory_usage(self) -> SystemValidationResult:
        """Valida uso de memoria del sistema"""
        try:
            memory = psutil.virtual_memory()
            usage_percent = memory.percent
            
            if usage_percent > self.thresholds['memory_usage_percent']:
                status = 'fail'
                message = f"Uso de memoria crítico"
            elif usage_percent > self.thresholds['memory_usage_percent'] * 0.8:
                status = 'warning'
                message = f"Uso de memoria alto"
            else:
                status = 'pass'
                message = f"Uso de memoria normal"
            
            return SystemValidationResult(
                component='system',
                validation_type='memory_usage',
                status=status,
                message=message,
                value=usage_percent,
                threshold=self.thresholds['memory_usage_percent'],
                unit='%',
                details={
                    'total_gb': round(memory.total / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2),
                    'used_gb': round(memory.used / (1024**3), 2)
                }
            )
            
        except Exception as e:
            return SystemValidationResult(
                component='system',
                validation_type='memory_usage',
                status='fail',
                message=f"Error obteniendo uso de memoria: {str(e)}",
                value=0,
                threshold=self.thresholds['memory_usage_percent'],
                unit='%',
                details={'error': str(e)}
            )
    
    def validate_cpu_usage(self, interval: float = 1.0) -> SystemValidationResult:
        """Valida uso de CPU del sistema"""
        try:
            # Obtener uso de CPU promedio durante el intervalo
            cpu_percent = psutil.cpu_percent(interval=interval)
            
            if cpu_percent > self.thresholds['cpu_usage_percent']:
                status = 'fail'
                message = f"Uso de CPU crítico"
            elif cpu_percent > self.thresholds['cpu_usage_percent'] * 0.8:
                status = 'warning'
                message = f"Uso de CPU alto"
            else:
                status = 'pass'
                message = f"Uso de CPU normal"
            
            # Información adicional
            cpu_count = psutil.cpu_count()
            load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
            
            return SystemValidationResult(
                component='system',
                validation_type='cpu_usage',
                status=status,
                message=message,
                value=cpu_percent,
                threshold=self.thresholds['cpu_usage_percent'],
                unit='%',
                details={
                    'cpu_count': cpu_count,
                    'load_avg_1m': round(load_avg[0], 2),
                    'load_avg_5m': round(load_avg[1], 2),
                    'load_avg_15m': round(load_avg[2], 2)
                }
            )
            
        except Exception as e:
            return SystemValidationResult(
                component='system',
                validation_type='cpu_usage',
                status='fail',
                message=f"Error obteniendo uso de CPU: {str(e)}",
                value=0,
                threshold=self.thresholds['cpu_usage_percent'],
                unit='%',
                details={'error': str(e)}
            )
    
    def validate_disk_usage(self, path: str = '/app') -> SystemValidationResult:
        """Valida uso de disco"""
        try:
            disk_usage = psutil.disk_usage(path)
            usage_percent = (disk_usage.used / disk_usage.total) * 100
            
            if usage_percent > self.thresholds['disk_usage_percent']:
                status = 'fail'
                message = f"Uso de disco crítico"
            elif usage_percent > self.thresholds['disk_usage_percent'] * 0.8:
                status = 'warning'
                message = f"Uso de disco alto"
            else:
                status = 'pass'
                message = f"Uso de disco normal"
            
            return SystemValidationResult(
                component='system',
                validation_type='disk_usage',
                status=status,
                message=message,
                value=usage_percent,
                threshold=self.thresholds['disk_usage_percent'],
                unit='%',
                details={
                    'path': path,
                    'total_gb': round(disk_usage.total / (1024**3), 2),
                    'used_gb': round(disk_usage.used / (1024**3), 2),
                    'free_gb': round(disk_usage.free / (1024**3), 2)
                }
            )
            
        except Exception as e:
            return SystemValidationResult(
                component='system',
                validation_type='disk_usage',
                status='fail',
                message=f"Error obteniendo uso de disco: {str(e)}",
                value=0,
                threshold=self.thresholds['disk_usage_percent'],
                unit='%',
                details={'error': str(e)}
            )
    
    def validate_response_time(self, endpoint: str = "http://localhost:8000/health", num_requests: int = 10) -> SystemValidationResult:
        """Valida tiempo de respuesta del sistema"""
        response_times = []
        successful_requests = 0
        
        try:
            for _ in range(num_requests):
                start_time = time.time()
                try:
                    response = requests.get(endpoint, timeout=10)
                    end_time = time.time()
                    
                    if response.status_code == 200:
                        successful_requests += 1
                    
                    response_times.append((end_time - start_time) * 1000)  # Convertir a ms
                    
                except requests.RequestException:
                    # En caso de error, agregar tiempo máximo
                    response_times.append(10000)  # 10 segundos
                
                # Pequeña pausa entre requests
                time.sleep(0.1)
            
            if not response_times:
                return SystemValidationResult(
                    component='api',
                    validation_type='response_time',
                    status='fail',
                    message="No se pudieron realizar requests",
                    value=0,
                    threshold=self.thresholds['response_time_ms'],
                    unit='ms'
                )
            
            avg_response_time = statistics.mean(response_times)
            median_response_time = statistics.median(response_times)
            p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
            success_rate = (successful_requests / num_requests) * 100
            
            # Evaluar basado en P95
            if p95_response_time > self.thresholds['response_time_ms']:
                status = 'fail'
                message = f"Tiempo de respuesta P95 crítico"
            elif p95_response_time > self.thresholds['response_time_ms'] * 0.8:
                status = 'warning'
                message = f"Tiempo de respuesta P95 alto"
            else:
                status = 'pass'
                message = f"Tiempo de respuesta aceptable"
            
            # Penalizar por baja tasa de éxito
            if success_rate < 90:
                if status == 'pass':
                    status = 'warning'
                message += f" (tasa de éxito: {success_rate:.1f}%)"
            
            return SystemValidationResult(
                component='api',
                validation_type='response_time',
                status=status,
                message=message,
                value=p95_response_time,
                threshold=self.thresholds['response_time_ms'],
                unit='ms',
                details={
                    'endpoint': endpoint,
                    'num_requests': num_requests,
                    'successful_requests': successful_requests,
                    'success_rate_percent': round(success_rate, 1),
                    'avg_ms': round(avg_response_time, 2),
                    'median_ms': round(median_response_time, 2),
                    'p95_ms': round(p95_response_time, 2),
                    'min_ms': round(min(response_times), 2),
                    'max_ms': round(max(response_times), 2)
                }
            )
            
        except Exception as e:
            return SystemValidationResult(
                component='api',
                validation_type='response_time',
                status='fail',
                message=f"Error midiendo tiempo de respuesta: {str(e)}",
                value=0,
                threshold=self.thresholds['response_time_ms'],
                unit='ms',
                details={'error': str(e)}
            )
    
    def validate_throughput(self, endpoint: str = "http://localhost:8000/health", duration_seconds: int = 30) -> SystemValidationResult:
        """Valida throughput del sistema"""
        
        def make_request():
            try:
                start_time = time.time()
                response = requests.get(endpoint, timeout=5)
                end_time = time.time()
                return {
                    'success': response.status_code == 200,
                    'response_time': end_time - start_time,
                    'timestamp': start_time
                }
            except:
                return {
                    'success': False,
                    'response_time': 5.0,
                    'timestamp': time.time()
                }
        
        try:
            results = []
            start_time = time.time()
            
            # Realizar requests concurrentes durante el período especificado
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                
                while time.time() - start_time < duration_seconds:
                    future = executor.submit(make_request)
                    futures.append(future)
                    time.sleep(0.1)  # Controlar rate de requests
                
                # Recopilar resultados
                for future in as_completed(futures, timeout=duration_seconds + 10):
                    try:
                        result = future.result(timeout=1)
                        results.append(result)
                    except:
                        continue
            
            if not results:
                return SystemValidationResult(
                    component='api',
                    validation_type='throughput',
                    status='fail',
                    message="No se pudieron completar requests para medir throughput",
                    value=0,
                    threshold=self.thresholds['throughput_qps'],
                    unit='qps'
                )
            
            # Calcular métricas
            total_duration = time.time() - start_time
            successful_requests = sum(1 for r in results if r['success'])
            total_requests = len(results)
            
            qps = total_requests / total_duration
            success_rate = (successful_requests / total_requests) * 100
            avg_response_time = statistics.mean([r['response_time'] for r in results])
            
            # Evaluar throughput
            if qps < self.thresholds['throughput_qps']:
                status = 'fail'
                message = f"Throughput muy bajo"
            elif qps < self.thresholds['throughput_qps'] * 2:
                status = 'warning'
                message = f"Throughput bajo"
            else:
                status = 'pass'
                message = f"Throughput aceptable"
            
            # Ajustar por tasa de éxito
            if success_rate < 95:
                if status == 'pass':
                    status = 'warning'
                elif status == 'warning':
                    status = 'fail'
                message += f" (éxito: {success_rate:.1f}%)"
            
            return SystemValidationResult(
                component='api',
                validation_type='throughput',
                status=status,
                message=message,
                value=qps,
                threshold=self.thresholds['throughput_qps'],
                unit='qps',
                details={
                    'endpoint': endpoint,
                    'duration_seconds': round(total_duration, 1),
                    'total_requests': total_requests,
                    'successful_requests': successful_requests,
                    'success_rate_percent': round(success_rate, 1),
                    'qps': round(qps, 2),
                    'avg_response_time_ms': round(avg_response_time * 1000, 2)
                }
            )
            
        except Exception as e:
            return SystemValidationResult(
                component='api',
                validation_type='throughput',
                status='fail',
                message=f"Error midiendo throughput: {str(e)}",
                value=0,
                threshold=self.thresholds['throughput_qps'],
                unit='qps',
                details={'error': str(e)}
            )
    
    def validate_service_availability(self) -> List[SystemValidationResult]:
        """Valida disponibilidad de servicios externos"""
        results = []
        
        services = {
            'qdrant': {
                'url': f"http://{os.getenv('QDRANT_HOST', 'ia_qdrant')}:{os.getenv('QDRANT_PORT', '6333')}/readyz",
                'timeout': 5
            },
            'ollama': {
                'url': f"http://{os.getenv('OLLAMA_HOST', 'ia_ollama_1')}:{os.getenv('OLLAMA_PORT', '11434')}/api/tags",
                'timeout': 10
            }
        }
        
        for service_name, config in services.items():
            try:
                start_time = time.time()
                response = requests.get(config['url'], timeout=config['timeout'])
                response_time = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    status = 'pass'
                    message = f"Servicio {service_name} disponible"
                    value = 1.0
                else:
                    status = 'fail'
                    message = f"Servicio {service_name} respondió con código {response.status_code}"
                    value = 0.0
                
                results.append(SystemValidationResult(
                    component=f'service_{service_name}',
                    validation_type='availability',
                    status=status,
                    message=message,
                    value=value,
                    threshold=1.0,
                    unit='available',
                    details={
                        'url': config['url'],
                        'response_time_ms': round(response_time, 2),
                        'status_code': response.status_code
                    }
                ))
                
            except requests.RequestException as e:
                results.append(SystemValidationResult(
                    component=f'service_{service_name}',
                    validation_type='availability',
                    status='fail',
                    message=f"Servicio {service_name} no disponible: {str(e)}",
                    value=0.0,
                    threshold=1.0,
                    unit='available',
                    details={
                        'url': config['url'],
                        'error': str(e)
                    }
                ))
        
        return results
    
    def validate_log_health(self, log_path: str = '/app/output/logs/app.log') -> SystemValidationResult:
        """Valida salud de logs del sistema"""
        try:
            if not os.path.exists(log_path):
                return SystemValidationResult(
                    component='logs',
                    validation_type='health_check',
                    status='warning',
                    message="Archivo de log no existe",
                    value=0,
                    threshold=1,
                    unit='exists',
                    details={'log_path': log_path}
                )
            
            # Obtener información del archivo
            stat = os.stat(log_path)
            file_size_mb = stat.st_size / (1024 * 1024)
            last_modified = time.time() - stat.st_mtime
            
            # Verificar actividad reciente (logs escritos en las últimas 24 horas)
            if last_modified > 86400:  # 24 horas
                status = 'warning'
                message = f"Log no ha sido actualizado en {last_modified/3600:.1f} horas"
                value = 0.5
            else:
                status = 'pass'
                message = f"Log activo (última modificación: {last_modified/60:.1f} min ago)"
                value = 1.0
            
            # Verificar tamaño del archivo (muy grande puede indicar problemas)
            if file_size_mb > 100:  # 100MB
                if status == 'pass':
                    status = 'warning'
                message += f" - Archivo de log muy grande ({file_size_mb:.1f}MB)"
                value *= 0.8
            
            # Intentar leer las últimas líneas para verificar errores recientes
            error_count = 0
            warning_count = 0
            
            try:
                with open(log_path, 'r') as f:
                    # Leer las últimas 100 líneas
                    lines = f.readlines()[-100:]
                    
                    for line in lines:
                        line_lower = line.lower()
                        if 'error' in line_lower or 'exception' in line_lower:
                            error_count += 1
                        elif 'warning' in line_lower or 'warn' in line_lower:
                            warning_count += 1
                
                # Evaluar cantidad de errores
                if error_count > 10:
                    status = 'fail'
                    message += f" - Muchos errores recientes ({error_count})"
                    value *= 0.3
                elif error_count > 5:
                    if status == 'pass':
                        status = 'warning'
                    message += f" - Algunos errores recientes ({error_count})"
                    value *= 0.7
                    
            except Exception:
                # No se pudo leer el archivo, pero existe
                message += " - No se pudo analizar contenido del log"
                value *= 0.8
            
            return SystemValidationResult(
                component='logs',
                validation_type='health_check',
                status=status,
                message=message,
                value=value,
                threshold=1,
                unit='health_score',
                details={
                    'log_path': log_path,
                    'file_size_mb': round(file_size_mb, 2),
                    'last_modified_hours': round(last_modified / 3600, 2),
                    'recent_errors': error_count,
                    'recent_warnings': warning_count
                }
            )
            
        except Exception as e:
            return SystemValidationResult(
                component='logs',
                validation_type='health_check',
                status='fail',
                message=f"Error validando logs: {str(e)}",
                value=0,
                threshold=1,
                unit='health_score',
                details={'error': str(e)}
            )
    
    def run_all_validations(self) -> List[SystemValidationResult]:
        """Ejecuta todas las validaciones de sistema"""
        results = []
        
        # Validaciones de recursos del sistema
        results.append(self.validate_memory_usage())
        results.append(self.validate_cpu_usage())
        results.append(self.validate_disk_usage())
        
        # Validaciones de servicios
        results.extend(self.validate_service_availability())
        
        # Validaciones de performance (solo si hay servicios disponibles)
        qdrant_available = any(r.status == 'pass' and 'qdrant' in r.component for r in results)
        if qdrant_available:
            results.append(self.validate_response_time())
            results.append(self.validate_throughput())
        
        # Validación de logs
        results.append(self.validate_log_health())
        
        return results
    
    def get_overall_score(self, results: List[SystemValidationResult]) -> float:
        """Calcula score general de validación de sistema"""
        if not results:
            return 0.0
        
        # Normalizar valores al rango 0-1
        normalized_scores = []
        
        for result in results:
            if result.validation_type == 'availability':
                score = result.value  # Ya está en 0-1
            elif result.validation_type in ['memory_usage', 'cpu_usage', 'disk_usage']:
                # Para uso de recursos, score = 1 - (valor/umbral) clamped to [0,1]
                score = max(0, 1 - (result.value / result.threshold))
            elif result.validation_type == 'response_time':
                # Para tiempo de respuesta, score = 1 - (valor/umbral) clamped to [0,1]
                score = max(0, 1 - (result.value / result.threshold))
            elif result.validation_type == 'throughput':
                # Para throughput, score = min(1, valor/umbral)
                score = min(1, result.value / result.threshold)
            else:
                score = result.value
            
            normalized_scores.append(score)
        
        return statistics.mean(normalized_scores) if normalized_scores else 0.0
    
    def print_results(self, results: List[SystemValidationResult], verbose: bool = False):
        """Imprime resultados de validación de sistema"""
        if not results:
            print("❌ No hay resultados de validación de sistema")
            return
        
        overall_score = self.get_overall_score(results)
        
        print(f"\n🖥️  Validación de Sistema - Score General: {overall_score:.2f}")
        print(f"   {'🟢 Excelente' if overall_score >= 0.8 else '🟡 Bueno' if overall_score >= 0.6 else '🔴 Necesita Mejora'}")
        print()
        
        # Agrupar por componente
        from collections import defaultdict
        components = defaultdict(list)
        for result in results:
            components[result.component].append(result)
        
        for component, component_results in components.items():
            print(f"🔧 {component.upper().replace('_', ' ')}:")
            
            for result in component_results:
                status_emoji = {'pass': '✅', 'warning': '⚠️', 'fail': '❌'}[result.status]
                
                if result.unit in ['%', 'ms', 'qps']:
                    value_str = f"{result.value:.1f}{result.unit}"
                    threshold_str = f"(límite: {result.threshold}{result.unit})"
                else:
                    value_str = f"{result.value}"
                    threshold_str = ""
                
                print(f"   {status_emoji} {result.validation_type.replace('_', ' ').title()}: {value_str} {threshold_str}")
                print(f"      {result.message}")
                
                if verbose and result.details:
                    print(f"      Detalles: {result.details}")
            print()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validador de sistema RAG Jurídico")
    parser.add_argument('--verbose', '-v', action='store_true', help='Mostrar detalles adicionales')
    parser.add_argument('--endpoint', '-e', default='http://localhost:8000/health', help='Endpoint para tests de performance')
    
    args = parser.parse_args()
    
    validator = SystemValidator()
    results = validator.run_all_validations()
    validator.print_results(results, verbose=args.verbose)
    
    # Exit con código de error si el score general es muy bajo
    overall_score = validator.get_overall_score(results)
    if overall_score < 0.5:
        exit(1)