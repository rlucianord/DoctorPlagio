
import hashlib
import secrets

from sqlalchemy import text
from .database import engine
def hash_api_key(api_key: str) -> str:
    """Almacena solo el hash de la clave."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def ensure_development_api_key() -> str | None:
    """
    Crea una clave de desarrollo si no existe una activa.
    Devuelve la clave solo cuando acaba de crearla.
    """
    with engine.begin() as conn:
        # Evita que dos procesos creen claves simultáneamente.
        conn.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": 814720261},
        )

        existing = conn.execute(
            text("""
                SELECT id
                FROM public.api_keys
                WHERE environment = 'development'
                  AND is_active = TRUE
                  AND revoked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                LIMIT 1
            """)
        ).first()

        if existing:
            print("Ya existe una API Key de desarrollo activa.")
            return None

        prefix = "dp_dev_" + secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        api_key = f"{prefix}.{secret}"

        conn.execute(
            text("""
                INSERT INTO public.api_keys (
                    name,
                    key_prefix,
                    key_hash,
                    environment,
                    scopes,
                    is_active
                )
                VALUES (
                    :name,
                    :prefix,
                    :key_hash,
                    'development',
                    CAST('["analyze", "report"]' AS jsonb),
                    TRUE
                )
            """),
            {
                "name": "DoctorPlagio Development",
                "prefix": prefix,
                "key_hash": hash_api_key(api_key),
            },
        )

    # Solo se muestra cuando acaba de crearse.
    # No compartas esta salida ni la guardes en logs permanentes.
    print("\nAPI KEY CREADA. Guárdala en un lugar seguro:")
    print(api_key)
    print("El secreto no puede recuperarse desde PostgreSQL.")

    return api_key
