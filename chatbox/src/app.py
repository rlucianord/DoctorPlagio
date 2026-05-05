from flask import Flask, request, render_template, session, jsonify
import sys
import os
from pathlib import Path

# --- PROTOCOLO DE RUTAS DOCTORPLAGIO ---
# 1. Obtenemos la ruta de la carpeta donde vive este script (src)
current_dir = Path(__file__).resolve().parent

# 2. Obtenemos la raíz del proyecto (un nivel arriba de src)
project_root = current_dir.parent

# 3. Añadimos la raíz al sys.path para que Python vea /models y /app
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ahora tus imports ya no fallarán
try:
    ffrom  models.model  import get_response # Ajusta el nombre exacto de tu archivo
    print("✅ Módulos de 'models' vinculados correctamente.")
except ImportError as e:
    print(f"❌ Error crítico de importación: {e}")


app = Flask(__name__)
app.secret_key = "tu_clave_secreta_aqui_123!"

@app.route("/", methods=["GET", "POST"])
def chat():
    if "chat_history" not in session:
        session["chat_history"] = []

    if request.method == "POST":
        user_input = request.form.get("user_input", "").strip()

        if user_input:
            try:
                response = get_response(user_input)
                bot_response = response["choices"][0]["message"]["content"]

                session["chat_history"].extend([
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": bot_response}
                ])
                session.modified = True

                return jsonify({"bot_response": bot_response})  # Return JSON
            except Exception as e:
                session["chat_history"].append({
                    "role": "system",
                    "content": f"Error: {str(e)}"
                })
                return jsonify({"error": str(e)}), 500  # Return JSON error

    return render_template("index.html", chat_history=session["chat_history"])


if __name__ == "__main__":
    app.run(debug=True, port=5001)