from flask import Flask, request, render_template, session, jsonify
import models
from  models.model  import get_response

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