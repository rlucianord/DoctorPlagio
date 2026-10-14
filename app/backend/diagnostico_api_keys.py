
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from sqlalchemy import text
from backend.database import engine


def diagnosticar():
    print("=" * 60)
    print("DIAGNÓSTICO DE API KEYS Y POSTGRESQL")
    print("=" * 60)

    try:
        with engine.connect() as conn:
            database = conn.execute(
                text("SELECT current_database()")
            ).scalar_one()

            table = conn.execute(
                text("SELECT to_regclass('public.api_keys')")
            ).scalar_one()

            print("Base de datos:", database)
            print("Tabla public.api_keys:", table)

            if table is None:
                print("ERROR: la tabla no existe en esta base.")
                return

            count = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM public.api_keys
                    WHERE environment = 'development'
                      AND is_active = TRUE
                      AND revoked_at IS NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                """)
            ).scalar_one()

            print("Claves de desarrollo activas:", count)

            print("\nConexión y tabla verificadas correctamente.")

    except Exception as exc:
        print("ERROR:", type(exc).__name__)
        print(exc)


if __name__ == "__main__":
    diagnosticar()
