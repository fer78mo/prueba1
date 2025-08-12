#!/usr/bin/env python3
"""
Validador de Calidad de Embeddings para RAG Jurídico

Valida la calidad de los embeddings generados, su consistencia
y la efectividad del proceso de retrieval.
"""

import os
import json
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import logging
from collections import defaultdict
import time

@dataclass
class EmbeddingValidationResult:
    """Resultado de validación de embeddings"""
    component: str
    validation_type: str
    status: str  # 'pass', 'warning', 'fail'
    message: str
    score: float  # 0.0 - 1.0
    details: Optional[Dict] = None

class EmbeddingValidator:
    """Validador de calidad de embeddings"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.qdrant_client = None
        self._init_qdrant_client()
    
    def _init_qdrant_client(self):
        """Inicializa cliente de Qdrant"""
        try:
            from qdrant_client import QdrantClient
            qdrant_host = os.getenv('QDRANT_HOST', 'ia_qdrant')
            qdrant_port = int(os.getenv('QDRANT_PORT', '6333'))
            
            self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
            
        except Exception as e:
            self.logger.error(f"Error inicializando cliente Qdrant: {e}")
    
    def validate_collection_exists(self, collection_name: str = "juridico") -> EmbeddingValidationResult:
        """Valida que la colección existe en Qdrant"""
        try:
            if not self.qdrant_client:
                return EmbeddingValidationResult(
                    component="qdrant_client",
                    validation_type="collection_existence",
                    status="fail",
                    message="Cliente Qdrant no disponible",
                    score=0.0
                )
            
            collections = self.qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if collection_name in collection_names:
                # Obtener información de la colección
                collection_info = self.qdrant_client.get_collection(collection_name)
                vectors_count = collection_info.vectors_count
                
                return EmbeddingValidationResult(
                    component="collection",
                    validation_type="collection_existence",
                    status="pass",
                    message=f"Colección '{collection_name}' existe con {vectors_count} vectores",
                    score=1.0,
                    details={
                        "collection_name": collection_name,
                        "vectors_count": vectors_count,
                        "config": collection_info.config.dict() if hasattr(collection_info, 'config') else None
                    }
                )
            else:
                return EmbeddingValidationResult(
                    component="collection",
                    validation_type="collection_existence",
                    status="fail",
                    message=f"Colección '{collection_name}' no existe. Disponibles: {collection_names}",
                    score=0.0,
                    details={"available_collections": collection_names}
                )
                
        except Exception as e:
            return EmbeddingValidationResult(
                component="collection",
                validation_type="collection_existence",
                status="fail",
                message=f"Error verificando colección: {str(e)}",
                score=0.0,
                details={"error": str(e)}
            )
    
    def validate_embedding_dimension(self, collection_name: str = "juridico") -> EmbeddingValidationResult:
        """Valida que las dimensiones de embeddings sean consistentes"""
        try:
            if not self.qdrant_client:
                return EmbeddingValidationResult(
                    component="embeddings",
                    validation_type="dimension_consistency",
                    status="fail",
                    message="Cliente Qdrant no disponible",
                    score=0.0
                )
            
            # Obtener información de la colección
            collection_info = self.qdrant_client.get_collection(collection_name)
            
            if hasattr(collection_info, 'config') and hasattr(collection_info.config, 'params'):
                vector_size = collection_info.config.params.vectors.size
                distance = collection_info.config.params.vectors.distance
                
                # Validar dimensión esperada (común para modelos de embeddings)
                expected_sizes = [384, 512, 768, 1024, 1536]  # Dimensiones comunes
                
                if vector_size in expected_sizes:
                    status = "pass"
                    message = f"Dimensión de embeddings válida: {vector_size}"
                    score = 1.0
                else:
                    status = "warning"
                    message = f"Dimensión no estándar: {vector_size}. Esperadas: {expected_sizes}"
                    score = 0.7
                
                return EmbeddingValidationResult(
                    component="embeddings",
                    validation_type="dimension_consistency",
                    status=status,
                    message=message,
                    score=score,
                    details={
                        "vector_size": vector_size,
                        "distance_metric": distance,
                        "expected_sizes": expected_sizes
                    }
                )
            else:
                return EmbeddingValidationResult(
                    component="embeddings",
                    validation_type="dimension_consistency",
                    status="warning",
                    message="No se pudo obtener información de configuración de vectores",
                    score=0.5
                )
                
        except Exception as e:
            return EmbeddingValidationResult(
                component="embeddings",
                validation_type="dimension_consistency",
                status="fail",
                message=f"Error validando dimensiones: {str(e)}",
                score=0.0,
                details={"error": str(e)}
            )
    
    def validate_embedding_quality(self, collection_name: str = "juridico", sample_size: int = 100) -> EmbeddingValidationResult:
        """Valida calidad de embeddings mediante muestreo"""
        try:
            if not self.qdrant_client:
                return EmbeddingValidationResult(
                    component="embeddings",
                    validation_type="quality_check",
                    status="fail",
                    message="Cliente Qdrant no disponible",
                    score=0.0
                )
            
            # Scroll para obtener una muestra de vectores
            scroll_result = self.qdrant_client.scroll(
                collection_name=collection_name,
                limit=sample_size,
                with_vectors=True
            )
            
            if not scroll_result[0]:
                return EmbeddingValidationResult(
                    component="embeddings",
                    validation_type="quality_check",
                    status="fail",
                    message="No se encontraron vectores en la colección",
                    score=0.0
                )
            
            vectors = []
            valid_vectors = 0
            zero_vectors = 0
            
            for point in scroll_result[0]:
                if hasattr(point, 'vector') and point.vector:
                    vector = np.array(point.vector)
                    vectors.append(vector)
                    
                    # Verificar que no sea vector cero
                    if np.allclose(vector, 0):
                        zero_vectors += 1
                    else:
                        valid_vectors += 1
            
            if not vectors:
                return EmbeddingValidationResult(
                    component="embeddings",
                    validation_type="quality_check",
                    status="fail",
                    message="No se pudieron extraer vectores válidos",
                    score=0.0
                )
            
            # Calcular estadísticas de calidad
            vectors_array = np.array(vectors)
            
            # Verificar varianza (embeddings muy similares indican problemas)
            variance = np.var(vectors_array, axis=0).mean()
            
            # Verificar norma de vectores
            norms = np.linalg.norm(vectors_array, axis=1)
            avg_norm = np.mean(norms)
            norm_std = np.std(norms)
            
            # Calcular diversidad (distancia promedio entre vectores)
            if len(vectors) > 1:
                distances = []
                for i in range(min(50, len(vectors))):  # Limitar cálculo
                    for j in range(i+1, min(50, len(vectors))):
                        dist = np.linalg.norm(vectors[i] - vectors[j])
                        distances.append(dist)
                avg_distance = np.mean(distances) if distances else 0
            else:
                avg_distance = 0
            
            # Evaluar calidad
            quality_issues = []
            score = 1.0
            
            # Verificar vectores cero
            zero_ratio = zero_vectors / len(vectors)
            if zero_ratio > 0.1:
                quality_issues.append(f"Demasiados vectores cero ({zero_ratio:.1%})")
                score *= 0.5
            
            # Verificar varianza muy baja (indica embeddings muy similares)
            if variance < 0.01:
                quality_issues.append(f"Varianza muy baja ({variance:.4f})")
                score *= 0.7
            
            # Verificar normas anómalas
            if avg_norm < 0.1 or avg_norm > 10:
                quality_issues.append(f"Norma promedio anómala ({avg_norm:.3f})")
                score *= 0.8
            
            # Verificar diversidad
            if avg_distance < 0.5:
                quality_issues.append(f"Baja diversidad entre vectores ({avg_distance:.3f})")
                score *= 0.8
            
            if quality_issues:
                status = "warning" if score > 0.5 else "fail"
                message = f"Problemas de calidad detectados: {'; '.join(quality_issues)}"
            else:
                status = "pass"
                message = f"Calidad de embeddings aceptable (muestra de {len(vectors)} vectores)"
            
            return EmbeddingValidationResult(
                component="embeddings",
                validation_type="quality_check",
                status=status,
                message=message,
                score=score,
                details={
                    "sample_size": len(vectors),
                    "valid_vectors": valid_vectors,
                    "zero_vectors": zero_vectors,
                    "variance": round(variance, 4),
                    "avg_norm": round(avg_norm, 3),
                    "norm_std": round(norm_std, 3),
                    "avg_distance": round(avg_distance, 3),
                    "quality_issues": quality_issues
                }
            )
            
        except Exception as e:
            return EmbeddingValidationResult(
                component="embeddings",
                validation_type="quality_check",
                status="fail",
                message=f"Error en validación de calidad: {str(e)}",
                score=0.0,
                details={"error": str(e)}
            )
    
    def validate_retrieval_consistency(self, collection_name: str = "juridico", test_queries: Optional[List[str]] = None) -> EmbeddingValidationResult:
        """Valida consistencia del retrieval con consultas de prueba"""
        try:
            if not self.qdrant_client:
                return EmbeddingValidationResult(
                    component="retrieval",
                    validation_type="consistency_check",
                    status="fail",
                    message="Cliente Qdrant no disponible",
                    score=0.0
                )
            
            # Consultas de prueba por defecto para contenido jurídico
            if not test_queries:
                test_queries = [
                    "derechos humanos constitución",
                    "código civil obligaciones",
                    "procedimiento penal amparo",
                    "responsabilidad civil daños",
                    "contratos comerciales"
                ]
            
            # Necesitamos un modelo de embeddings para convertir consultas
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer('all-MiniLM-L6-v2')  # Modelo por defecto
            except ImportError:
                return EmbeddingValidationResult(
                    component="retrieval",
                    validation_type="consistency_check",
                    status="fail",
                    message="SentenceTransformers no disponible para test de retrieval",
                    score=0.0
                )
            
            results_consistency = []
            response_times = []
            
            for query in test_queries:
                start_time = time.time()
                
                # Generar embedding para la consulta
                query_vector = model.encode(query).tolist()
                
                # Realizar búsqueda
                search_result = self.qdrant_client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=5
                )
                
                end_time = time.time()
                response_times.append(end_time - start_time)
                
                # Analizar resultados
                if search_result:
                    scores = [hit.score for hit in search_result]
                    results_consistency.append({
                        'query': query,
                        'results_count': len(search_result),
                        'top_score': max(scores),
                        'score_variance': np.var(scores),
                        'response_time': end_time - start_time
                    })
                else:
                    results_consistency.append({
                        'query': query,
                        'results_count': 0,
                        'top_score': 0,
                        'score_variance': 0,
                        'response_time': end_time - start_time
                    })
            
            # Evaluar consistencia
            avg_response_time = np.mean(response_times)
            successful_queries = sum(1 for r in results_consistency if r['results_count'] > 0)
            avg_top_score = np.mean([r['top_score'] for r in results_consistency if r['top_score'] > 0])
            
            # Calcular score
            success_ratio = successful_queries / len(test_queries)
            
            if success_ratio < 0.5:
                status = "fail"
                score = 0.2
                message = f"Baja tasa de éxito en retrieval ({success_ratio:.1%})"
            elif success_ratio < 0.8:
                status = "warning"
                score = 0.6
                message = f"Retrieval parcialmente exitoso ({success_ratio:.1%})"
            else:
                status = "pass"
                score = 0.8 + (success_ratio * 0.2)
                message = f"Retrieval consistente ({success_ratio:.1%} éxito)"
            
            # Penalizar por tiempo de respuesta muy alto
            if avg_response_time > 2.0:
                score *= 0.8
                message += f" - Tiempo de respuesta alto ({avg_response_time:.2f}s)"
            
            return EmbeddingValidationResult(
                component="retrieval",
                validation_type="consistency_check",
                status=status,
                message=message,
                score=score,
                details={
                    "test_queries_count": len(test_queries),
                    "successful_queries": successful_queries,
                    "success_ratio": round(success_ratio, 3),
                    "avg_response_time": round(avg_response_time, 3),
                    "avg_top_score": round(avg_top_score, 3) if avg_top_score > 0 else 0,
                    "query_results": results_consistency
                }
            )
            
        except Exception as e:
            return EmbeddingValidationResult(
                component="retrieval",
                validation_type="consistency_check",
                status="fail",
                message=f"Error en validación de retrieval: {str(e)}",
                score=0.0,
                details={"error": str(e)}
            )
    
    def validate_index_health(self, collection_name: str = "juridico") -> EmbeddingValidationResult:
        """Valida salud general del índice de vectores"""
        try:
            if not self.qdrant_client:
                return EmbeddingValidationResult(
                    component="index",
                    validation_type="health_check",
                    status="fail",
                    message="Cliente Qdrant no disponible",
                    score=0.0
                )
            
            # Obtener información de la colección
            collection_info = self.qdrant_client.get_collection(collection_name)
            
            # Obtener estadísticas básicas
            vectors_count = collection_info.vectors_count
            
            # Verificar estado del índice
            status_info = collection_info.status
            
            health_issues = []
            score = 1.0
            
            # Verificar cantidad mínima de vectores
            if vectors_count < 10:
                health_issues.append(f"Muy pocos vectores ({vectors_count})")
                score *= 0.3
            elif vectors_count < 100:
                health_issues.append(f"Pocos vectores para validación robusta ({vectors_count})")
                score *= 0.7
            
            # Verificar estado de la colección
            if status_info != "green":
                health_issues.append(f"Estado de colección no óptimo: {status_info}")
                score *= 0.6
            
            # Verificar consistencia de payload (metadatos)
            try:
                # Obtener muestra para verificar payloads
                scroll_result = self.qdrant_client.scroll(
                    collection_name=collection_name,
                    limit=10,
                    with_payload=True
                )
                
                payloads_with_data = 0
                total_payloads = 0
                
                for point in scroll_result[0]:
                    total_payloads += 1
                    if hasattr(point, 'payload') and point.payload:
                        payloads_with_data += 1
                
                if total_payloads > 0:
                    payload_ratio = payloads_with_data / total_payloads
                    if payload_ratio < 0.5:
                        health_issues.append(f"Muchos vectores sin metadata ({payload_ratio:.1%})")
                        score *= 0.8
                
            except Exception as e:
                health_issues.append("No se pudo verificar metadata de vectores")
                score *= 0.9
            
            if health_issues:
                status = "warning" if score > 0.5 else "fail"
                message = f"Problemas de salud del índice: {'; '.join(health_issues)}"
            else:
                status = "pass"
                message = f"Índice saludable con {vectors_count} vectores"
            
            return EmbeddingValidationResult(
                component="index",
                validation_type="health_check",
                status=status,
                message=message,
                score=score,
                details={
                    "vectors_count": vectors_count,
                    "collection_status": status_info,
                    "health_issues": health_issues
                }
            )
            
        except Exception as e:
            return EmbeddingValidationResult(
                component="index",
                validation_type="health_check",
                status="fail",
                message=f"Error verificando salud del índice: {str(e)}",
                score=0.0,
                details={"error": str(e)}
            )
    
    def run_all_validations(self, collection_name: str = "juridico") -> List[EmbeddingValidationResult]:
        """Ejecuta todas las validaciones de embeddings"""
        results = []
        
        results.append(self.validate_collection_exists(collection_name))
        results.append(self.validate_embedding_dimension(collection_name))
        results.append(self.validate_embedding_quality(collection_name))
        results.append(self.validate_retrieval_consistency(collection_name))
        results.append(self.validate_index_health(collection_name))
        
        return results
    
    def get_overall_score(self, results: List[EmbeddingValidationResult]) -> float:
        """Calcula score general de validación de embeddings"""
        if not results:
            return 0.0
        
        # Pesos para diferentes tipos de validación
        weights = {
            'collection_existence': 0.20,
            'dimension_consistency': 0.15,
            'quality_check': 0.25,
            'consistency_check': 0.25,
            'health_check': 0.15
        }
        
        weighted_score = 0.0
        total_weight = 0.0
        
        for result in results:
            weight = weights.get(result.validation_type, 0.1)
            weighted_score += result.score * weight
            total_weight += weight
        
        return weighted_score / total_weight if total_weight > 0 else 0.0
    
    def print_results(self, results: List[EmbeddingValidationResult], verbose: bool = False):
        """Imprime resultados de validación de embeddings"""
        if not results:
            print("❌ No hay resultados de validación de embeddings")
            return
        
        overall_score = self.get_overall_score(results)
        
        print(f"\n🔍 Validación de Embeddings - Score General: {overall_score:.2f}")
        print(f"   {'🟢 Excelente' if overall_score >= 0.8 else '🟡 Bueno' if overall_score >= 0.6 else '🔴 Necesita Mejora'}")
        print()
        
        # Agrupar por componente
        components = defaultdict(list)
        for result in results:
            components[result.component].append(result)
        
        for component, component_results in components.items():
            print(f"📊 {component.upper()}:")
            
            for result in component_results:
                status_emoji = {'pass': '✅', 'warning': '⚠️', 'fail': '❌'}[result.status]
                print(f"   {status_emoji} {result.validation_type.replace('_', ' ').title()}: {result.score:.2f}")
                print(f"      {result.message}")
                
                if verbose and result.details:
                    print(f"      Detalles: {result.details}")
            print()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validador de embeddings RAG Jurídico")
    parser.add_argument('--collection', '-c', default='juridico', help='Nombre de la colección')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mostrar detalles adicionales')
    
    args = parser.parse_args()
    
    validator = EmbeddingValidator()
    results = validator.run_all_validations(args.collection)
    validator.print_results(results, verbose=args.verbose)
    
    # Exit con código de error si hay fallos críticos
    critical_failures = sum(1 for r in results if r.status == 'fail')
    if critical_failures > 0:
        exit(1)