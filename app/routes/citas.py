from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from datetime import datetime

from app.db import fetch_all, fetch_one, execute_query

citas_bp = Blueprint("citas", __name__)

# =========================
# DECORADOR LOGIN SIMPLE
# =========================
def login_required():
    def wrapper(func):
        def inner(*args, **kwargs):
            if not session.get("user_id"):
                flash("Debes iniciar sesión", "warning")
                return redirect(url_for("auth.login"))
            return func(*args, **kwargs)
        inner.__name__ = func.__name__
        return inner
    return wrapper


# =========================
# MIS CITAS
# =========================
@citas_bp.route("/mis-citas")
@login_required()
def mis_citas():

    if session.get("rol") != "cliente":
        return redirect(url_for("public.home"))

    citas = fetch_all("""
        SELECT
            c.id,
            c.fecha,
            c.hora_inicio,
            c.hora_fin,
            c.estado,
            m.nombre AS manicurista_nombre,
            COALESCE(STRING_AGG(s.nombre, ', '), '') AS servicios
        FROM citas c
        JOIN manicuristas m ON m.id = c.manicurista_id
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
        WHERE c.cliente_id = %s
        GROUP BY c.id, m.nombre
        ORDER BY c.fecha DESC, c.hora_inicio DESC
    """, (session["user_id"],))

    return render_template("mis_citas.html", citas=citas)


# =========================
# CANCELAR CITA
# =========================
@citas_bp.route("/cancelar-cita/<int:cita_id>", methods=["POST"])
@login_required()
def cancelar_cita(cita_id):

    cita = fetch_one("""
        SELECT id, cliente_id, estado
        FROM citas
        WHERE id = %s
    """, (cita_id,))

    if not cita:
        flash("Cita no encontrada", "danger")
        return redirect(url_for("citas.mis_citas"))

    if cita["cliente_id"] != session.get("user_id"):
        flash("No tienes permiso", "danger")
        return redirect(url_for("citas.mis_citas"))

    if cita["estado"] not in ["pendiente", "confirmada"]:
        flash("No se puede cancelar esta cita", "warning")
        return redirect(url_for("citas.mis_citas"))

    execute_query("""
        UPDATE citas
        SET estado = 'cancelada_cliente'
        WHERE id = %s
    """, (cita_id,))

    flash("Cita cancelada correctamente", "success")
    return redirect(url_for("citas.mis_citas"))


# =========================
# REAGENDAR
# =========================
@citas_bp.route("/reagendar/<int:cita_id>")
@login_required()
def reagendar(cita_id):

    cita = fetch_one("""
        SELECT *
        FROM citas
        WHERE id = %s
    """, (cita_id,))

    if not cita:
        return redirect(url_for("citas.mis_citas"))

    if cita["cliente_id"] != session.get("user_id"):
        return redirect(url_for("citas.mis_citas"))

    servicios = fetch_all("""
        SELECT servicio_id
        FROM cita_servicios
        WHERE cita_id = %s
    """, (cita_id,))

    servicios_ids = [str(s["servicio_id"]) for s in servicios]

    return redirect(
        url_for(
            "reservas.reservar",
            servicios=",".join(servicios_ids),
            manicurista_id=cita["manicurista_id"],
            fecha=cita["fecha"].strftime("%Y-%m-%d")
        )
    )