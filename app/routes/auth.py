from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from app.db import fetch_one

auth_bp = Blueprint("auth", __name__)

# =========================
# LOGIN CLIENTE
# =========================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = fetch_one(
            "SELECT * FROM usuarios WHERE email = %s AND activo = TRUE",
            (email,)
        )

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Credenciales inválidas", "danger")
            return render_template("login.html")

        if user["rol"] != "cliente":
            flash("Este acceso es solo para clientas", "danger")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["rol"] = user["rol"]
        session["nombre"] = user["nombre"]

        flash(f"Bienvenida, {user['nombre']}", "success")
        return redirect(url_for("public.home"))

    return render_template("login.html")


# =========================
# LOGOUT
# =========================
@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente", "info")
    return redirect(url_for("public.home"))