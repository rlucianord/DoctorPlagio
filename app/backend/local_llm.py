"""
Motor LLM local para DoctorPlagio.

Actualmente soporta modelos GGUF mediante llama.cpp.

Modelo principal:
    unsloth/gpt-oss-20b-GGUF
    gpt-oss-20b-Q2_K_L.gguf

El modelo se descarga automáticamente desde Hugging Face
si no existe localmente.

El modelo Qwen2.5-3B existente se conserva y puede utilizarse
estableciendo la variable de entorno LOCAL_LLM_MODEL.
"""

from __future__ import annotations

import gc
import json
import os
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download
from llama_cpp import Llama


# ============================================================
# PROYECTO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ============================================================
# MODELO GPT-OSS
# ============================================================

HF_REPO_ID = "unsloth/gpt-oss-20b-GGUF"

MODEL_FILENAME = "gpt-oss-20b-Q2_K_L.gguf"

MODEL_DIR = (
    PROJECT_ROOT
    / "models"
    / "gpt-oss-20b-GGUF"
)

DEFAULT_MODEL_PATH = (
    MODEL_DIR
    / MODEL_FILENAME
)


# ============================================================
# MODELO CONFIGURABLE
# ============================================================

MODEL_PATH = Path(
    os.environ.get(
        "LOCAL_LLM_MODEL",
        str(DEFAULT_MODEL_PATH),
    )
)


# ============================================================
# CONFIGURACIÓN LLAMA.CPP
# ============================================================

N_CTX = int(
    os.environ.get(
        "LOCAL_LLM_CONTEXT",
        "8192",
    )
)

N_THREADS_ENV = os.environ.get(
    "LOCAL_LLM_THREADS"
)

N_THREADS = (
    int(N_THREADS_ENV)
    if N_THREADS_ENV
    else None
)

N_GPU_LAYERS = int(
    os.environ.get(
        "LOCAL_LLM_GPU_LAYERS",
        "0",
    )
)

N_BATCH = int(
    os.environ.get(
        "LOCAL_LLM_BATCH",
        "512",
    )
)

DEFAULT_SEED = int(
    os.environ.get(
        "LOCAL_LLM_SEED",
        "42",
    )
)


# ============================================================
# INSTANCIA GLOBAL
# ============================================================

_llm: Llama | None = None


# ============================================================
# RUTA DEL MODELO
# ============================================================

def get_model_path() -> Path:
    """
    Devuelve la ruta configurada para el modelo.
    """
    return MODEL_PATH


# ============================================================
# EXISTENCIA DEL MODELO
# ============================================================

def model_exists() -> bool:
    """
    Indica si el archivo GGUF existe localmente.
    """
    return MODEL_PATH.exists()


# ============================================================
# DESCARGA AUTOMÁTICA
# ============================================================

def ensure_model_exists() -> Path:
    """
    Comprueba si el modelo GGUF existe.

    Si existe:
        devuelve la ruta inmediatamente.

    Si no existe:
        descarga el modelo desde Hugging Face.

    El modelo solamente se descarga una vez.
    """

    if MODEL_PATH.exists():

        print("✅ Modelo local encontrado:")
        print(f"   {MODEL_PATH}")

        return MODEL_PATH

    print()
    print("=" * 70)
    print("⬇️ MODELO LOCAL NO ENCONTRADO")
    print("=" * 70)
    print(f"📦 Repositorio: {HF_REPO_ID}")
    print(f"📄 Archivo: {MODEL_FILENAME}")
    print(f"📁 Destino: {MODEL_DIR}")
    print()
    print("⚠️ El archivo ocupa varios GB.")
    print(
        "⚠️ La descarga puede tardar dependiendo "
        "de la velocidad de Internet."
    )
    print("=" * 70)
    print()

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        downloaded_path = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=MODEL_FILENAME,
            local_dir=str(MODEL_DIR),
        )

    except Exception as exc:

        print()
        print("❌ ERROR DESCARGANDO EL MODELO")
        print(f"❌ {exc}")
        print()

        raise RuntimeError(
            "No fue posible descargar el modelo "
            "desde Hugging Face."
        ) from exc

    downloaded_path = Path(
        downloaded_path
    )

    print()
    print("✅ MODELO DESCARGADO")
    print(f"📁 {downloaded_path}")
    print()

    return downloaded_path


