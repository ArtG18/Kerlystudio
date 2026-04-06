from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from app.db import fetch_one

auth_bp = Blueprint("auth", __name__)

# =========================
# LOGIN UNIFICADO
# =========================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Buscamos al usuario (sea admin o cliente) que esté activo
        user = fetch_one(
            "SELECT * FROM usuarios WHERE email = %s AND activo = TRUE",
            (email,)
        )

        # Validación de credenciales
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Correo o contraseña incorrectos. Por favor, intenta de nuevo.", "danger")
            return render_template("login.html")

        # Guardamos la sesión
        session.clear() # Limpiamos rastro de sesiones anteriores por seguridad
        session["user_id"] = user["id"]
        session["rol"] = user["rol"]
        session["nombre"] = user["nombre"]

        # Redirección inteligente según el ROL
        if user["rol"] == "admin":
            flash(f"Panel de Control: Bienvenida, {user['nombre']} 🛠️", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            # Saludo personalizado para clientas
            primer_nombre = user["nombre"].split(' ')[0]
            flash(f"¡Qué alegría verte de nuevo, {primer_nombre}! ✨", "success")
            return redirect(url_for("public.home"))

    return render_template("login.html")


# =========================
# LOGOUT
# =========================
@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente. ¡Vuelve pronto!", "success")
    return redirect(url_for("public.home"))


# =========================
# REGISTRO DE CLIENTES
# =========================
# Si tienes una ruta de registro, asegúrate de que use generate_password_hash
# y que asigne por defecto el rol 'cliente'.