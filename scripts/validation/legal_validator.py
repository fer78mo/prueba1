#!/usr/bin/env python3
"""
Validador Específico para Contenido Jurídico

Valida la calidad, coherencia y precisión del contenido legal
en las respuestas del sistema RAG.
"""

import re
import os
import json
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
import logging
from collections import Counter

@dataclass
class LegalValidationResult:
    """Resultado de validación legal"""
    question_id: str
    validation_type: str
    status: str  # 'pass', 'warning', 'fail'
    message: str
    score: float  # 0.0 - 1.0
    details: Optional[Dict] = None

class LegalValidator:
    """Validador específico para contenido jurídico"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Patrones de referencias legales mexicanas
        self.legal_patterns = {
            'articulo': re.compile(r'\b[Aa]rt(?:ículo|iculo)?\.?\s*(\d+(?:\s*bis)?(?:\s*ter)?(?:\s*qu[aá]ter)?)', re.IGNORECASE),
            'fraccion': re.compile(r'\b[Ff]racc(?:ión|ion)?\.?\s*([IVX]+|\d+)', re.IGNORECASE),
            'inciso': re.compile(r'\b[Ii]nciso\s*([a-z])\)', re.IGNORECASE),
            'numeral': re.compile(r'\b[Nn]umeral\s*(\d+)', re.IGNORECASE),
            'parrafo': re.compile(r'\b[Pp]árrafo\s*(\d+)', re.IGNORECASE),
            'codigo': re.compile(r'\b[Cc]ódigo\s+(?:Civil|Penal|Federal|de\s+(?:Comercio|Procedimientos))[a-zA-ZÁáÉéÍíÓóÚúÜüÑñ\s]*', re.IGNORECASE),
            'ley': re.compile(r'\b[Ll]ey\s+(?:General|Federal|de)?[a-zA-ZÁáÉéÍíÓóÚúÜüÑñ\s]+', re.IGNORECASE),
            'constitucion': re.compile(r'\b[Cc]onstitución\s+Política', re.IGNORECASE),
            'jurisprudencia': re.compile(r'\b[Jj]urisprudencia\s+(?:obligatoria|aislada)', re.IGNORECASE),
            'tesis': re.compile(r'\b[Tt]esis\s+[IVX]+\.\d+[A-Za-z]*', re.IGNORECASE)
        }
        
        # Términos jurídicos que deberían aparecer en contextos legales
        self.legal_terms = {
            'procedimientos': ['debido proceso', 'audiencia', 'notificación', 'emplazamiento', 'sentencia'],
            'derechos': ['garantías individuales', 'derechos humanos', 'amparo', 'protección'],
            'responsabilidad': ['culpa', 'dolo', 'negligencia', 'responsabilidad civil', 'daños y perjuicios'],
            'contratos': ['contrato', 'obligación', 'prestación', 'cumplimiento', 'incumplimiento'],
            'penal': ['delito', 'pena', 'sanción', 'tipo penal', 'antijuridicidad', 'culpabilidad']
        }
        
        # Indicadores de calidad jurídica
        self.quality_indicators = {
            'precision': ['específicamente', 'en particular', 'conforme a', 'de acuerdo con'],
            'fundamentacion': ['en virtud de', 'con base en', 'de conformidad con', 'según establece'],
            'analisis': ['por tanto', 'en consecuencia', 'se desprende que', 'se concluye que'],
            'contexto': ['en el contexto de', 'en el ámbito de', 'tratándose de', 'en materia de']
        }
    
    def validate_legal_references(self, text: str, question_id: str) -> LegalValidationResult:
        """Valida referencias legales en el texto"""
        references_found = {}
        total_references = 0
        
        for ref_type, pattern in self.legal_patterns.items():
            matches = pattern.findall(text)
            if matches:
                references_found[ref_type] = matches
                total_references += len(matches)
        
        # Calcular score basado en cantidad y diversidad de referencias
        if total_references == 0:
            score = 0.0
            status = 'warning'
            message = "No se encontraron referencias legales específicas"
        elif total_references < 3:
            score = 0.4
            status = 'warning'
            message = f"Pocas referencias legales encontradas ({total_references})"
        else:
            # Bonus por diversidad de tipos de referencias
            diversity_bonus = len(references_found) * 0.1
            score = min(0.7 + diversity_bonus, 1.0)
            status = 'pass'
            message = f"Referencias legales adecuadas ({total_references} referencias de {len(references_found)} tipos)"
        
        return LegalValidationResult(
            question_id=question_id,
            validation_type='legal_references',
            status=status,
            message=message,
            score=score,
            details={
                'total_references': total_references,
                'references_by_type': references_found,
                'diversity_score': len(references_found)
            }
        )
    
    def validate_legal_terminology(self, text: str, question_id: str) -> LegalValidationResult:
        """Valida uso apropiado de terminología jurídica"""
        text_lower = text.lower()
        terms_found = {}
        total_terms = 0
        
        for category, terms in self.legal_terms.items():
            found_in_category = []
            for term in terms:
                if term.lower() in text_lower:
                    found_in_category.append(term)
                    total_terms += 1
            
            if found_in_category:
                terms_found[category] = found_in_category
        
        # Evaluar calidad terminológica
        if total_terms == 0:
            score = 0.0
            status = 'fail'
            message = "No se encontró terminología jurídica apropiada"
        elif total_terms < 3:
            score = 0.3
            status = 'warning'
            message = f"Terminología jurídica limitada ({total_terms} términos)"
        else:
            score = min(0.6 + (len(terms_found) * 0.1), 1.0)
            status = 'pass'
            message = f"Terminología jurídica apropiada ({total_terms} términos de {len(terms_found)} categorías)"
        
        return LegalValidationResult(
            question_id=question_id,
            validation_type='legal_terminology',
            status=status,
            message=message,
            score=score,
            details={
                'total_terms': total_terms,
                'terms_by_category': terms_found,
                'categories_covered': len(terms_found)
            }
        )
    
    def validate_response_structure(self, text: str, question_id: str) -> LegalValidationResult:
        """Valida estructura de respuesta jurídica"""
        indicators_found = {}
        total_indicators = 0
        
        for indicator_type, phrases in self.quality_indicators.items():
            found_phrases = []
            for phrase in phrases:
                if phrase.lower() in text.lower():
                    found_phrases.append(phrase)
                    total_indicators += 1
            
            if found_phrases:
                indicators_found[indicator_type] = found_phrases
        
        # Evaluar estructura y calidad argumentativa
        text_sentences = text.split('.')
        avg_sentence_length = sum(len(s.split()) for s in text_sentences) / len(text_sentences) if text_sentences else 0
        
        # Evaluar score basado en indicadores de calidad
        if total_indicators == 0:
            score = 0.2
            status = 'warning'
            message = "Estructura argumentativa básica, faltan conectores jurídicos"
        elif total_indicators < 3:
            score = 0.5
            status = 'warning'
            message = f"Estructura argumentativa mejorable ({total_indicators} indicadores)"
        else:
            score = min(0.7 + (len(indicators_found) * 0.05), 1.0)
            status = 'pass'
            message = f"Buena estructura argumentativa ({total_indicators} indicadores de {len(indicators_found)} tipos)"
        
        # Ajustar por longitud de oraciones (muy cortas o muy largas pueden indicar problemas)
        if avg_sentence_length < 8 or avg_sentence_length > 40:
            score *= 0.9
            
        return LegalValidationResult(
            question_id=question_id,
            validation_type='response_structure',
            status=status,
            message=message,
            score=score,
            details={
                'quality_indicators': indicators_found,
                'total_indicators': total_indicators,
                'avg_sentence_length': round(avg_sentence_length, 2),
                'total_sentences': len(text_sentences)
            }
        )
    
    def validate_citation_format(self, text: str, question_id: str) -> LegalValidationResult:
        """Valida formato de citaciones legales"""
        # Patrones de citación formal
        citation_patterns = [
            re.compile(r'\b[Aa]rtículo\s+\d+(?:\s*bis)?(?:\s*ter)?(?:\s*quáter)?\s+(?:del|de\s+la)\s+[A-Z][a-záéíóú\s]+', re.IGNORECASE),
            re.compile(r'\b[Ff]racción\s+[IVX]+\s+del\s+[Aa]rtículo\s+\d+', re.IGNORECASE),
            re.compile(r'\b[Tt]esis\s+[IVX]+\.\d+[A-Za-z]*\s*\(.+\)', re.IGNORECASE)
        ]
        
        formal_citations = 0
        citation_details = []
        
        for pattern in citation_patterns:
            matches = pattern.finditer(text)
            for match in matches:
                formal_citations += 1
                citation_details.append({
                    'text': match.group(),
                    'start': match.start(),
                    'end': match.end()
                })
        
        # Evaluar calidad de citaciones
        if formal_citations == 0:
            score = 0.0
            status = 'warning'
            message = "No se encontraron citaciones formales"
        elif formal_citations < 2:
            score = 0.4
            status = 'warning'
            message = f"Pocas citaciones formales ({formal_citations})"
        else:
            score = min(0.6 + (formal_citations * 0.1), 1.0)
            status = 'pass'
            message = f"Citaciones formales adecuadas ({formal_citations})"
        
        return LegalValidationResult(
            question_id=question_id,
            validation_type='citation_format',
            status=status,
            message=message,
            score=score,
            details={
                'formal_citations_count': formal_citations,
                'citations': citation_details[:5]  # Limitar a 5 para no saturar
            }
        )
    
    def validate_legal_coherence(self, question: str, answer: str, question_id: str) -> LegalValidationResult:
        """Valida coherencia entre pregunta y respuesta legal"""
        question_lower = question.lower()
        answer_lower = answer.lower()
        
        # Extraer términos clave de la pregunta
        question_legal_terms = set()
        for category, terms in self.legal_terms.items():
            for term in terms:
                if term.lower() in question_lower:
                    question_legal_terms.add(term)
        
        # Verificar si la respuesta aborda los términos de la pregunta
        addressed_terms = set()
        for term in question_legal_terms:
            if term.lower() in answer_lower:
                addressed_terms.add(term)
        
        # Calcular coherencia
        if not question_legal_terms:
            # Si la pregunta no tiene términos legales específicos, evaluar coherencia general
            score = 0.6
            status = 'pass'
            message = "Pregunta general, respuesta contextualmente apropiada"
        else:
            coherence_ratio = len(addressed_terms) / len(question_legal_terms)
            
            if coherence_ratio < 0.3:
                score = 0.2
                status = 'fail'
                message = f"Baja coherencia: respuesta no aborda términos clave de la pregunta ({len(addressed_terms)}/{len(question_legal_terms)})"
            elif coherence_ratio < 0.7:
                score = 0.5
                status = 'warning'
                message = f"Coherencia parcial: algunos términos clave no abordados ({len(addressed_terms)}/{len(question_legal_terms)})"
            else:
                score = 0.8 + (coherence_ratio * 0.2)
                status = 'pass'
                message = f"Buena coherencia: respuesta aborda los términos clave ({len(addressed_terms)}/{len(question_legal_terms)})"
        
        return LegalValidationResult(
            question_id=question_id,
            validation_type='legal_coherence',
            status=status,
            message=message,
            score=score,
            details={
                'question_terms': list(question_legal_terms),
                'addressed_terms': list(addressed_terms),
                'coherence_ratio': round(len(addressed_terms) / len(question_legal_terms) if question_legal_terms else 1.0, 3)
            }
        )
    
    def validate_response(self, question: str, answer: str, question_id: str) -> List[LegalValidationResult]:
        """Ejecuta todas las validaciones legales para una respuesta"""
        results = []
        
        # Validaciones del contenido de la respuesta
        results.append(self.validate_legal_references(answer, question_id))
        results.append(self.validate_legal_terminology(answer, question_id))
        results.append(self.validate_response_structure(answer, question_id))
        results.append(self.validate_citation_format(answer, question_id))
        
        # Validación de coherencia entre pregunta y respuesta
        results.append(self.validate_legal_coherence(question, answer, question_id))
        
        return results
    
    def get_overall_score(self, results: List[LegalValidationResult]) -> float:
        """Calcula score general de validación legal"""
        if not results:
            return 0.0
        
        # Pesos para diferentes tipos de validación
        weights = {
            'legal_references': 0.25,
            'legal_terminology': 0.20,
            'response_structure': 0.15,
            'citation_format': 0.15,
            'legal_coherence': 0.25
        }
        
        weighted_score = 0.0
        total_weight = 0.0
        
        for result in results:
            weight = weights.get(result.validation_type, 0.1)
            weighted_score += result.score * weight
            total_weight += weight
        
        return weighted_score / total_weight if total_weight > 0 else 0.0
    
    def print_results(self, results: List[LegalValidationResult], verbose: bool = False):
        """Imprime resultados de validación legal"""
        if not results:
            print("❌ No hay resultados de validación legal")
            return
        
        overall_score = self.get_overall_score(results)
        
        print(f"\n⚖️  Validación Legal - Score General: {overall_score:.2f}")
        print(f"   {'🟢 Excelente' if overall_score >= 0.8 else '🟡 Bueno' if overall_score >= 0.6 else '🔴 Necesita Mejora'}")
        print()
        
        for result in results:
            status_emoji = {'pass': '✅', 'warning': '⚠️', 'fail': '❌'}[result.status]
            print(f"{status_emoji} {result.validation_type.replace('_', ' ').title()}: {result.score:.2f}")
            print(f"   {result.message}")
            
            if verbose and result.details:
                print(f"   Detalles: {result.details}")
            print()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validador de contenido jurídico")
    parser.add_argument('--question', '-q', required=True, help='Pregunta a validar')
    parser.add_argument('--answer', '-a', required=True, help='Respuesta a validar')
    parser.add_argument('--id', default='test', help='ID de la pregunta')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mostrar detalles adicionales')
    
    args = parser.parse_args()
    
    validator = LegalValidator()
    results = validator.validate_response(args.question, args.answer, args.id)
    validator.print_results(results, verbose=args.verbose)