#!/usr/bin/env python3
"""
Tests para el Sistema de Validación Avanzado RAG Jurídico

Tests unitarios básicos para validar el funcionamiento
de los módulos de validación.
"""

import unittest
import os
import sys
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock

# Agregar paths para importar módulos
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/scripts')

class TestConfigValidator(unittest.TestCase):
    """Tests para ConfigValidator"""
    
    def setUp(self):
        from scripts.validation.config_validator import ConfigValidator
        self.validator = ConfigValidator()
    
    def test_validate_environment_variables(self):
        """Test validación de variables de entorno"""
        results = self.validator.validate_environment_variables()
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)
        
        # Verificar que se validan las variables críticas
        var_names = [r.component for r in results]
        self.assertIn('env_var_QDRANT_HOST', var_names)
        self.assertIn('env_var_OLLAMA_HOST', var_names)
    
    @patch('requests.get')
    def test_validate_qdrant_connection_success(self, mock_get):
        """Test conexión exitosa con Qdrant"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = self.validator.validate_qdrant_connection()
        
        self.assertEqual(result.status, 'ok')
        self.assertEqual(result.component, 'qdrant_connection')
    
    @patch('requests.get')
    def test_validate_qdrant_connection_failure(self, mock_get):
        """Test fallo de conexión con Qdrant"""
        mock_get.side_effect = Exception("Connection failed")
        
        result = self.validator.validate_qdrant_connection()
        
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.component, 'qdrant_connection')
    
    def test_run_all_validations(self):
        """Test ejecución de todas las validaciones"""
        results = self.validator.run_all_validations()
        
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)
        
        # Verificar que hay diferentes tipos de validaciones
        validation_types = {r.component for r in results}
        self.assertTrue(len(validation_types) > 1)


class TestLegalValidator(unittest.TestCase):
    """Tests para LegalValidator"""
    
    def setUp(self):
        from scripts.validation.legal_validator import LegalValidator
        self.validator = LegalValidator()
    
    def test_validate_legal_references(self):
        """Test validación de referencias legales"""
        text_with_refs = "Según el artículo 123 de la Constitución y la fracción IV del Código Civil..."
        text_without_refs = "Esta es una respuesta genérica sin referencias específicas."
        
        result_with = self.validator.validate_legal_references(text_with_refs, "test1")
        result_without = self.validator.validate_legal_references(text_without_refs, "test2")
        
        self.assertGreater(result_with.score, result_without.score)
        self.assertEqual(result_with.validation_type, 'legal_references')
    
    def test_validate_legal_terminology(self):
        """Test validación de terminología jurídica"""
        legal_text = "La responsabilidad civil por daños y perjuicios requiere el debido proceso legal."
        non_legal_text = "El clima está muy bonito hoy en la ciudad."
        
        result_legal = self.validator.validate_legal_terminology(legal_text, "test1")
        result_non_legal = self.validator.validate_legal_terminology(non_legal_text, "test2")
        
        self.assertGreater(result_legal.score, result_non_legal.score)
        self.assertEqual(result_legal.validation_type, 'legal_terminology')
    
    def test_validate_response_structure(self):
        """Test validación de estructura de respuesta"""
        structured_text = "En virtud de lo anterior, se concluye que conforme a la ley..."
        unstructured_text = "Si. No. Tal vez."
        
        result_structured = self.validator.validate_response_structure(structured_text, "test1")
        result_unstructured = self.validator.validate_response_structure(unstructured_text, "test2")
        
        self.assertGreater(result_structured.score, result_unstructured.score)
    
    def test_validate_response_complete(self):
        """Test validación completa de respuesta"""
        question = "¿Cuáles son los derechos fundamentales en la Constitución?"
        answer = """Los derechos fundamentales establecidos en la Constitución Política incluyen 
        las garantías individuales del artículo 1° al 29°. Conforme a la jurisprudencia, 
        estos derechos son inalienables y constituyen la base del debido proceso legal."""
        
        results = self.validator.validate_response(question, answer, "test")
        
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)
        
        # Verificar que se ejecutan todas las validaciones
        validation_types = {r.validation_type for r in results}
        expected_types = {
            'legal_references', 'legal_terminology', 
            'response_structure', 'citation_format', 'legal_coherence'
        }
        self.assertEqual(validation_types, expected_types)
    
    def test_get_overall_score(self):
        """Test cálculo de score general"""
        # Crear resultados mock
        from scripts.validation.legal_validator import LegalValidationResult
        
        results = [
            LegalValidationResult("test", "legal_references", "pass", "Good", 0.8),
            LegalValidationResult("test", "legal_terminology", "pass", "Good", 0.7),
            LegalValidationResult("test", "response_structure", "warning", "Ok", 0.6),
            LegalValidationResult("test", "citation_format", "pass", "Good", 0.9),
            LegalValidationResult("test", "legal_coherence", "pass", "Good", 0.8)
        ]
        
        score = self.validator.get_overall_score(results)
        
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestSystemValidator(unittest.TestCase):
    """Tests para SystemValidator"""
    
    def setUp(self):
        from scripts.validation.system_validator import SystemValidator
        self.validator = SystemValidator()
    
    @patch('psutil.virtual_memory')
    def test_validate_memory_usage(self, mock_memory):
        """Test validación de uso de memoria"""
        # Mock memoria normal
        mock_memory.return_value = Mock(
            percent=50.0,
            total=8*1024**3,  # 8GB
            available=4*1024**3,  # 4GB
            used=4*1024**3  # 4GB
        )
        
        result = self.validator.validate_memory_usage()
        
        self.assertEqual(result.validation_type, 'memory_usage')
        self.assertIn(result.status, ['pass', 'warning', 'fail'])
        self.assertEqual(result.value, 50.0)
    
    @patch('psutil.cpu_percent')
    def test_validate_cpu_usage(self, mock_cpu):
        """Test validación de uso de CPU"""
        mock_cpu.return_value = 30.0
        
        result = self.validator.validate_cpu_usage(interval=0.1)
        
        self.assertEqual(result.validation_type, 'cpu_usage')
        self.assertEqual(result.value, 30.0)
        self.assertEqual(result.status, 'pass')
    
    @patch('psutil.disk_usage')
    def test_validate_disk_usage(self, mock_disk):
        """Test validación de uso de disco"""
        mock_disk.return_value = Mock(
            total=100*1024**3,  # 100GB
            used=50*1024**3,    # 50GB
            free=50*1024**3     # 50GB
        )
        
        result = self.validator.validate_disk_usage()
        
        self.assertEqual(result.validation_type, 'disk_usage')
        self.assertEqual(result.value, 50.0)  # 50% usage
        self.assertEqual(result.status, 'pass')
    
    @patch('requests.get')
    def test_validate_service_availability(self, mock_get):
        """Test validación de disponibilidad de servicios"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        results = self.validator.validate_service_availability()
        
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) >= 2)  # Al menos Qdrant y Ollama
        
        for result in results:
            self.assertEqual(result.validation_type, 'availability')
            self.assertIn('service_', result.component)


