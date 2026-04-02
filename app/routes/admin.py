from flask import Blueprint, render_template, session, redirect, url_for
from app.db import fetch_all, fetch_one

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required():
    def wrapper(func):
        def inner(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login"))

            if session.get("rol") != "admin":
                return redirect(url_for("public.home"))

            return func(*args, **kwargs)
        inner.__name__ = func.__name__
        return inner
    return wrapper


@admin_bp.route("/")
@admin_required()
def dashboard():

    stats = fetch_one("""
        SELECT
            COUNT(DISTINCT c.id) FILTER (WHERE c.fecha = CURRENT_DATE) AS citas_hoy,
            COUNT(DISTINCT c.id) FILTER (WHERE c.estado = 'pendiente') AS pendientes,
            COUNT(DISTINCT c.id) FILTER (WHERE c.estado = 'confirmada') AS confirmadas,
            COALESCE(SUM(s.precio) FILTER (
                WHERE c.estado = 'completada' AND c.fecha = CURRENT_DATE
            ), 0) AS ingresos_hoy
        FROM citas c
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
    """)

    citas = fetch_all("""
        SELECT
            c.id,
            c.fecha,
            c.hora_inicio,
            c.estado,
            u.nombre AS cliente_nombre,
            COALESCE(STRING_AGG(s.nombre, ', '), '') AS servicios
        FROM citas c
        JOIN usuarios u ON u.id = c.cliente_id
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
        GROUP BY c.id, u.nombre
        ORDER BY c.fecha ASC, c.hora_inicio ASC
        LIMIT 10
    """)

    return render_template("dashboard.html", stats=stats, citas=citas)