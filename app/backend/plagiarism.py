from __future__ import annotations
import asyncio
import json
import re
from pathlib import Path
import sys
import httpx
import numpy as np

from backend.local_llm import generate_json
# ============================================================
# RUTA DEL PROYECTO
# ============================================================

path_actual = Path(__file__).resolve()
raiz_proyecto = path_actual.parents[2]

if str(raiz_proyecto) not in sys.path:
    sys.path.insert(0, str(raiz_proyecto))


# ============================================================
# IMPORTACIONES DEL PROYECTO
# ============================================================

from backend.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from backend.vector_store import get_collection

from backend.similarity_engine import (
    get_model,
    sentence_chunks,
    analyze_fragment_against_candidate,
    SEMANTIC_CANDIDATE_MIN,
    TOP_K,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

# Tamaño objetivo de los bloques de IA.
#
# IMPORTANTE:
# Esto NO significa que el documento se limite a este tamaño.
# Se crearán tantos bloques como sean necesarios para cubrir
# TODO el documento.
AI_TARGET_CHARS = 6000

# Máximo aproximado de un bloque.
# Intentamos no superarlo, pero nunca cortamos una oración
# arbitrariamente.
AI_MAX_CHARS = 9000

# Tamaño mínimo deseable.
AI_MIN_CHARS = 2500

# Cuando una sección está cerca del límite, utilizamos
# embeddings para encontrar el mejor punto de corte.
#
# El embedding NO corta cada vez que cambia el tema.
# Solamente ayuda a elegir entre varios puntos de corte
# posibles.
SEMANTIC_BREAK_WINDOW = 4

# Ollama
OLLAMA_TIMEOUT = 300.0
OLLAMA_NUM_PREDICT = 300


# ============================================================
# LIMPIEZA
# ============================================================

def _clean_for_embedding(text: str) -> str:
    """
    Normaliza espacios sin eliminar contenido.
    """
    return re.sub(r"\s+", " ", text).strip()


def _normalize_document(text: str) -> str:
    """
    Normaliza saltos de línea conservando la estructura
    de párrafos.
    """

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Espacios horizontales.
    text = re.sub(r"[ \t]+", " ", text)

    # Demasiados saltos de línea -> máximo 2.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# DETECCIÓN DE ESTRUCTURA ACADÉMICA
# ============================================================

def _looks_like_heading(paragraph: str) -> bool:
    """
    Determina si un párrafo parece ser un encabezado académico.

    No pretende comprender perfectamente la tesis.
    Busca señales típicas:

    - CAPÍTULO I
    - CAPÍTULO 1
    - 1. INTRODUCCIÓN
    - 1.1 Marco teórico
    - INTRODUCCIÓN
    - METODOLOGÍA
    - RESULTADOS
    - CONCLUSIONES
    - REFERENCIAS
    """

    text = paragraph.strip()

    if not text:
        return False

    # Demasiado largo para ser un encabezado.
    if len(text) > 180:
        return False

    # Encabezado con numeración:
    #
    # 1.
    # 1.1
    # 2.3.4
    # 1)
    # 1.2)
    numbered_heading = re.match(
        r"^(?:\d+(?:\.\d+)*[\.\)]?)\s+\S+",
        text,
        flags=re.UNICODE,
    )

    if numbered_heading:
        return True

    # Capítulos.
    chapter_heading = re.match(
        r"^(?:CAP[IÍ]TULO|CHAPTER)\s+"
        r"(?:[IVXLCDM]+|\d+)",
        text,
        flags=re.IGNORECASE,
    )

    if chapter_heading:
        return True

    # Encabezados académicos comunes.
    academic_headings = {
        "introducción",
        "introduccion",
        "resumen",
        "abstract",
        "justificación",
        "justificacion",
        "planteamiento del problema",
        "objetivos",
        "objetivo general",
        "objetivos generales",
        "objetivos específicos",
        "objetivos especificos",
        "marco teórico",
        "marco teorico",
        "marco conceptual",
        "marco metodológico",
        "marco metodologico",
        "metodología",
        "metodologia",
        "método",
        "metodo",
        "resultados",
        "análisis de resultados",
        "analisis de resultados",
        "discusión",
        "discusion",
        "conclusiones",
        "recomendaciones",
        "referencias",
        "referencias bibliográficas",
        "referencias bibliograficas",
        "bibliografía",
        "bibliografia",
        "anexos",
        "anexo",
    }

    normalized = re.sub(
        r"\s+",
        " ",
        text.lower(),
    ).strip()

    if normalized in academic_headings:
        return True

    # Texto completamente en mayúsculas y relativamente corto.
    letters = re.sub(
        r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]",
        "",
        text,
    )

    if len(letters) >= 4:
        uppercase_ratio = sum(
            1
            for char in letters
            if char.isupper()
        ) / len(letters)

        if uppercase_ratio > 0.85 and len(text) <= 120:
            return True

    return False