# ============================================================
# INFORMACIÓN DEL MODELO
# ============================================================

def get_model_info() -> dict[str, Any]:
    """
    Devuelve información del modelo configurado.
    """

    return {
        "engine": "llama.cpp",
        "library": "llama-cpp-python",
        "model": MODEL_PATH.name,
        "model_path": str(MODEL_PATH),
        "model_exists": MODEL_PATH.exists(),
        "huggingface_repo": HF_REPO_ID,
        "context": N_CTX,
        "threads": N_THREADS,
        "gpu_layers": N_GPU_LAYERS,
        "batch": N_BATCH,
        "seed": DEFAULT_SEED,
    }


# ============================================================
# CARGAR MODELO
# ============================================================

def get_model() -> Llama:
    """
    Carga el modelo GGUF una sola vez.

    Si el modelo no existe, lo descarga automáticamente.
    """

    global _llm

    if _llm is not None:
        return _llm

    model_path = ensure_model_exists()

    print()
    print("🧠 Cargando modelo local mediante llama.cpp...")
    print(f"🧠 Modelo: {model_path.name}")
    print(f"🧠 Ruta: {model_path}")
    print(f"🧠 Contexto: {N_CTX}")
    print(f"🧠 GPU layers: {N_GPU_LAYERS}")
    print(f"🧠 Batch: {N_BATCH}")

    if N_THREADS is not None:
        print(f"🧠 Threads: {N_THREADS}")

    _llm = Llama(
        model_path=str(model_path),
        n_ctx=N_CTX,
        n_threads=N_THREADS,
        n_gpu_layers=N_GPU_LAYERS,
        n_batch=N_BATCH,
        seed=DEFAULT_SEED,
        verbose=False,
    )

    print("✅ Modelo local cargado correctamente.")

    return _llm


# ============================================================
# GENERACIÓN
# ============================================================

def generate(
    prompt: str,
    max_tokens: int = 800,
    temperature: float = 0.0,
    seed: int | None = None,
) -> str:
    """
    Genera texto utilizando el modelo local.
    """

    llm = get_model()

    effective_seed = (
        DEFAULT_SEED
        if seed is None
        else seed
    )
    
    response = llm.create_chat_completion(
    messages=[
        {
            "role": "user",
            "content": prompt,
        }
    ],
    response_format={
        "type": "json_object",
        "schema": {
            "type": "object",
            "properties": {
                "ai_score": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "label": {
                    "type": "string",
                },
                "reasoning": {
                    "type": "string",
                    "maxLength": 500,
                },
            },
            "required": [
                "ai_score",
                "label",
                "reasoning",
            ],
        },
    },
    max_tokens=2000,
    temperature=0.0,
    seed=42,
    )

    try:

        content = response[
            "choices"
        ][0][
            "message"
        ][
            "content"
        ]

    except (
        KeyError,
        IndexError,
        TypeError,
    ) as exc:

        raise RuntimeError(
            "El modelo local devolvió una "
            "respuesta inesperada."
        ) from exc

    return str(content).strip()


# ============================================================
# EXTRAER PRIMER JSON
# ============================================================

def _clean_json_response(
    response: str,
) -> str:
    """
    Extrae el primer objeto JSON completo.

    GPT-OSS puede devolver marcadores especiales
    de sus canales de razonamiento, por ejemplo:

        <|channel|>analysis
        <|message|>
        ...
        <|end|>
        <|start|>assistant
        <|channel|>final
        <|message|>
        {"ai_score": 0.0, ...}

    Esta función elimina esos marcadores y
    devuelve únicamente el primer objeto JSON completo.
    """

    if not response:
        return ""

    response = str(response).strip()

    response = response.replace(
        "\r\n",
        "\n",
    )

    # --------------------------------------------------------
    # GPT-OSS: preferir el canal FINAL
    # --------------------------------------------------------

    final_marker = "<|channel|>final"

    final_position = response.rfind(
        final_marker
    )

    if final_position >= 0:

        response = response[
            final_position
            + len(final_marker):
        ]

    # --------------------------------------------------------
    # Eliminar tokens especiales
    # --------------------------------------------------------

    special_tokens = (
        "<|start|>",
        "<|end|>",
        "<|channel|>",
        "<|message|>",
        "<|analysis|>",
        "<|final|>",
    )

    for token in special_tokens:

        response = response.replace(
            token,
            "",
        )

    response = response.strip()

    # --------------------------------------------------------
    # Eliminar Markdown
    # --------------------------------------------------------

    response = response.replace(
        "```json",
        "",
    )

    response = response.replace(
        "```JSON",
        "",
    )

    response = response.replace(
        "```",
        "",
    )

    response = response.strip()

    # --------------------------------------------------------
    # Buscar el primer {
    # --------------------------------------------------------

    start = response.find("{")

    if start == -1:
        return ""

    # --------------------------------------------------------
    # Buscar el cierre correspondiente
    # respetando strings JSON
    # --------------------------------------------------------

    depth = 0
    in_string = False
    escape = False

    for i in range(
        start,
        len(response),
    ):

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

                return response[
                    start:i + 1
                ].strip()

    # JSON incompleto o truncado.
    return ""


