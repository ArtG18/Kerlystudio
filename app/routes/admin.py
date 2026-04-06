from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from app.db import fetch_all, fetch_one, execute_query

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# =========================
# DECORADOR DE SEGURIDAD
# =========================
def admin_required():
    def wrapper(func):
        def inner(*args, **kwargs):
            # Verificar si hay sesión y si el rol es admin
            if not session.get("user_id"):
                flash("Por favor, inicia sesión como administrador.", "warning")
                return redirect(url_for("auth.login"))
            
            if session.get("rol") != "admin":
                flash("No tienes permisos para acceder a esta sección.", "danger")
                return redirect(url_for("public.home"))
            
            return func(*args, **kwargs)
        inner.__name__ = func.__name__
        return inner
    return wrapper

# =========================
# DASHBOARD PRINCIPAL
# =========================
@admin_bp.route("/")
@admin_required()
def dashboard():
    # Métricas rápidas
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

    # Próximas 10 citas (Ordenadas por lo más reciente)
    citas = fetch_all("""
        SELECT 
            c.id, c.fecha, c.hora_inicio, c.estado,
            u.nombre AS cliente_nombre,
            COALESCE(STRING_AGG(s.nombre, ', '), 'Sin servicios') AS servicios
        FROM citas c
        JOIN usuarios u ON u.id = c.cliente_id
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
        GROUP BY c.id, u.nombre
        ORDER BY c.fecha DESC, c.hora_inicio DESC
        LIMIT 10
    """)

    return render_template("dashboard.html", stats=stats, citas=citas)

# =========================
# GESTIÓN DE CITAS (LISTADO)
# =========================
@admin_bp.route("/citas")
@admin_required()
def admin_citas():
    citas = fetch_all("""
        SELECT 
            c.id, c.fecha, c.hora_inicio, c.estado,
            u.nombre AS cliente_nombre, u.telefono,
            m.nombre AS manicurista_nombre,
            COALESCE(STRING_AGG(s.nombre, ', '), '') AS servicios
        FROM citas c
        JOIN usuarios u ON u.id = c.cliente_id
        JOIN manicuristas m ON m.id = c.manicurista_id
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
        GROUP BY c.id, u.nombre, u.telefono, m.nombre
        ORDER BY c.fecha DESC, c.hora_inicio DESC
    """)
    
    # Ingresos totales de hoy para el encabezado
    ingresos_hoy = fetch_one("""
        SELECT SUM(s.precio) as total
        FROM cita_servicios cs
        JOIN servicios s ON s.id = cs.servicio_id
        JOIN citas c ON c.id = cs.cita_id
        WHERE c.estado = 'completada' AND c.fecha = CURRENT_DATE
    """)

    return render_template("admin_citas.html", citas=citas, ingresos_hoy=ingresos_hoy)

# =========================
# ACCIONES DE CITA (CAMBIO DE ESTADO)
# =========================
@admin_bp.route("/citas/<int:cita_id>/<nuevo_estado>", methods=["POST"])
@admin_required()
def cambiar_estado_cita(cita_id, nuevo_estado):
    estados_validos = ['confirmada', 'cancelada_admin', 'completada', 'pendiente']
    
    if nuevo_estado in estados_validos:
        execute_query(
            "UPDATE citas SET estado = %s WHERE id = %s",
            (nuevo_estado, cita_id)
        )
        flash(f"Cita actualizada a: {nuevo_estado.replace('_', ' ').capitalize()}", "success")
    else:
        flash("Estado no válido.", "danger")
        
    return redirect(url_for("admin.admin_citas"))

# =========================
# GESTIÓN DE SERVICIOS
# =========================
@admin_bp.route("/servicios", methods=["GET", "POST"])
@admin_required()
def admin_servicios():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        categoria = request.form.get("categoria")
        precio = request.form.get("precio")
        duracion = request.form.get("duracion_min")
        descripcion = request.form.get("descripcion")

        execute_query("""
            INSERT INTO servicios (nombre, categoria, precio, duracion_min, descripcion, activo)
            VALUES (%s, %s, %s, %s, %s, TRUE)
        """, (nombre, categoria, precio, duracion, descripcion))
        
        flash("Servicio creado con éxito ✨", "success")
        return redirect(url_for("admin.admin_servicios"))

    servicios = fetch_all("SELECT * FROM servicios ORDER BY categoria, nombre")
    categorias = ["Manicura", "Pedicura", "Esmaltado", "Retiro", "Diseño"]
    
    return render_template("admin_servicios.html", servicios=servicios, categorias_servicio=categorias)

@admin_bp.route("/servicios/toggle/<int:servicio_id>", methods=["POST"])
@admin_required()
def toggle_servicio(servicio_id):
    execute_query("UPDATE servicios SET activo = NOT activo WHERE id = %s", (servicio_id,))
    flash("Estado del servicio actualizado.", "success")
    return redirect(url_for("admin.admin_servicios"))