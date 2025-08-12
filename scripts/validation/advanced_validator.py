#!/usr/bin/env python3
"""
Sistema de Validación Avanzado para RAG Jurídico

Script principal que ejecuta todas las validaciones del sistema
y proporciona un reporte completo de estado.
"""

import os
import sys
import argparse
import json
import time
from typing import Dict, List, Any
import logging
from dataclasses import asdict

# Agregar el directorio del proyecto al path para imports
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/scripts')

try:
    from scripts.validation.config_validator import ConfigValidator
    from scripts.validation.legal_validator import LegalValidator
    from scripts.validation.embedding_validator import EmbeddingValidator
    from scripts.validation.system_validator import SystemValidator
except ImportError as e:
    print(f"Error importando validadores: {e}")
    print("Asegúrate de que el script se ejecute desde el contenedor de la aplicación")
    sys.exit(1)

class AdvancedValidationRunner:
    """Runner principal para el sistema de validación avanzado"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = self._setup_logging()
        
        # Inicializar validadores
        self.config_validator = ConfigValidator()
        self.legal_validator = LegalValidator()
        self.embedding_validator = EmbeddingValidator()
        self.system_validator = SystemValidator()
        
        self.all_results = {}
    
    def _setup_logging(self) -> logging.Logger:
        """Configura logging para el validador"""
        logging.basicConfig(
            level=logging.INFO if self.verbose else logging.WARNING,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    def run_config_validation(self) -> Dict[str, Any]:
        """Ejecuta validación de configuración"""
        print("🔧 Ejecutando validación de configuración...")
        
        results = self.config_validator.run_all_validations()
        self.config_validator.print_results(verbose=self.verbose)
        
        summary = self.config_validator.get_summary()
        
        return {
            'results': [asdict(r) for r in results],
            'summary': summary,
            'overall_status': 'pass' if summary['error'] == 0 else 'fail' if summary['error'] > summary['warning'] else 'warning'
        }
    
    def run_system_validation(self) -> Dict[str, Any]:
        """Ejecuta validación de sistema"""
        print("🖥️  Ejecutando validación de sistema...")
        
        results = self.system_validator.run_all_validations()
        self.system_validator.print_results(results, verbose=self.verbose)
        
        overall_score = self.system_validator.get_overall_score(results)
        
        return {
            'results': [asdict(r) for r in results],
            'overall_score': overall_score,
            'overall_status': 'pass' if overall_score >= 0.7 else 'warning' if overall_score >= 0.5 else 'fail'
        }
    
    def run_embedding_validation(self, collection_name: str = "juridico") -> Dict[str, Any]:
        """Ejecuta validación de embeddings"""
        print("🔍 Ejecutando validación de embeddings...")
        
        results = self.embedding_validator.run_all_validations(collection_name)
        self.embedding_validator.print_results(results, verbose=self.verbose)
        
        overall_score = self.embedding_validator.get_overall_score(results)
        
        return {
            'results': [asdict(r) for r in results],
            'overall_score': overall_score,
            'overall_status': 'pass' if overall_score >= 0.7 else 'warning' if overall_score >= 0.5 else 'fail',
            'collection_name': collection_name
        }
    
    def run_legal_validation_sample(self, sample_file: str = None) -> Dict[str, Any]:
        """Ejecuta validación legal con una muestra"""
        print("⚖️  Ejecutando validación legal (muestra)...")
        
        # Muestra de preguntas y respuestas para validación
        if sample_file and os.path.exists(sample_file):
            try:
                with open(sample_file, 'r', encoding='utf-8') as f:
                    sample_data = json.load(f)
                
                if isinstance(sample_data, list) and len(sample_data) > 0:
                    sample_qa = sample_data[0]
                    question = sample_qa.get('question', '')
                    answer = sample_qa.get('answer', '')
                    question_id = sample_qa.get('id', 'sample')
                else:
                    raise ValueError("Formato de archivo de muestra no válido")
                    
            except Exception as e:
                print(f"⚠️  Error leyendo archivo de muestra: {e}")
                # Usar muestra por defecto
                question = "¿Cuáles son los derechos fundamentales establecidos en la Constitución Política?"
                answer = "Los derechos fundamentales establecidos en la Constitución Política incluyen..."
                question_id = "default_sample"
        else:
            # Muestra por defecto
            question = "¿Cuáles son los derechos fundamentales establecidos en la Constitución Política?"
            answer = "Los derechos fundamentales establecidos en la Constitución Política de los Estados Unidos Mexicanos incluyen las garantías individuales consagradas en el Título Primero, Capítulo I, artículos 1 al 29. Entre estos se encuentran: el derecho a la vida, libertad, igualdad ante la ley, libertad de expresión, derecho a la educación, derecho al trabajo, y protección contra la discriminación. El artículo 1° establece que todas las personas gozarán de los derechos humanos reconocidos en la Constitución y en los tratados internacionales. Asimismo, el artículo 14 garantiza el debido proceso legal y el derecho de audiencia."
            question_id = "default_sample"
        
        results = self.legal_validator.validate_response(question, answer, question_id)
        self.legal_validator.print_results(results, verbose=self.verbose)
        
        overall_score = self.legal_validator.get_overall_score(results)
        
        return {
            'results': [asdict(r) for r in results],
            'overall_score': overall_score,
            'overall_status': 'pass' if overall_score >= 0.7 else 'warning' if overall_score >= 0.5 else 'fail',
            'sample_question': question,
            'sample_answer': answer[:200] + "..." if len(answer) > 200 else answer
        }
    
    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Genera reporte completo de todas las validaciones"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Calcular estado general
        statuses = [self.all_results[key]['overall_status'] for key in self.all_results]
        
        if all(status == 'pass' for status in statuses):
            overall_status = 'pass'
            overall_message = "✅ Todas las validaciones pasaron exitosamente"
        elif any(status == 'fail' for status in statuses):
            overall_status = 'fail'
            overall_message = "❌ Se detectaron fallos críticos en el sistema"
        else:
            overall_status = 'warning'
            overall_message = "⚠️  Se detectaron advertencias que requieren atención"
        
        # Calcular scores promedio donde aplique
        scores = []
        for key in ['system', 'embeddings', 'legal']:
            if key in self.all_results and 'overall_score' in self.all_results[key]:
                scores.append(self.all_results[key]['overall_score'])
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        report = {
            'timestamp': timestamp,
            'overall_status': overall_status,
            'overall_message': overall_message,
            'average_score': round(avg_score, 3),
            'validation_results': self.all_results,
            'summary': {
                'total_validations': len(self.all_results),
                'passed': sum(1 for r in self.all_results.values() if r['overall_status'] == 'pass'),
                'warnings': sum(1 for r in self.all_results.values() if r['overall_status'] == 'warning'),
                'failures': sum(1 for r in self.all_results.values() if r['overall_status'] == 'fail')
            }
        }
        
        return report
    
    def save_report(self, report: Dict[str, Any], output_file: str = None) -> str:
        """Guarda el reporte en archivo JSON"""
        if not output_file:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"/app/output/validation_report_{timestamp}.json"
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return output_file
    
    def print_summary_report(self, report: Dict[str, Any]):
        """Imprime resumen del reporte"""
        print("\n" + "="*80)
        print("📊 REPORTE COMPLETO DE VALIDACIÓN RAG JURÍDICO")
        print("="*80)
        print(f"Timestamp: {report['timestamp']}")
        print(f"Estado General: {report['overall_message']}")
        print(f"Score Promedio: {report['average_score']:.2f}/1.00")
        print()
        
        summary = report['summary']
        print(f"📈 Resumen de Validaciones:")
        print(f"   Total: {summary['total_validations']}")
        print(f"   ✅ Exitosas: {summary['passed']}")
        print(f"   ⚠️  Advertencias: {summary['warnings']}")
        print(f"   ❌ Fallos: {summary['failures']}")
        print()
        
        # Detalles por tipo de validación
        for validation_type, results in report['validation_results'].items():
            status_emoji = {'pass': '✅', 'warning': '⚠️', 'fail': '❌'}[results['overall_status']]
            print(f"{status_emoji} {validation_type.upper()}: {results['overall_status']}")
            
            if 'overall_score' in results:
                print(f"   Score: {results['overall_score']:.2f}")
            
            if validation_type == 'config' and 'summary' in results:
                config_summary = results['summary']
                print(f"   OK: {config_summary['ok']}, Advertencias: {config_summary['warning']}, Errores: {config_summary['error']}")
        
        print()
        print("="*80)
    
    def run_all_validations(self, collection_name: str = "juridico", sample_file: str = None) -> Dict[str, Any]:
        """Ejecuta todas las validaciones del sistema"""
        print("🚀 Iniciando Sistema de Validación Avanzado RAG Jurídico")
        print("="*60)
        
        # 1. Validación de configuración (siempre primero)
        self.all_results['config'] = self.run_config_validation()
        
        # 2. Validación de sistema
        self.all_results['system'] = self.run_system_validation()
        
        # 3. Validación de embeddings (solo si la configuración básica está OK)
        if self.all_results['config']['overall_status'] != 'fail':
            self.all_results['embeddings'] = self.run_embedding_validation(collection_name)
        else:
            print("⚠️  Saltando validación de embeddings debido a fallos de configuración")
            self.all_results['embeddings'] = {
                'overall_status': 'fail',
                'overall_score': 0.0,
                'results': [],
                'message': 'Saltado debido a fallos de configuración'
            }
        
        # 4. Validación legal (muestra)
        self.all_results['legal'] = self.run_legal_validation_sample(sample_file)
        
        # Generar reporte completo
        report = self.generate_comprehensive_report()
        
        return report

def main():
    parser = argparse.ArgumentParser(
        description="Sistema de Validación Avanzado RAG Jurídico",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python advanced_validator.py                     # Validación completa
  python advanced_validator.py --verbose           # Con detalles adicionales
  python advanced_validator.py --config-only       # Solo validación de configuración
  python advanced_validator.py --output /tmp/report.json  # Guardar reporte
        """
    )
    
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Mostrar información detallada')
    parser.add_argument('--config-only', action='store_true',
                        help='Ejecutar solo validación de configuración')
    parser.add_argument('--system-only', action='store_true',
                        help='Ejecutar solo validación de sistema')
    parser.add_argument('--embeddings-only', action='store_true',
                        help='Ejecutar solo validación de embeddings')
    parser.add_argument('--legal-only', action='store_true',
                        help='Ejecutar solo validación legal')
    parser.add_argument('--collection', '-c', default='juridico',
                        help='Nombre de la colección de Qdrant (default: juridico)')
    parser.add_argument('--sample-file', '-s',
                        help='Archivo JSON con muestra para validación legal')
    parser.add_argument('--output', '-o',
                        help='Archivo de salida para el reporte JSON')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suprimir output excepto errores críticos')
    
    args = parser.parse_args()
    
    # Configurar nivel de output
    if args.quiet:
        verbose = False
        print_output = False
    else:
        verbose = args.verbose
        print_output = True
    
    # Crear runner
    runner = AdvancedValidationRunner(verbose=verbose)
    
    try:
        # Ejecutar validaciones según argumentos
        if args.config_only:
            if print_output:
                print("Ejecutando solo validación de configuración...")
            results = runner.run_config_validation()
            report = {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'validation_results': {'config': results},
                'overall_status': results['overall_status']
            }
        elif args.system_only:
            if print_output:
                print("Ejecutando solo validación de sistema...")
            results = runner.run_system_validation()
            report = {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'validation_results': {'system': results},
                'overall_status': results['overall_status']
            }
        elif args.embeddings_only:
            if print_output:
                print("Ejecutando solo validación de embeddings...")
            results = runner.run_embedding_validation(args.collection)
            report = {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'validation_results': {'embeddings': results},
                'overall_status': results['overall_status']
            }
        elif args.legal_only:
            if print_output:
                print("Ejecutando solo validación legal...")
            results = runner.run_legal_validation_sample(args.sample_file)
            report = {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'validation_results': {'legal': results},
                'overall_status': results['overall_status']
            }
        else:
            # Validación completa
            report = runner.run_all_validations(args.collection, args.sample_file)
        
        # Mostrar resumen si no está en modo quiet
        if print_output:
            runner.print_summary_report(report)
        
        # Guardar reporte si se especifica archivo de salida
        if args.output:
            output_file = runner.save_report(report, args.output)
            if print_output:
                print(f"\n📄 Reporte guardado en: {output_file}")
        
        # Determinar código de salida
        overall_status = report.get('overall_status', 'fail')
        if overall_status == 'fail':
            if print_output:
                print("\n❌ Validación falló - revisar errores críticos")
            exit(1)
        elif overall_status == 'warning':
            if print_output:
                print("\n⚠️  Validación completada con advertencias")
            exit(0)
        else:
            if print_output:
                print("\n✅ Validación completada exitosamente")
            exit(0)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Validación interrumpida por el usuario")
        exit(130)
    except Exception as e:
        print(f"\n❌ Error ejecutando validación: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()