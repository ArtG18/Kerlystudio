from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import os

from app.db import fetch_all, fetch_one, execute_query
from app.services.citas_service import obtener_servicios_activos, crear_cita

reservas_bp = Blueprint("reservas", __name__)

# =========================
# RESERVAR
# =========================
@reservas_bp.route("/reservar", methods=["GET", "POST"])
def reservar():

    # 🔥 BLOQUEAR ADMIN
    if session.get("rol") == "admin":
        flash("Acceso no permitido para administradores", "warning")
        return redirect(url_for("public.home"))

    servicios = obtener_servicios_activos()

    manicuristas = fetch_all("""
        SELECT id, nombre
        FROM manicuristas
        WHERE activo = TRUE
        ORDER BY nombre
    """)

    # =========================
    # POST
    # =========================
    if request.method == "POST":

        nombre = request.form.get("nombre", "").strip()
        email = request.form.get("email", "").strip().lower()
        telefono = request.form.get("telefono", "").strip()

        service_ids = request.form.getlist("servicios")
        manicurista_id = request.form.get("manicurista_id", type=int)
        fecha_raw = request.form.get("fecha")
        hora_inicio_raw = request.form.get("hora_inicio")

        # VALIDACIONES
        if not all([nombre, email, telefono]):
            flash("Completa todos los datos", "danger")
            return render_template("reservar.html", servicios=servicios, manicuristas=manicuristas)

        if not service_ids or not manicurista_id or not fecha_raw or not hora_inicio_raw:
            flash("Debes completar servicio, fecha y hora", "danger")
            return render_template("reservar.html", servicios=servicios, manicuristas=manicuristas)

        try:
            fecha = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
            hora_inicio = datetime.strptime(hora_inicio_raw, "%H:%M").time()
        except:
            flash("Datos inválidos", "danger")
            return render_template("reservar.html", servicios=servicios, manicuristas=manicuristas)

        # 🔥 SERVICIOS
        servicios_seleccionados = fetch_all("""
            SELECT id, duracion_min
            FROM servicios
            WHERE id = ANY(%s)
        """, (service_ids,))

        total_duracion = sum(s["duracion_min"] for s in servicios_seleccionados)

        hora_fin_dt = datetime.combine(fecha, hora_inicio) + timedelta(minutes=total_duracion)
        hora_fin = hora_fin_dt.time()

        # 🔥 VERIFICAR DISPONIBILIDAD
        ocupado = fetch_one("""
            SELECT 1
            FROM citas
            WHERE manicurista_id = %s
            AND fecha = %s
            AND NOT (
                hora_fin <= %s OR hora_inicio >= %s
            )
            LIMIT 1
        """, (manicurista_id, fecha, hora_inicio, hora_fin))

        if ocupado:
            flash("Horario no disponible", "warning")
            return render_template("reservar.html", servicios=servicios, manicuristas=manicuristas)

        # 🔥 CREAR CLIENTE SI NO EXISTE
        cliente = fetch_one("SELECT id FROM usuarios WHERE email=%s", (email,))

        if not cliente:
            cliente = execute_query("""
                INSERT INTO usuarios (nombre, email, telefono, password_hash, rol, activo)
                VALUES (%s, %s, %s, %s, 'cliente', TRUE)
                RETURNING id
            """, (
                nombre,
                email,
                telefono,
                generate_password_hash(os.urandom(16).hex())
            ), fetchone=True)

        # 🔥 CREAR CITA
        cita = crear_cita(
            cliente["id"],
            manicurista_id,
            fecha,
            hora_inicio,
            hora_fin,
            ""
        )

        # 🔥 RELACIÓN SERVICIOS
        for sid in service_ids:
            execute_query("""
                INSERT INTO cita_servicios (cita_id, servicio_id)
                VALUES (%s, %s)
            """, (cita["id"], sid))

        flash("✨ Cita agendada correctamente", "success")
        return redirect(url_for("public.home"))

    # =========================
    # GET
    # =========================
    return render_template(
        "reservar.html",
        servicios=servicios,
        manicuristas=manicuristas
    )


# =========================
# HORAS DISPONIBLES (AJAX)
# =========================
@reservas_bp.route("/horas-disponibles")
def horas_disponibles():

    manicurista_id = request.args.get("manicurista_id", type=int)
    fecha_raw = request.args.get("fecha")

    if not manicurista_id or not fecha_raw:
        return {"ocupadas": []}

    fecha = datetime.strptime(fecha_raw, "%Y-%m-%d").date()

    citas = fetch_all("""
        SELECT hora_inicio, hora_fin
        FROM citas
        WHERE manicurista_id = %s
        AND fecha = %s
        AND estado NOT IN ('cancelada_admin', 'completada')
    """, (manicurista_id, fecha))

    ocupadas = []

    for c in citas:
        hora = c["hora_inicio"]
        while hora < c["hora_fin"]:
            ocupadas.append(hora.strftime("%H:%M"))
            hora = (datetime.combine(fecha, hora) + timedelta(minutes=30)).time()

    return {"ocupadas": ocupadas}