# ============================================================
# EXTRACCIÓN DE UNIDADES ACADÉMICAS
# ============================================================

def _academic_units(text: str) -> list[dict]:
    """
    Convierte el documento en unidades estructurales.

    Cada unidad es:

        {
            "text": "...",
            "heading": True/False
        }

    No elimina contenido.
    """

    normalized = _normalize_document(text)

    if not normalized:
        return []

    raw_paragraphs = re.split(
        r"\n\s*\n",
        normalized,
    )

    units = []

    for paragraph in raw_paragraphs:

        paragraph = paragraph.strip()

        if not paragraph:
            continue

        units.append(
            {
                "text": paragraph,
                "heading": _looks_like_heading(paragraph),
            }
        )

    return units


# ============================================================
# EMBEDDINGS PARA ELEGIR PUNTOS DE CORTE
# ============================================================

def _embedding_similarity(
    embedding_a,
    embedding_b,
) -> float:

    return float(
        np.dot(
            embedding_a,
            embedding_b,
        )
    )


# ============================================================
# CORTE INTELIGENTE DE UNA SECCIÓN LARGA
# ============================================================

def _split_large_section(
    paragraphs: list[str],
    model,
) -> list[str]:
    """
    Divide una sección grande respetando párrafos.

    El embedding solamente ayuda a seleccionar el mejor
    punto de corte cerca del tamaño objetivo.

    Esto evita el problema anterior de generar más de 100
    bloques en un documento de 50 páginas.
    """

    if not paragraphs:
        return []

    if len(paragraphs) == 1:

        text = paragraphs[0]

        if len(text) <= AI_MAX_CHARS:
            return [text]

        # Párrafo excepcionalmente largo.
        # En este caso sí debemos dividirlo, pero por oraciones.
        sentences = re.split(
            r"(?<=[.!?])\s+",
            text,
        )

        chunks = []
        current = []

        current_length = 0

        for sentence in sentences:

            sentence = sentence.strip()

            if not sentence:
                continue

            if (
                current
                and
                current_length + len(sentence) + 1
                > AI_MAX_CHARS
            ):

                chunks.append(
                    " ".join(current)
                )

                current = [sentence]
                current_length = len(sentence)

            else:

                current.append(sentence)
                current_length += (
                    len(sentence) + 1
                )

        if current:
            chunks.append(
                " ".join(current)
            )

        return chunks

    embeddings = model.encode(
        paragraphs,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
        batch_size=32,
    )

    chunks = []

    start = 0

    while start < len(paragraphs):

        current_length = 0
        end = start

        while (
            end < len(paragraphs)
            and
            current_length
            + len(paragraphs[end])
            + 2
            <= AI_MAX_CHARS
        ):

            current_length += (
                len(paragraphs[end]) + 2
            )

            end += 1

        # Llegamos al final.
        if end >= len(paragraphs):

            chunks.append(
                "\n\n".join(
                    paragraphs[start:]
                )
            )

            break

        # Si el bloque todavía es pequeño,
        # intentamos llevarlo al menos al objetivo.
        if current_length < AI_TARGET_CHARS:

            while (
                end < len(paragraphs)
                and current_length < AI_TARGET_CHARS
            ):

                current_length += (
                    len(paragraphs[end]) + 2
                )

                end += 1

            if end >= len(paragraphs):

                chunks.append(
                    "\n\n".join(
                        paragraphs[start:]
                    )
                )

                break

        # ----------------------------------------------------
        # Tenemos un bloque candidato.
        #
        # Buscamos un punto natural cerca del objetivo.
        # ----------------------------------------------------

        candidate_start = max(
            start + 1,
            end - SEMANTIC_BREAK_WINDOW,
        )

        candidate_end = min(
            len(paragraphs) - 1,
            end + SEMANTIC_BREAK_WINDOW,
        )

        best_cut = end
        best_score = float("inf")

        for cut in range(
            candidate_start,
            candidate_end + 1,
        ):

            if cut >= len(paragraphs):
                break

            left_embedding = embeddings[cut - 1]
            right_embedding = embeddings[cut]

            similarity = _embedding_similarity(
                left_embedding,
                right_embedding,
            )

            # Preferimos cortes con menor continuidad
            # semántica entre ambos lados.
            distance = 1.0 - similarity

            # Penalización ligera si nos alejamos demasiado
            # del tamaño objetivo.
            size = sum(
                len(paragraphs[i]) + 2
                for i in range(start, cut)
            )

            size_penalty = (
                abs(size - AI_TARGET_CHARS)
                / AI_TARGET_CHARS
            ) * 0.15

            score = distance + size_penalty

            if score < best_score:
                best_score = score
                best_cut = cut

        if best_cut <= start:
            best_cut = min(
                start + 1,
                len(paragraphs),
            )

        chunks.append(
            "\n\n".join(
                paragraphs[start:best_cut]
            )
        )

        start = best_cut

    return [
        chunk.strip()
        for chunk in chunks
        if chunk.strip()
    ]