# ============================================================
# GENERACIÓN JSON
# ============================================================

def generate_json(
    prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.0,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Genera una respuesta JSON.

    GPT-OSS puede utilizar parte de los tokens
    de salida en su razonamiento antes de producir
    la respuesta final.

    Por eso usamos 400 tokens por defecto en lugar
    de los 150 anteriores.
    """

    json_prompt = f"""
Responde exclusivamente con UN objeto JSON válido.

REGLAS OBLIGATORIAS:

- No escribas explicaciones antes del JSON.
- No escribas explicaciones después del JSON.
- No escribas análisis previo.
- No escribas Markdown.
- No uses bloques de código.
- No repitas el objeto JSON.
- El objeto debe comenzar con {{ y terminar con }}.
- Usa exactamente las claves solicitadas por la tarea.
- Todos los valores deben ser JSON válido.
- Después de la última }} termina la respuesta.

TAREA:

{prompt}
"""

    response = generate(
        json_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=seed,
    )

    cleaned = _clean_json_response(
        response
    )

    if not cleaned:

        return {
            "error": "invalid_json",
            "raw_response": response,
        }

    try:

        data = json.loads(
            cleaned
        )

    except json.JSONDecodeError:

        return {
            "error": "invalid_json",
            "raw_response": response,
            "cleaned_response": cleaned,
        }

    if not isinstance(
        data,
        dict,
    ):

        return {
            "error": "invalid_json_object",
            "raw_response": response,
            "cleaned_response": cleaned,
        }

    return data


# ============================================================
# PRUEBA GENERAL DEL MODELO
# ============================================================

def test_model() -> str:
    """
    Prueba básica de generación.
    """

    prompt = """
Responde en español.

Explica brevemente qué es una tesis universitaria.

No utilices más de tres oraciones.
"""

    return generate(
        prompt,
        max_tokens=300,
        temperature=0.0,
        seed=42,
    )


# ============================================================
# PRUEBA JSON
# ============================================================

def test_json() -> dict[str, Any]:
    """
    Prueba que el modelo pueda producir JSON válido.
    """

    prompt = """
Analiza esta oración:

"La investigación analiza los resultados obtenidos."

Devuelve exactamente este formato:

{
    "ai_score": 0.0,
    "label": "bajo",
    "reasoning": "explicación breve"
}

El ai_score debe estar entre 0.0 y 1.0.
"""

    return generate_json(
        prompt,
        max_tokens=2000,
        temperature=0.0,
        seed=42,
    )


# ============================================================
# DESCARGA MANUAL
# ============================================================

def download_model() -> Path:
    """
    Fuerza la comprobación/descarga del modelo.

    Útil para descargarlo antes de ejecutar DoctorPlagio.
    """

    return ensure_model_exists()


# ============================================================
# DESCARGA + CARGA
# ============================================================

def load_model() -> Llama:
    """
    Alias explícito para descargar y cargar el modelo.
    """

    return get_model()


# ============================================================
# DESCARGAR MODELO DESDE TERMINAL
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("🧠 DOCTORPLAGIO - LOCAL LLM")
    print("=" * 70)
    print()

    print("Configuración:")
    print()

    info = get_model_info()

    for key, value in info.items():

        print(
            f"{key}: {value}"
        )

    print()

    print(
        "Comprobando modelo..."
    )

    path = ensure_model_exists()

    print()
    print(
        "✅ Modelo disponible en:"
    )
    print(path)
    print()