import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:123456789$@localhost:5432/drplagium"
)
SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key") # ¡Asegúrate de cambiar esto en producción!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "sk_test_...") # Tu clave secreta de Stripe
# Otras configuraciones para Ollama si es necesario
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mixtral")