# ============================================================
# CHUNKING ACADÉMICO COMPLETO
# ============================================================

def academic_chunks(
    text: str,
) -> list[dict]:
    """
    Divide TODO el documento respetando su estructura académica.

    Características:

    - Conserva encabezados.
    - Conserva párrafos.
    - No corta por cada cambio semántico.
    - Utiliza embeddings solamente para elegir puntos
      de corte dentro de secciones grandes.
    - Genera bloques grandes.
    - Devuelve posición y sección.

    El resultado cubre el 100% del texto recibido.
    """

    units = _academic_units(text)

    if not units:
        return []

    model = get_model()

    sections = []

    current_heading = "Documento"

    current_paragraphs = []

    for unit in units:

        if unit["heading"]:

            # Guardar sección anterior.
            if current_paragraphs:

                sections.append(
                    {
                        "heading": current_heading,
                        "paragraphs": current_paragraphs,
                    }
                )

            current_heading = unit["text"]

            current_paragraphs = []

        else:

            current_paragraphs.append(
                unit["text"]
            )

    # Última sección.
    if current_paragraphs:

        sections.append(
            {
                "heading": current_heading,
                "paragraphs": current_paragraphs,
            }
        )

    all_chunks = []

    for section in sections:

        heading = section["heading"]
        paragraphs = section["paragraphs"]

        if not paragraphs:
            continue

        # El encabezado se incluye en el primer bloque
        # de su sección para conservar contexto.
        section_chunks = _split_large_section(
            paragraphs,
            model,
        )

        for index, chunk in enumerate(
            section_chunks
        ):

            if index == 0 and heading != "Documento":

                chunk_text = (
                    f"{heading}\n\n{chunk}"
                )

            else:

                chunk_text = chunk

            all_chunks.append(
                {
                    "section": heading,
                    "text": chunk_text,
                }
            )

    # Si no se detectaron secciones.
    if not all_chunks:

        fallback = _split_large_section(
            [
                unit["text"]
                for unit in units
            ],
            model,
        )

        all_chunks = [
            {
                "section": "Documento",
                "text": chunk,
            }
            for chunk in fallback
        ]

    # --------------------------------------------------------
    # VERIFICACIÓN DE COBERTURA
    # --------------------------------------------------------

    original_length = len(
        _clean_for_embedding(text)
    )

    chunked_length = sum(
        len(
            _clean_for_embedding(
                chunk["text"]
            )
        )
        for chunk in all_chunks
    )

    print(
        f"📚 Documento: {original_length:,} caracteres"
    )

    print(
        f"📦 Bloques académicos: "
        f"{len(all_chunks)}"
    )

    print(
        f"📦 Caracteres contenidos en bloques: "
        f"{chunked_length:,}"
    )

    return all_chunks