class TestEmbeddingValidator(unittest.TestCase):
    """Tests para EmbeddingValidator"""
    
    def setUp(self):
        from scripts.validation.embedding_validator import EmbeddingValidator
        self.validator = EmbeddingValidator()
    
    def test_init_without_qdrant(self):
        """Test inicialización sin conexión a Qdrant"""
        # El validador debería manejar gracefully la falta de conexión
        self.assertIsNotNone(self.validator)
    
    @patch('qdrant_client.QdrantClient')
    def test_validate_collection_exists_success(self, mock_client_class):
        """Test validación exitosa de existencia de colección"""
        # Mock del cliente y respuesta
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock collections response
        mock_collection = Mock()
        mock_collection.name = 'juridico'
        mock_collections = Mock()
        mock_collections.collections = [mock_collection]
        mock_client.get_collections.return_value = mock_collections
        
        # Mock collection info
        mock_collection_info = Mock()
        mock_collection_info.vectors_count = 1000
        mock_client.get_collection.return_value = mock_collection_info
        
        # Recrear validator con mock
        self.validator.qdrant_client = mock_client
        
        result = self.validator.validate_collection_exists('juridico')
        
        self.assertEqual(result.status, 'pass')
        self.assertEqual(result.validation_type, 'collection_existence')


class TestAdvancedValidator(unittest.TestCase):
    """Tests para el sistema de validación completo"""
    
    def setUp(self):
        from scripts.validation.advanced_validator import AdvancedValidationRunner
        self.runner = AdvancedValidationRunner(verbose=False)
    
    def test_init(self):
        """Test inicialización del runner"""
        self.assertIsNotNone(self.runner.config_validator)
        self.assertIsNotNone(self.runner.legal_validator)
        self.assertIsNotNone(self.runner.embedding_validator)
        self.assertIsNotNone(self.runner.system_validator)
    
    def test_generate_comprehensive_report(self):
        """Test generación de reporte completo"""
        # Mock results
        self.runner.all_results = {
            'config': {'overall_status': 'pass'},
            'system': {'overall_status': 'warning', 'overall_score': 0.7},
            'embeddings': {'overall_status': 'pass', 'overall_score': 0.8},
            'legal': {'overall_status': 'pass', 'overall_score': 0.9}
        }
        
        report = self.runner.generate_comprehensive_report()
        
        self.assertIn('timestamp', report)
        self.assertIn('overall_status', report)
        self.assertIn('validation_results', report)
        self.assertIn('summary', report)
        
        # Verificar estructura del summary
        summary = report['summary']
        self.assertIn('total_validations', summary)
        self.assertIn('passed', summary)
        self.assertIn('warnings', summary)
        self.assertIn('failures', summary)
    
    def test_save_report(self):
        """Test guardado de reporte"""
        report = {
            'timestamp': '2024-01-01 12:00:00',
            'overall_status': 'pass',
            'validation_results': {}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = f.name
        
        try:
            saved_file = self.runner.save_report(report, output_file)
            
            self.assertEqual(saved_file, output_file)
            self.assertTrue(os.path.exists(output_file))
            
            # Verificar contenido
            with open(output_file, 'r') as f:
                loaded_report = json.load(f)
            
            self.assertEqual(loaded_report['overall_status'], 'pass')
            
        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)


def run_tests():
    """Ejecuta todos los tests"""
    # Configurar suite de tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Agregar test classes
    test_classes = [
        TestConfigValidator,
        TestLegalValidator,
        TestSystemValidator,
        TestEmbeddingValidator,
        TestAdvancedValidator
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Ejecutar tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Tests para Sistema de Validación")
    parser.add_argument('--test-class', help='Ejecutar solo una clase de test específica')
    
    args = parser.parse_args()
    
    if args.test_class:
        # Ejecutar solo una clase específica
        if args.test_class in globals():
            suite = unittest.TestLoader().loadTestsFromTestCase(globals()[args.test_class])
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)
            exit(0 if result.wasSuccessful() else 1)
        else:
            print(f"Test class '{args.test_class}' not found")
            exit(1)
    else:
        # Ejecutar todos los tests
        success = run_tests()
        exit(0 if success else 1)