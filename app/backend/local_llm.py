"""
Motor LLM local de DoctorPlagio.

Ejecuta modelos GGUF directamente mediante llama.cpp.

No depende de Ollama ni de una API externa.
"""

from __future__ import annotations

import gc
import json
import os
from pathlib import Path
from typing import Any

from llama_cpp import Llama


# ============================================================
# CONFIGURACIÓN
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Modelo principal actual: Qwen2.5
DEFAULT_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "Qwen2.5-3B-Instruct-Q4_K_M.gguf"
)

# Permite cambiar el modelo desde una variable de entorno
# sin modificar nuevamente este archivo.
MODEL_PATH = Path(
    os.environ.get(
        "LOCAL_LLM_MODEL",
        str(DEFAULT_MODEL_PATH),
    )
)


# ============================================================
# CONTEXTO DEL MODELO
# ============================================================

N_CTX = int(
    os.environ.get(
        "LOCAL_LLM_CONTEXT",
        "8192",
    )
)


# ============================================================
# HILOS CPU
# ============================================================

N_THREADS_ENV = os.environ.get(
    "LOCAL_LLM_THREADS"
)

N_THREADS = (
    int(N_THREADS_ENV)
    if N_THREADS_ENV
    else None
)


# ============================================================
# GPU
# ============================================================

# 0 = CPU.
#
# Si posteriormente comprobamos que tu GPU es compatible,
# podemos aumentar este valor.

N_GPU_LAYERS = int(
    os.environ.get(
        "LOCAL_LLM_GPU_LAYERS",
        "0",
    )
)


# ============================================================
# BATCH
# ============================================================

N_BATCH = int(
    os.environ.get(
        "LOCAL_LLM_BATCH",
        "512",
    )
)


# ============================================================
# SEMILLA
# ============================================================

DEFAULT_SEED = int(
    os.environ.get(
        "LOCAL_LLM_SEED",
        "42",
    )
)


# ============================================================
# ESTADO DEL MODELO
# ============================================================

_llm: Llama | None = None


# ============================================================
# INFORMACIÓN
# ============================================================

def get_model_path() -> Path:
    """
    Devuelve la ruta configurada para el modelo.
    """
    return MODEL_PATH


def model_exists() -> bool:
    """
    Comprueba si el archivo GGUF existe.
    """
    return MODEL_PATH.is_file()


def get_model_info() -> dict[str, Any]:
    """
    Devuelve información básica del modelo local.
    """
    return {
        "engine": "llama.cpp",
        "library": "llama-cpp-python",
        "model": MODEL_PATH.name,
        "model_path": str(MODEL_PATH),
        "model_exists": model_exists(),
        "context": N_CTX,
        "threads": N_THREADS,
        "gpu_layers": N_GPU_LAYERS,
        "batch": N_BATCH,
        "seed": DEFAULT_SEED,
    }


# ============================================================
# CARGA DEL MODELO
# ============================================================

def get_model() -> Llama:
    """
    Carga el modelo LLM una sola vez y lo mantiene en memoria.

    No queremos cargar el GGUF nuevamente para cada bloque.
    """

    global _llm

    if _llm is not None:
        return _llm

    if not model_exists():
        raise FileNotFoundError(
            "No se encontró el modelo GGUF de DoctorPlagio:\n"
            f"{MODEL_PATH}"
        )

    print(
        "🧠 Cargando modelo local mediante llama.cpp..."
    )

    print(
        f"🧠 Modelo: {MODEL_PATH.name}"
    )

    print(
        f"🧠 Ruta: {MODEL_PATH}"
    )

    print(
        f"🧠 Contexto: {N_CTX}"
    )

    print(
        f"🧠 GPU layers: {N_GPU_LAYERS}"
    )

    print(
        f"🧠 Batch: {N_BATCH}"
    )

    _llm = Llama(
        model_path=str(MODEL_PATH),
        n_ctx=N_CTX,
        n_batch=N_BATCH,
        n_threads=N_THREADS,
        n_gpu_layers=N_GPU_LAYERS,
        seed=DEFAULT_SEED,
        verbose=False,
    )

    print(
        "✅ Modelo local cargado correctamente."
    )

    return _llm


# ============================================================
# GENERACIÓN DE TEXTO
# ============================================================