# ============================================================
# ANÁLISIS DE IA DE UN BLOQUE
# ============================================================
print("🔎 PLAGIARISM.PY CARGADO:", __file__)
print("🔎 ASYNCIO DISPONIBLE:", asyncio)
async def analyze_ai_chunk(
    chunk: dict,
    chunk_number: int,
    total_chunks: int,
):
    """
    Analiza un bloque académico con el modelo local
    mediante llama.cpp.

    El modelo estima únicamente la presencia de
    características lingüísticas compatibles con
    generación automática.

    ai_score NO representa una probabilidad de autoría.
    """

    text = _clean_for_embedding(chunk["text"])

    if not text:
        return None

    prompt = f"""
Analiza el siguiente texto académico.

Evalúa únicamente qué tan presentes están características
lingüísticas que pueden ser compatibles con generación automática.

NO determines quién escribió el texto.
NO afirmes que fue escrito por IA.
NO confundas el tema o la calidad del contenido con generación automática.

Considera, cuando existan:

- uniformidad excesiva del estilo;
- patrones sintácticos repetitivos;
- formulaciones genéricas o poco específicas;
- transiciones excesivamente regulares;
- repetición de estructuras;
- lenguaje artificialmente uniforme;
- cambios poco naturales de estilo;
- señales lingüísticas observables que puedan ser compatibles
  con generación automática.

IMPORTANTE:
Una redacción clara, correcta, académica o formal NO constituye
por sí sola evidencia de generación automática.

Devuelve ÚNICAMENTE un objeto JSON válido.

El JSON debe tener exactamente estas tres claves:

{{
    "ai_score": 0.0,
    "label": "bajo",
    "reasoning": "explicación breve"
}}

Reglas para ai_score:

0.0 = muy pocas características compatibles con generación automática
0.5 = presencia moderada
1.0 = presencia alta

El valor debe ser un número entre 0.0 y 1.0.

El razonamiento debe describir características observables
del texto y tener como máximo dos oraciones.

La etiqueta debe ser una de estas:

"bajo"
"intermedio"
"alto"

SECCIÓN:
{chunk["section"]}

TEXTO:
{text}
"""

    try:

        # llama.cpp es síncrono.
        # Lo ejecutamos en un hilo para no bloquear
        # el flujo async.

        ai_data = await asyncio.to_thread(
            generate_json,
            prompt,
            300,
            0.0,
            42,
        )

        print("🔎 RESPUESTA DEL MODELO:")
        print(ai_data)

        # --------------------------------------------------
        # Validar respuesta
        # --------------------------------------------------

        if not isinstance(ai_data, dict):

            print(
                f"⚠️ Respuesta inválida del modelo local "
                f"en bloque {chunk_number}/{total_chunks}"
            )

            return {
                "available": False,
                "chunk": chunk_number,
                "section": chunk["section"],
                "characters": len(text),
                "ai_score": None,
                "human_score": None,
                "label": "No disponible",
                "reasoning": (
                    "El modelo local no devolvió "
                    "un objeto JSON válido."
                ),
            }

        if "error" in ai_data:

            print(
                f"⚠️ JSON inválido del modelo local "
                f"en bloque {chunk_number}/{total_chunks}"
            )

            return {
                "available": False,
                "chunk": chunk_number,
                "section": chunk["section"],
                "characters": len(text),
                "ai_score": None,
                "human_score": None,
                "label": "No disponible",
                "reasoning": (
                    "El modelo local no pudo generar "
                    "una respuesta JSON válida."
                ),
            }

        # --------------------------------------------------
        # Obtener score
        # --------------------------------------------------

        raw_score = ai_data.get("ai_score")

        try:
            score = float(raw_score)

        except (TypeError, ValueError):

            print(
                f"⚠️ ai_score inválido "
                f"en bloque {chunk_number}: "
                f"{raw_score}"
            )

            return {
                "available": False,
                "chunk": chunk_number,
                "section": chunk["section"],
                "characters": len(text),
                "ai_score": None,
                "human_score": None,
                "label": "No disponible",
                "reasoning": "ai_score inválido.",
            }

        # --------------------------------------------------
        # Normalizar score
        # --------------------------------------------------

        score = max(
            0.0,
            min(1.0, score)
        )

        # --------------------------------------------------
        # La etiqueta la determina DoctorPlagio,
        # NO el modelo.
        # --------------------------------------------------

        if score < 0.40:

            label = "bajo"

        elif score < 0.70:

            label = "intermedio"

        else:

            label = "alto"

        # --------------------------------------------------
        # Resultado
        # --------------------------------------------------

        return {
            "available": True,
            "chunk": chunk_number,
            "section": chunk["section"],
            "characters": len(text),

            "ai_score": round(
                score,
                4,
            ),

            "human_score": round(
                1.0 - score,
                4,
            ),

            "label": label,

            "reasoning": ai_data.get(
                "reasoning",
                "Análisis completado.",
            ),

            "text_preview": text[:300],
        }

    except Exception as exc:

        print(
            f"⚠️ Error en análisis de IA "
            f"del bloque {chunk_number}/{total_chunks}: "
            f"{exc}"
        )

        print(
            f"Tipo de error: {type(exc).__name__}"
        )

        return {
            "available": False,
            "chunk": chunk_number,
            "section": chunk["section"],
            "characters": len(text),
            "ai_score": None,
            "human_score": None,
            "label": "No disponible",
            "reasoning": str(exc),
        }
