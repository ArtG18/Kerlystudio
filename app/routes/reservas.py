from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
from app.db import fetch_all, fetch_one, execute_query
from app.services.citas_service import obtener_servicios_activos, crear_cita

reservas_bp = Blueprint("reservas", __name__)

# ==========================================================
# MEJORA 1: API DE HORAS DISPONIBLES (PARA AJAX)
# ==========================================================
@reservas_bp.route("/api/horas-disponibles")
def horas_disponibles():
    manicurista_id = request.args.get("manicurista_id")
    fecha = request.args.get("fecha")

    if not manicurista_id or not fecha:
        return jsonify({"error": "Faltan parámetros"}), 400

    # 1. Definimos los bloques horarios del estudio (puedes mover esto a la DB luego)
    bloques_teoricos = [
        "09:00", "10:00", "11:00", "12:00", 
        "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"
    ]

    # 2. Consultamos qué horas ya están ocupadas en la DB
    # Filtramos por manicurista, fecha y que la cita no esté cancelada
    ocupadas_db = fetch_all("""
        SELECT hora_inicio 
        FROM citas 
        WHERE manicurista_id = %s 
          AND fecha = %s 
          AND estado NOT IN ('cancelada_admin', 'cancelada_cliente')
    """, (manicurista_id, fecha))

    # Convertimos los objetos time de la DB a strings "HH:MM" para comparar
    horas_ocupadas = [c["hora_inicio"].strftime("%H:%M") for c in ocupadas_db]
    
    # 3. Calculamos las disponibles (Bloques que NO están en horas_ocupadas)
    disponibles = [h for h in bloques_teoricos if h not in horas_ocupadas]

    return jsonify({
        "disponibles": disponibles,
        "ocupadas": horas_ocupadas
    })


# ==========================================================
# MEJORA 2: PROCESO DE RESERVA CON PROTECCIÓN DE ROL
# ==========================================================
@reservas_bp.route("/reservar", methods=["GET", "POST"])
def reservar():
    # Seguridad: El admin no reserva citas para sí mismo desde aquí
    if session.get("rol") == "admin":
        flash("Como administrador, usa el Panel de Gestión para agendar citas.", "info")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        # Si no está logueado, redirigir al login (Mejora de flujo)
        if not session.get("user_id"):
            flash("Debes iniciar sesión para completar tu reserva. ✨", "warning")
            return redirect(url_for("auth.login"))

        cliente_id = session.get("user_id")
        manicurista_id = request.form.get("manicurista_id")
        fecha = request.form.get("fecha")
        hora_inicio = request.form.get("hora")
        service_ids = request.form.getlist("servicios")
        notas = request.form.get("notas", "")

        # Validación de campos obligatorios
        if not all([manicurista_id, fecha, hora_inicio, service_ids]):
            flash("Por favor, selecciona todos los pasos del ritual de belleza.", "danger")
            return redirect(url_for("reservas.reservar"))

        try:
            # Cálculo de duración básica (ejemplo 1 hora, personalizable por servicio)
            hora_dt = datetime.strptime(hora_inicio, "%H:%M")
            hora_fin = (hora_dt + timedelta(hours=1)).strftime("%H:%M")

            # Crear la cita (Estado inicial: 'pendiente')
            nueva_cita = crear_cita(
                cliente_id=cliente_id,
                manicurista_id=manicurista_id,
                fecha=fecha,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin,
                notas=notas
            )

            if nueva_cita:
                # Insertar los servicios vinculados
                for s_id in service_ids:
                    execute_query(
                        "INSERT INTO cita_servicios (cita_id, servicio_id) VALUES (%s, %s)",
                        (nueva_cita["id"], s_id)
                    )
                
                # MEJORA 3: FEEDBACK DE LUJO
                flash("¡Tu solicitud ha sido enviada! Te confirmaremos por WhatsApp en breve. ✨", "success")
                return render_template("reserva_exitosa.html", cita_id=nueva_cita["id"])

        except Exception as e:
            print(f"ERROR RESERVA: {e}")
            flash("Lo sentimos, hubo un error al procesar tu turno. Inténtalo de nuevo.", "danger")
            return redirect(url_for("reservas.reservar"))

    # --- LÓGICA PARA EL GET ---
    servicios = obtener_servicios_activos()
    manicuristas = fetch_all("SELECT id, nombre FROM manicuristas WHERE activo = TRUE")
    
    # Agrupamos servicios por categoría para que el formulario se vea ordenado
    servicios_agrupados = {}
    for s in servicios:
        cat = s['categoria']
        if cat not in servicios_agrupados:
            servicios_agrupados[cat] = []
        servicios_agrupados[cat].append(s)

    return render_template(
        "reservar.html",
        servicios_agrupados=servicios_agrupados,
        manicuristas=manicuristas
    )