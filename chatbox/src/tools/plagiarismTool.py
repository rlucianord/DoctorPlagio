# chatbox/src/tools/plagiarism_tool.py
import sys
import os
from pathlib import Path

# --- AJUSTE DE RUTAS SENIOR (PRIMERO) ---
# Necesitamos subir 3 niveles para llegar a la raíz (tools -> src -> chatbox -> raíz)
# O usar una ruta absoluta basada en tu entorno de Ubuntu
path_herramienta = Path(__file__).resolve()
raiz_proyecto = path_herramienta.parents[3] # Sube hasta DoctorPlagio/

if str(raiz_proyecto) not in sys.path:
    sys.path.insert(0, str(raiz_proyecto))

# --- AHORA SÍ LOS IMPORTS ---
from agency_swarm.tools import BaseTool
from pydantic import Field
# Esto ahora funcionará porque la raíz está en el path
from app.backend.plagiarism import analyze_plagiarism 
import asyncio

class PlagiarismCheckerTool(BaseTool):
    """Herramienta para detectar plagio y uso de IA en un texto."""
    text: str = Field(..., description="El contenido del documento a analizar.")

    def run(self):
        try:
            # Manejo del loop para entornos async/sync combinados
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            result = loop.run_until_complete(analyze_plagiarism(self.text, None))
            return str(result)
        except Exception as e:
            return f"Error en la herramienta de plagio: {str(e)}"