
import hashlib
import hmac
import os

from sqlalchemy import text
from flask import request, jsonify

from .database import engine


def validate_api_key():
    """
    Valida la API Key de servicio contra public.api_keys.
    Devuelve None si es válida; una respuesta HTTP si no lo es.
    """
    supplied_key = request.headers.get("X-API-Key", "").strip()

    if not supplied_key or "." not in supplied_key:
        return jsonify({
            "error": "API Key ausente o inválida"
        }), 401

    prefix = supplied_key.split(".", 1)[0]

    if not prefix or len(supplied_key) > 256:
        return jsonify({
            "error": "API Key inválida"
        }), 401

    key_hash = hashlib.sha256(
        supplied_key.encode("utf-8")
    ).hexdigest()

    environment = os.getenv(
        "APP_ENV", "development"
    ).lower()

    try:
        with engine.begin() as conn:
            record = conn.execute(
                text("""
                    SELECT id, key_hash
                    FROM public.api_keys
                    WHERE key_prefix = :prefix
                      AND environment = :environment
                      AND is_active = TRUE
                      AND revoked_at IS NULL
                      AND (
                          expires_at IS NULL
                          OR expires_at > NOW()
                      )
                    LIMIT 1
                """),
                {
                    "prefix": prefix,
                    "environment": environment,
                },
            ).first()

            if record is None:
                return jsonify({
                    "error": "API Key no autorizada"
                }), 401

            if not hmac.compare_digest(
                record.key_hash.strip(),
                key_hash,
            ):
                return jsonify({
                    "error": "API Key no autorizada"
                }), 401

            conn.execute(
                text("""
                    UPDATE public.api_keys
                    SET last_used_at = NOW()
                    WHERE id = :id
                """),
                {"id": record.id},
            )

        return None

    except Exception:
        # No revelar detalles de PostgreSQL al cliente.
        print("Error interno al validar la API Key.")
        return jsonify({
            "error": "No fue posible validar las credenciales"
        }), 503
