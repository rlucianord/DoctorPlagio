# chatbox/src/tools/plagiarism_tool.py
from agency_swarm.tools import BaseTool
from pydantic import Field
from app.backend.plagiarism import analyze_plagiarism
import asyncio
import sys
import os
from pathlib import Path

# --- AJUSTE DE RUTAS SENIOR ---
# Obtenemos la ruta de /chatbox (un nivel arriba de /src)
chatbox_path = Path(__file__).resolve().parent.parent
sys.path.append(str(chatbox_path))

# También añadimos la raíz del proyecto por si necesitas /app
root_path = chatbox_path.parent
sys.path.append(str(root_path))


class PlagiarismCheckerTool(BaseTool):
    """Herramienta para detectar plagio y uso de IA en un texto."""
    text: str = Field(..., description="El contenido del documento a analizar.")

    def run(self):
        # Como tu función es async y Agency Swarm es sync, usamos el loop
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(analyze_plagiarism(self.text, None))
        return str(result)