# ============================================================
# ANÁLISIS DE IA DEL DOCUMENTO COMPLETO
# ============================================================

async def analyze_ai_document(
    text: str,
):
    """
    Analiza el documento COMPLETO.

    No utiliza text[:1500].
    No utiliza text[:2000].

    Todos los bloques académicos participan.
    """

    clean_text = _normalize_document(
        text
    )

    if not clean_text:

        return {
            "available": False,
            "ai_score": None,
            "human_score": None,
            "label": "No disponible",
            "reasoning": (
                "El documento no contiene texto."
            ),
            "chunks_analyzed": 0,
            "chunks_successful": 0,
            "chunks": [],
        }

    print(
        "🧠 Preparando análisis completo "
        "del documento..."
    )

    chunks = academic_chunks(
        clean_text
    )

    total_chunks = len(chunks)

    print(
        f"🧠 Se analizarán "
        f"{total_chunks} bloques académicos."
    )

    results = []

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):

        print(
            f"🧠 IA: bloque "
            f"{index}/{total_chunks} "
            f"| sección: "
            f"{chunk['section']} "
            f"| caracteres: "
            f"{len(chunk['text']):,}"
        )

        result = await analyze_ai_chunk(
            chunk,
            index,
            total_chunks,
        )

        if result is not None:
            results.append(result)

    valid_results = [
        result
        for result in results
        if (
            result.get("available")
            and result.get("ai_score")
            is not None
        )
    ]

    if not valid_results:

        return {
            "available": False,
            "ai_score": None,
            "human_score": None,
            "label": "No disponible",
            "reasoning": (
                "No fue posible analizar "
                "ningún bloque."
            ),
            "chunks_analyzed": total_chunks,
            "chunks_successful": 0,
            "chunks_failed": total_chunks,
            "chunks": results,
        }

    # ========================================================
    # PROMEDIO PONDERADO POR TEXTO
    # ========================================================

    total_characters = sum(
        result["characters"]
        for result in valid_results
    )

    if total_characters <= 0:

        global_score = 0.0

    else:

        global_score = (
            sum(
                result["ai_score"]
                * result["characters"]
                for result in valid_results
            )
            / total_characters
        )

    global_score = max(
        0.0,
        min(1.0, global_score),
    )

    scores = [
        result["ai_score"]
        for result in valid_results
    ]

    # ========================================================
    # SECCIONES
    # ========================================================

    section_scores = {}

    for result in valid_results:

        section = result.get(
            "section",
            "Documento",
        )

        if section not in section_scores:
            section_scores[section] = {
                "characters": 0,
                "weighted_score": 0.0,
                "chunks": 0,
            }

        section_scores[section][
            "characters"
        ] += result["characters"]

        section_scores[section][
            "weighted_score"
        ] += (
            result["ai_score"]
            * result["characters"]
        )

        section_scores[section][
            "chunks"
        ] += 1

    for section, data in section_scores.items():

        if data["characters"] > 0:

            data["ai_score"] = round(
                data["weighted_score"]
                / data["characters"],
                4,
            )

        else:

            data["ai_score"] = None

        del data["weighted_score"]

    # ========================================================
    # RESULTADO
    # ========================================================

    return {
        "available": True,

        "ai_score": round(
            global_score,
            4,
        ),

        "human_score": round(
            1.0 - global_score,
            4,
        ),

        "label": (
            "AI-generated"
            if global_score > 0.5
            else "Human-written"
        ),

        "reasoning": (
            "Estimación calculada mediante el análisis "
            f"de {len(valid_results)} bloques académicos "
            "que cubren el documento completo. "
            "La puntuación global está ponderada "
            "por la cantidad de texto analizado."
        ),

        "chunks_analyzed": total_chunks,

        "chunks_successful": len(
            valid_results
        ),

        "chunks_failed": (
            total_chunks
            - len(valid_results)
        ),

        "score_range": {
            "minimum": round(
                min(scores),
                4,
            ),
            "maximum": round(
                max(scores),
                4,
            ),
        },

        "sections": section_scores,

        "chunks": results,
    }


# ============================================================
# ANÁLISIS DE PLAGIO
# ============================================================

