import httpx

def test_ollama():
    try:
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3", "prompt": "Responde: OK", "stream": False}
        )
        print("Conexión con Ollama:", "✅ EXITOSA" if response.status_code == 200 else "❌ FALLIDA")
    except Exception as e:
        print(f"❌ Error de red: {e}")

test_ollama()