def generate(
    prompt: str,
    *,
    max_tokens: int = 300,
    temperature: float = 0.0,
    seed: int | None = None,
) -> str:
    """
    Ejecuta una generación de texto con el modelo local.

    Devuelve solamente el texto generado.
    """

    if not prompt or not prompt.strip():
        raise ValueError(
            "El prompt no puede estar vacío."
        )

    llm = get_model()

    generation_seed = (
        DEFAULT_SEED
        if seed is None
        else seed
    )

    result = llm(
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=generation_seed,
        echo=False,
    )

    choices = result.get(
        "choices",
        [],
    )

    if not choices:
        raise RuntimeError(
            "llama.cpp no devolvió ninguna respuesta."
        )

    text = choices[0].get(
        "text",
        "",
    )

    return text.strip()


# ============================================================
# LIMPIEZA DE RESPUESTAS JSON
# ============================================================
def _clean_json_response(response: str) -> str:
    """
    Extrae el primer objeto JSON válido encontrado
    en la respuesta del modelo.

    Esto protege a DoctorPlagio contra respuestas donde
    el modelo repite el mismo JSON varias veces.
    """

    response = response.strip()

    if not response:
        return ""

    # Buscar el primer objeto JSON.
    start = response.find("{")

    if start == -1:
        return ""

    # Buscar el cierre correcto del primer objeto JSON.
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(response)):

        char = response[i]

        if in_string:

            if escape:
                escape = False

            elif char == "\\":
                escape = True

            elif char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True

        elif char == "{":
            depth += 1

        elif char == "}":

            depth -= 1

            if depth == 0:
                return response[start:i + 1].strip()

    return ""
def generate_json(
    prompt: str,
    max_tokens: int = 150,
    temperature: float = 0.0,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Genera una respuesta JSON y extrae únicamente el primer
    objeto JSON válido producido por el modelo.
    """

    json_prompt = f"""
    Responde exclusivamente con un único objeto JSON válido.

    IMPORTANTE:
    - Devuelve solamente UN objeto JSON.
    - No repitas el objeto.
    - No escribas otro JSON después.
    - No uses Markdown.
    - No uses bloques de código.
    - Después del carácter }} debes terminar la respuesta.

    {prompt}
    """

    response = generate(
        json_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=seed,
    )

    cleaned = _clean_json_response(response)

    if not cleaned:
        return {
            "error": "invalid_json",
            "raw_response": response,
        }

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "error": "invalid_json",
            "raw_response": response,
        }

    if not isinstance(data, dict):
        return {
            "error": "invalid_json_object",
            "raw_response": response,
        }

    return data


# ============================================================
# PRUEBA DEL MODELO
# ============================================================

def test_model() -> dict[str, Any]:
    """
    Prueba sencilla para verificar que el modelo local funciona.
    """

    prompt = """
Responde únicamente con esta frase:

DoctorPlagio funciona localmente.
"""

    try:

        response = generate(
            prompt,
            max_tokens=20,
            temperature=0.0,
            seed=42,
        )

        return {
            "available": True,
            "engine": "llama.cpp",
            "model": MODEL_PATH.name,
            "response": response,
        }

    except Exception as exc:

        return {
            "available": False,
            "engine": "llama.cpp",
            "model": MODEL_PATH.name,
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }


# ============================================================
# PRUEBA JSON
# ============================================================

def test_json() -> dict[str, Any]:
    """
    Prueba específicamente la capacidad del modelo
    para devolver JSON válido en español.
    """

    prompt = """
Analiza brevemente este texto:

La investigación estudia los factores que influyen
en el rendimiento académico de los estudiantes.

Devuelve exactamente estas tres propiedades:

ai_score:
número entre 0.0 y 1.0

label:
una clasificación breve

reasoning:
una explicación de máximo dos oraciones.

No resumas el texto.
Explica solamente las características lingüísticas observables.
"""

    return generate_json(
        prompt,
        max_tokens=120,
        temperature=0.0,
        seed=42,
    )


# ============================================================
# LIBERAR MODELO
# ============================================================

def unload_model() -> None:
    """
    Libera explícitamente el modelo local.
    """

    global _llm

    if _llm is None:
        return

    try:
        _llm.close()
    except Exception as exc:
        print(
            f"⚠️ Error cerrando el modelo: {exc}"
        )
    finally:
        _llm = None

    gc.collect()

test_model()