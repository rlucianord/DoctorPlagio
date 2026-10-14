import sys
from pathlib import Path
APP_DIR = Path(__file__).resolve().parents[1]

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from backend.api_keys import ensure_development_api_key


if __name__ == "__main__":
    key = ensure_development_api_key()

    if key:
        print("\nPrimera clave de desarrollo creada correctamente.")
    else:
        print("\nNo se creó otra clave; ya existe una activa.")
