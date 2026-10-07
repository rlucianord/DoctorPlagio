"""Prompts for DoctorPlagio AI Analysis V2."""
from __future__ import annotations

SYSTEM_RULES = """
No atribuyas autoría. No afirmes que un texto fue escrito por IA como un hecho.
Todas las respuestas de texto destinadas al usuario deben estar redactadas exclusivamente en español.
La puntuación representa una ESTIMACIÓN ANALÍTICA de características lingüísticas
compatibles con redacción o asistencia de IA. Una redacción formal, técnica o
uniforme no es por sí sola evidencia de IA. La información institucional específica,
normativa, procedimientos, nombres de sistemas y datos concretos pueden provenir de
fuentes humanas aunque la redacción haya sido posteriormente asistida por IA.
""".strip()


def segment_prompt(text: str, section: str, chapter: str, metrics: dict) -> str:
    return f"""
{SYSTEM_RULES}

Analiza este segmento académico como una pieza de evidencia, no como una prueba de autoría.
El CAPÍTULO y la SECCIÓN son únicamente metadata de estructura académica.
NO los uses como evidencia de IA ni evalúes sus palabras, numeración o formato.
Evalúa únicamente el contenido redactado que aparece en TEXTO: uniformidad sintáctica, patrones de redacción, vocabulario, transiciones,
redundancia semántica, señales compatibles con generación automática y señales de
intervención humana. Usa las métricas calculadas por Python como evidencia cuantitativa.

Devuelve SOLO JSON con exactamente estas claves:
ai_score (0.0-1.0), label (bajo/intermedio/alto),
syntactic_uniformity (0.0-1.0), repetitive_patterns (0.0-1.0),
vocabulary_uniformity (0.0-1.0), transition_regularity (0.0-1.0),
semantic_redundancy (0.0-1.0), ai_signals (lista breve), human_signals (lista breve),
reasoning (máximo 40 palabras), evidence_sentences (lista de máximo 5 objetos con sentence y reason).

CAPÍTULO: {chapter}
SECCIÓN: {section}
MÉTRICAS PYTHON:
{metrics}

TEXTO:
{text}

Para evidence_sentences selecciona solo oraciones concretas del texto que justifiquen
las señales observadas. No inventes ni reformules la oración: cópiala exactamente.
""".strip()


def chapter_prompt(chapter: str, pages: str, metrics: dict, segment_summaries: list[dict]) -> str:
    return f"""
{SYSTEM_RULES}

Analiza el capítulo completo a partir de los resultados de sus segmentos.
El nombre del capítulo y sus secciones son metadata estructural y no evidencia de IA.
No penalices numeración, títulos académicos, nombres de capítulos o subtítulos.
Evalúa específicamente: uniformidad sintáctica, patrones repetitivos, vocabulario,
estructura argumentativa, transiciones, redundancia semántica, contenido institucional,
fuentes/referencias, señales de generación automática y señales de redacción humana.
Compara los segmentos entre sí y evita interpretar la normalización deliberada de un
manual técnico como evidencia automática de IA.

Devuelve SOLO JSON con exactamente estas claves:
ai_score (0.0-1.0), human_score (0.0-1.0), confidence (bajo/medio/alto/muy alto),
main_patterns (lista), ai_signals (lista), human_signals (lista),
page_evidence (lista), reasoning (máximo 100 palabras).

CAPÍTULO: {chapter}
PÁGINAS: {pages}
MÉTRICAS AGREGADAS:
{metrics}

RESULTADOS DE SEGMENTOS:
{segment_summaries}
""".strip()


def document_prompt(chapter_summaries: list[dict], global_metrics: dict) -> str:
    return f"""
{SYSTEM_RULES}

Realiza un análisis transversal del documento. Los nombres y numeraciones de capítulos/secciones son metadata y no deben influir en la puntuación.
Compara únicamente el contenido evaluable de los capítulos para detectar
arquitecturas argumentativas repetidas, vocabulario y transiciones recurrentes,
cambios de estilo, inconsistencias, información institucional específica y patrones
que atraviesan el documento. No confundas redacción uniforme de un manual con IA.
Distingue claramente redacción posiblemente asistida por IA de información conceptual
que puede provenir de fuentes humanas.

Devuelve SOLO JSON con exactamente estas claves:
ai_score (0.0-1.0), human_score (0.0-1.0), confidence (bajo/medio/alto/muy alto),
recurring_patterns (lista), strongest_pages (lista), human_evidence (lista),
limitations (lista), reasoning (máximo 120 palabras), characterization (A/B/C/D/indeterminado).

A = principalmente escrito manualmente
B = escrito manualmente y posteriormente editado con IA
C = construido mediante IA a partir de información proporcionada por humanos
D = generado mayoritariamente por IA con poca intervención humana

No elijas una categoría por intuición: basa la caracterización en los datos resumidos.

MÉTRICAS GLOBALES:
{global_metrics}

RESÚMENES DE CAPÍTULOS:
{chapter_summaries}
""".strip()
