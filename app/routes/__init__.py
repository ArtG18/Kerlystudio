from flask import Flask, session
import os

from app.routes.public import public_bp
from app.routes.auth import auth_bp
from app.db import fetch_one
from app.routes.reservas import reservas_bp
from app.routes.citas import citas_bp
from app.routes.admin import admin_bp

def create_app():
    app = Flask(__name__)

    # CONFIG
    app.secret_key = os.getenv("SECRET_KEY", "dev-key")

    # BLUEPRINTS
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(reservas_bp)
    app.register_blueprint(citas_bp)
    app.register_blueprint(admin_bp)

    # =========================
    # CONTEXT GLOBAL (USUARIO)
    # =========================
    @app.context_processor
    def inject_user():
        def current_user():
            user_id = session.get("user_id")
            if not user_id:
                return None
            return fetch_one(
                "SELECT id, nombre, email, telefono, rol FROM usuarios WHERE id = %s",
                (user_id,)
            )

        return dict(logged_user=current_user())

    # =========================
    # ERROR HANDLER
    # =========================
    @app.errorhandler(500)
    def error_500(e):
        return "Error interno del servidor", 500

    return app