async def analyze_plagiarism(
    document_content: str,
    db_session=None,
):
    """
    Analiza el documento contra la colección Chroma V1.1.

    El porcentaje de plagio representa cobertura de evidencia,
    no una probabilidad matemática de plagio.

    El análisis de IA se realiza sobre TODO el documento.
    """

    text = _clean_for_embedding(
        document_content
    )

    if not text:

        return {
            "plagiarism_percentage": 0.0,
            "details": [],
            "ai_analysis": {
                "available": False,
                "ai_score": None,
                "human_score": None,
                "label": "No disponible",
                "reasoning": (
                    "Documento vacío."
                ),
            },
        }

    # ========================================================
    # FRAGMENTOS PARA PLAGIO
    # ========================================================

    fragments = sentence_chunks(
        text
    )

    if not fragments:

        return {
            "plagiarism_percentage": 0.0,
            "details": [],
            "ai_analysis": {
                "available": False,
                "ai_score": None,
                "human_score": None,
                "label": "No disponible",
                "reasoning": (
                    "No fue posible crear "
                    "fragmentos."
                ),
            },
        }

    print(
        f"🔎 Analizando plagio en "
        f"{len(fragments)} fragmentos..."
    )

    collection = get_collection()

    model = get_model()

    details = []

    flagged_fragments = 0

    # ========================================================
    # PLAGIO
    # ========================================================

    for fragment in fragments:

        embedding = model.encode(
            [fragment],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0].astype(
            "float32"
        ).tolist()

        results = collection.query(
            query_embeddings=[embedding],
            n_results=min(
                TOP_K,
                max(
                    1,
                    collection.count(),
                ),
            ),
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

        docs = (
            results.get(
                "documents"
            )
            or [[]]
        )[0]

        metas = (
            results.get(
                "metadatas"
            )
            or [[]]
        )[0]

        distances = (
            results.get(
                "distances"
            )
            or [[]]
        )[0]

        best_for_fragment = None

        for (
            candidate,
            metadata,
            distance,
        ) in zip(
            docs,
            metas,
            distances,
        ):

            semantic = max(
                0.0,
                min(
                    1.0,
                    1.0
                    - float(distance),
                ),
            )

            if (
                semantic
                < SEMANTIC_CANDIDATE_MIN
            ):
                continue

            evidence = (
                analyze_fragment_against_candidate(
                    fragment,
                    candidate,
                    semantic,
                )
            )

            evidence["source"] = (
                metadata or {}
            ).get(
                "source",
                "Desconocido",
            )

            evidence["fragment"] = (
                fragment[:500]
            )

            evidence[
                "matched_fragment"
            ] = candidate[:500]

            if (
                best_for_fragment is None
                or
                evidence[
                    "evidence_score"
                ]
                >
                best_for_fragment[
                    "evidence_score"
                ]
            ):

                best_for_fragment = evidence

        if best_for_fragment:

            if (
                best_for_fragment[
                    "classification"
                ]
                in {
                    "probable_copy",
                    "probable_paraphrase",
                    "textual_overlap",
                }
                and
                best_for_fragment[
                    "evidence_score"
                ]
                >= 0.50
            ):

                flagged_fragments += 1

                details.append(
                    best_for_fragment
                )

    # ========================================================
    # COBERTURA DE PLAGIO
    # ========================================================

    coverage = (
        flagged_fragments
        / len(fragments)
    ) * 100.0

    # ========================================================
    # IA — DOCUMENTO COMPLETO
    # ========================================================

    print(
        "🧠 Iniciando análisis de IA "
        "del documento completo..."
    )

    ai_report = await analyze_ai_document(
        text
    )

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    return {
        "plagiarism_percentage": round(
            min(
                100.0,
                coverage,
            ),
            2,
        ),

        "details": details,

        "ai_analysis": ai_report,

        "analysis_meta": {
            "chunks_analyzed": len(
                fragments
            ),

            "chunks_with_strong_evidence": (
                flagged_fragments
            ),

            "metric": (
                "cosine distance on "
                "normalized embeddings"
            ),

            "model": (
                "paraphrase-multilingual-"
                "mpnet-base-v2"
            ),

            "interpretation": (
                "evidence coverage, not "
                "probability of plagiarism"
            ),

            "ai_analysis_scope": (
                "full_document"
            ),

            "ai_chunking": (
                "academic_structure"
            ),

            "ai_target_chunk_chars": (
                AI_TARGET_CHARS
            ),

            "ai_max_chunk_chars": (
                AI_MAX_CHARS
            ),
        },
    }