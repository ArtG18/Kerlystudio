import os
from functools import wraps
from datetime import datetime, date, timedelta, time
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")


# =========================
# DATABASE HELPERS
# =========================
def get_conn():
    database_url = app.config["DATABASE_URL"]
    if not database_url:
        raise RuntimeError("DATABASE_URL no configurada")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


def fetch_one(query, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchone()
    finally:
        conn.close()


def fetch_all(query, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall()
    finally:
        conn.close()

def agrupar_servicios_por_categoria(servicios):
    agrupados = {}

    for servicio in servicios:
        categoria = servicio["categoria"]

        if categoria not in agrupados:
            agrupados[categoria] = []

        agrupados[categoria].append(servicio)

    return agrupados


def get_config(clave):
    result = fetch_one(
        "SELECT valor FROM configuracion WHERE clave = %s",
        (clave,)
    )
    return result["valor"] if result else ""


def execute_query(query, params=None, fetchone=False, fetchall=False):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            result = None
            if fetchone:
                result = cur.fetchone()
            elif fetchall:
                result = cur.fetchall()
            conn.commit()
            return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# =========================
# AUTH HELPERS
# =========================
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return fetch_one(
        "SELECT id, nombre, email, telefono, rol, activo FROM usuarios WHERE id = %s",
        (user_id,),
    )


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Debes iniciar sesión.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Debes iniciar sesión como administrador.", "warning")
            return redirect(url_for("admin_login"))
        if session.get("rol") != "admin":
            flash("No tienes permiso para entrar a esa sección.", "danger")
            return redirect(url_for("home"))
        return view_func(*args, **kwargs)

    return wrapper


@app.context_processor
def inject_user():
    return {
        "logged_user": current_user(),
        "today_date": date.today().strftime("%Y-%m-%d"),
        "get_config": get_config
    }


# =========================
# DB INIT
# =========================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # =========================
    # USUARIOS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        nombre TEXT,
        email TEXT UNIQUE,
        telefono TEXT,
        password_hash TEXT,
        rol TEXT DEFAULT 'cliente',
        activo BOOLEAN DEFAULT TRUE
    );
    """)

    # =========================
    # MANICURISTAS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS manicuristas (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        activo BOOLEAN DEFAULT TRUE
    );
    """)

    # =========================
    # SERVICIOS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS servicios (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        descripcion TEXT,
        duracion_min INTEGER NOT NULL,
        precio INTEGER NOT NULL,
        categoria TEXT,
        activo BOOLEAN DEFAULT TRUE
    );
    """)

    # 🔥 ASEGURAR COLUMNAS NUEVAS (NO ROMPE SI YA EXISTEN)
    cur.execute("""
    ALTER TABLE servicios
    ADD COLUMN IF NOT EXISTS imagen TEXT;
    """)

    # =========================
    # CITAS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS citas (
        id SERIAL PRIMARY KEY,
        cliente_id INTEGER REFERENCES usuarios(id),
        manicurista_id INTEGER REFERENCES manicuristas(id),
        fecha DATE,
        hora_inicio TIME,
        hora_fin TIME,
        estado TEXT DEFAULT 'pendiente',
        notas TEXT,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # =========================
    # RELACIÓN CITA-SERVICIOS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cita_servicios (
        id SERIAL PRIMARY KEY,
        cita_id INTEGER REFERENCES citas(id) ON DELETE CASCADE,
        servicio_id INTEGER REFERENCES servicios(id)
    );
    """)

    # =========================
    # CONFIGURACIÓN
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS configuracion (
        id SERIAL PRIMARY KEY,
        clave TEXT UNIQUE,
        valor TEXT
    );
    """)

    # =========================
    # INSERTS BASE (SIN DUPLICAR)
    # =========================

    # WhatsApp
    cur.execute("""
    INSERT INTO configuracion (clave, valor)
    VALUES ('whatsapp_numero', '56900000000')
    ON CONFLICT (clave) DO NOTHING;
    """)

    # Manicuristas
    cur.execute("""
    INSERT INTO manicuristas (nombre, activo)
    VALUES 
    ('Kerly', TRUE),
    ('Andrea', TRUE),
    ('Camila', TRUE)
    ON CONFLICT DO NOTHING;
    """)

    # Servicios
    cur.execute("""
    INSERT INTO servicios (nombre, duracion_min, precio, categoria, imagen)
    VALUES
    ('Manicure', 45, 12000, 'Manicure', 'manicure.jpg'),
    ('Pedicure', 60, 15000, 'Pedicure', 'pedicure.jpg'),
    ('Extensión', 90, 25000, 'Extensión', 'extension.jpg'),
    ('Kapping', 60, 18000, 'Kapping', 'kapping.jpg'),
    ('Pestañas', 60, 20000, 'Pestañas', 'pestanas.jpg'),
    ('Cejas', 30, 10000, 'Cejas', 'cejas.jpg'),
    ('Depilación', 40, 15000, 'Depilación', 'depilacion.jpg')
    ON CONFLICT DO NOTHING;
    """)

    conn.commit()
    cur.close()
    conn.close()


# =========================
# PUBLIC ROUTES
# =========================
@app.route("/")
def home():
    featured_services = fetch_all(
        """
        SELECT id, nombre, descripcion, duracion_min, precio, categoria
        FROM servicios
        WHERE activo = TRUE
        ORDER BY id
        LIMIT 6
        """
    )
    return render_template("home.html", featured_services=featured_services)


@app.route("/catalogo")
def catalogo():
    servicios_lista = fetch_all(
        """
        SELECT id, nombre, descripcion, duracion_min, precio, categoria
        FROM servicios
        WHERE activo = TRUE
        ORDER BY categoria ASC, nombre ASC
        """
    )
    servicios_agrupados = agrupar_servicios_por_categoria(servicios_lista)
    return render_template("catalogo.html", servicios_agrupados=servicios_agrupados)


@app.route("/registro", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        email = request.form.get("email", "").strip().lower()
        telefono = request.form.get("telefono", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not all([nombre, email, password, password2]):
            flash("Completa todos los campos obligatorios.", "danger")
            return render_template("register.html")

        if password != password2:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("register.html")

        if len(password) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
            return render_template("register.html")

        existing = fetch_one("SELECT id FROM usuarios WHERE email = %s", (email,))
        if existing:
            flash("Ya existe una cuenta con ese correo.", "warning")
            return render_template("register.html")

        execute_query(
            """
            INSERT INTO usuarios (nombre, email, telefono, password_hash, rol)
            VALUES (%s, %s, %s, %s, 'cliente')
            """,
            (nombre, email, telefono, generate_password_hash(password)),
        )

        flash("Cuenta creada correctamente. Ahora inicia sesión.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = fetch_one(
            "SELECT * FROM usuarios WHERE email = %s AND activo = TRUE",
            (email,),
        )

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Credenciales inválidas.", "danger")
            return render_template("login.html")

        if user["rol"] != "cliente":
            flash("Este acceso es solo para clientas.", "danger")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["rol"] = user["rol"]
        session["nombre"] = user["nombre"]

        flash(f"Bienvenida, {user['nombre']}.", "success")
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = fetch_one(
            "SELECT * FROM usuarios WHERE email = %s AND activo = TRUE",
            (email,),
        )

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Credenciales inválidas.", "danger")
            return render_template("admin_login.html")

        if user["rol"] != "admin":
            flash("No tienes permisos de administración.", "danger")
            return render_template("admin_login.html")

        session["user_id"] = user["id"]
        session["rol"] = user["rol"]
        session["nombre"] = user["nombre"]

        flash(f"Bienvenido, {user['nombre']}.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("home"))


@app.route("/reservar", methods=["GET", "POST"])
def reservar():

    # 🔥 BLOQUEAR ADMIN
    if current_user() and current_user().get("rol") == "admin":
        flash("Acceso no permitido para administradores.", "warning")
        return redirect(url_for("home"))

    servicios_lista = fetch_all("""
        SELECT id, nombre, duracion_min, precio, categoria
        FROM servicios
        WHERE activo = TRUE
        ORDER BY categoria ASC, nombre ASC
    """)

    servicios_agrupados = agrupar_servicios_por_categoria(servicios_lista)

    manicuristas = fetch_all("""
        SELECT DISTINCT ON (nombre) id, nombre
        FROM manicuristas
        WHERE activo = TRUE
        ORDER BY nombre, id ASC
    """)

    # 🔥 PRELLENADO
    servicios_pre = request.args.get("servicios", "")
    servicios_pre = servicios_pre.split(",") if servicios_pre else []

    manicurista_pre = request.args.get("manicurista_id")
    fecha_pre = request.args.get("fecha")

    # =========================
    # POST
    # =========================
    if request.method == "POST":

        nombre = request.form.get("nombre", "").strip()
        email = request.form.get("email", "").strip().lower()
        telefono = request.form.get("telefono", "").strip()

        service_ids = request.form.getlist("servicios")
        manicurista_id = request.form.get("manicurista_id", type=int)
        fecha_raw = request.form.get("fecha", "")
        hora_inicio_raw = request.form.get("hora_inicio", "")
        notas = request.form.get("notas", "").strip()

        # VALIDACIONES
        if not nombre or not email or not telefono:
            flash("Debes completar nombre, correo y teléfono.", "danger")
            return render_template(
                "reservar.html",
                servicios_agrupados=servicios_agrupados,
                manicuristas=manicuristas,
                servicios_pre=servicios_pre,
                manicurista_pre=manicurista_pre,
                fecha_pre=fecha_pre,
            )

        if not service_ids or not manicurista_id or not fecha_raw or not hora_inicio_raw:
            flash("Debes completar servicio, manicurista, fecha y hora.", "danger")
            return render_template(
                "reservar.html",
                servicios_agrupados=servicios_agrupados,
                manicuristas=manicuristas,
                servicios_pre=servicios_pre,
                manicurista_pre=manicurista_pre,
                fecha_pre=fecha_pre,
            )

        try:
            service_ids = [int(sid) for sid in service_ids]
            fecha = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
            hora_inicio = parse_time(hora_inicio_raw)
        except ValueError:
            flash("Datos inválidos.", "danger")
            return render_template(
                "reservar.html",
                servicios_agrupados=servicios_agrupados,
                manicuristas=manicuristas,
                servicios_pre=servicios_pre,
                manicurista_pre=manicurista_pre,
                fecha_pre=fecha_pre,
            )

        if not validate_future_date(fecha):
            flash("No puedes reservar en una fecha pasada.", "danger")
            return render_template(
                "reservar.html",
                servicios_agrupados=servicios_agrupados,
                manicuristas=manicuristas,
                servicios_pre=servicios_pre,
                manicurista_pre=manicurista_pre,
                fecha_pre=fecha_pre,
            )

        selected_services = get_selected_services(service_ids)

        if len(selected_services) != len(service_ids):
            flash("Servicios inválidos.", "danger")
            return render_template(
                "reservar.html",
                servicios_agrupados=servicios_agrupados,
                manicuristas=manicuristas,
                servicios_pre=servicios_pre,
                manicurista_pre=manicurista_pre,
                fecha_pre=fecha_pre,
            )

        total_duration = calculate_total_duration(selected_services)

        hora_fin_dt = combine_date_time(fecha, hora_inicio) + timedelta(minutes=total_duration)
        hora_fin = hora_fin_dt.time()

        weekday = fecha.weekday()
        schedule = get_manicurista_schedule(manicurista_id, weekday)

        if not schedule:
            flash("No atiende ese día.", "danger")
            return render_template(
                "reservar.html",
                servicios_agrupados=servicios_agrupados,
                manicuristas=manicuristas,
                servicios_pre=servicios_pre,
                manicurista_pre=manicurista_pre,
                fecha_pre=fecha_pre,
            )

        if hora_inicio < schedule["hora_inicio"] or hora_fin > schedule["hora_fin"]:
            flash("Horario fuera de jornada.", "danger")
            return render_template(
                "reservar.html",
                servicios_agrupados=servicios_agrupados,
                manicuristas=manicuristas,
                servicios_pre=servicios_pre,
                manicurista_pre=manicurista_pre,
                fecha_pre=fecha_pre,
            )

        if not is_slot_available(manicurista_id, fecha, hora_inicio, hora_fin):
            flash("Horario no disponible.", "warning")
            return render_template(
                "reservar.html",
                servicios_agrupados=servicios_agrupados,
                manicuristas=manicuristas,
                servicios_pre=servicios_pre,
                manicurista_pre=manicurista_pre,
                fecha_pre=fecha_pre,
            )

        cliente = fetch_one(
            "SELECT id FROM usuarios WHERE email = %s LIMIT 1",
            (email,),
        )

        if not cliente:
            cliente = execute_query(
                """
                INSERT INTO usuarios (nombre, email, telefono, password_hash, rol, activo)
                VALUES (%s, %s, %s, %s, 'cliente', TRUE)
                RETURNING id
                """,
                (
                    nombre,
                    email,
                    telefono,
                    generate_password_hash(os.urandom(16).hex()),
                ),
                fetchone=True,
            )
        else:
            execute_query(
                """
                UPDATE usuarios
                SET nombre=%s, telefono=%s, activo=TRUE
                WHERE id=%s
                """,
                (nombre, telefono, cliente["id"]),
            )

        cita = execute_query(
            """
            INSERT INTO citas (cliente_id, manicurista_id, fecha, hora_inicio, hora_fin, estado, notas)
            VALUES (%s, %s, %s, %s, %s, 'pendiente', %s)
            RETURNING id
            """,
            (cliente["id"], manicurista_id, fecha, hora_inicio, hora_fin, notas),
            fetchone=True,
        )

        for service in selected_services:
            execute_query(
                "INSERT INTO cita_servicios (cita_id, servicio_id) VALUES (%s, %s)",
                (cita["id"], service["id"]),
            )

        flash("✨ Tu cita fue agendada con éxito", "success")
        return redirect(url_for("mis_citas"))

    # =========================
    # GET
    # =========================
    return render_template(
        "reservar.html",
        servicios_agrupados=servicios_agrupados,
        manicuristas=manicuristas,
        servicios_pre=servicios_pre,
        manicurista_pre=manicurista_pre,
        fecha_pre=fecha_pre,
    )


@app.route("/mis-citas")
@login_required
def mis_citas():
    if session.get("rol") != "cliente":
        return redirect(url_for("admin_dashboard"))

    citas = fetch_all("""
    SELECT
        c.id,
        c.fecha,
        c.hora_inicio,
        c.hora_fin,
        c.estado,
        u.nombre AS cliente_nombre,
        u.telefono,
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


@app.route("/cancelar-cita/<int:cita_id>", methods=["POST"])
@login_required
def cancelar_cita_cliente(cita_id):

    if session.get("rol") != "cliente":
        return redirect(url_for("admin_dashboard"))

    cita = fetch_one(
        "SELECT id, cliente_id, estado FROM citas WHERE id = %s",
        (cita_id,),
    )

    if not cita:
        flash("Cita no encontrada.", "danger")
        return redirect(url_for("mis_citas"))

    if cita["cliente_id"] != session.get("user_id"):
        flash("No tienes permiso.", "danger")
        return redirect(url_for("mis_citas"))

    if cita["estado"] not in ["pendiente", "confirmada"]:
        flash("No se puede cancelar.", "warning")
        return redirect(url_for("mis_citas"))

    execute_query(
        "UPDATE citas SET estado = 'cancelada_cliente' WHERE id = %s",
        (cita_id,),
    )

    flash("Cita cancelada correctamente.", "success")
    return redirect(url_for("mis_citas"))


@app.route("/reagendar/<int:cita_id>")
@login_required
def reagendar_cita(cita_id):

    cita = fetch_one(
        "SELECT * FROM citas WHERE id = %s",
        (cita_id,),
    )

    if not cita:
        return redirect(url_for("mis_citas"))

    if cita["cliente_id"] != session.get("user_id"):
        return redirect(url_for("mis_citas"))

    servicios = fetch_all(
        "SELECT servicio_id FROM cita_servicios WHERE cita_id = %s",
        (cita_id,),
    )

    servicios_ids = [str(s["servicio_id"]) for s in servicios]

    return redirect(
        url_for(
            "reservar",
            servicios=",".join(servicios_ids),
            manicurista_id=cita["manicurista_id"],
            fecha=cita["fecha"].strftime("%Y-%m-%d"),
        )
    )


@app.route("/api/disponibilidad")
def api_disponibilidad():
    manicurista_id = request.args.get("manicurista_id", type=int)
    fecha_raw = request.args.get("fecha", "")
    service_ids = request.args.getlist("servicios", type=int)

    if not manicurista_id or not fecha_raw or not service_ids:
        return jsonify({"slots": [], "error": "Faltan parámetros"}), 400

    try:
        fecha = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"slots": [], "error": "Fecha inválida"}), 400

    selected_services = get_selected_services(service_ids)
    if not selected_services:
        return jsonify({"slots": [], "error": "Servicios inválidos"}), 400

    total_duration = calculate_total_duration(selected_services)
    slots = generate_available_slots(manicurista_id, fecha, total_duration)
    return jsonify({"slots": slots})

@app.route("/horas-disponibles")
def horas_disponibles():

    manicurista_id = request.args.get("manicurista_id", type=int)
    fecha = request.args.get("fecha")

    if not manicurista_id or not fecha:
        return {"ocupadas": []}

    fecha = datetime.strptime(fecha, "%Y-%m-%d").date()

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

@app.route("/horarios")
def obtener_horarios():

    manicurista_id = request.args.get("manicurista_id", type=int)
    fecha_raw = request.args.get("fecha", "")
    service_ids = request.args.getlist("servicios", type=int)

    if not manicurista_id or not fecha_raw or not service_ids:
        return jsonify({"slots": []})

    try:
        fecha = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"slots": []})

    selected_services = get_selected_services(service_ids)
    if not selected_services:
        return jsonify({"slots": []})

    total_duration = calculate_total_duration(selected_services)

    slots = generate_available_slots(manicurista_id, fecha, total_duration)

    return jsonify({"slots": slots})

# =========================
# ADMIN ROUTES
# =========================
# =========================
# DASHBOARD
# =========================
@app.route("/admin")
@admin_required
def admin_dashboard():

    stats = fetch_one("""
        SELECT
            COUNT(*) AS total_citas,
            COUNT(*) FILTER (WHERE estado = 'pendiente') AS pendientes,
            COUNT(*) FILTER (WHERE estado = 'confirmada') AS confirmadas,
            COUNT(*) FILTER (WHERE fecha = CURRENT_DATE) AS hoy
        FROM citas
    """)

    ingresos_hoy = fetch_one("""
        SELECT COALESCE(SUM(s.precio),0) as total
        FROM citas c
        JOIN cita_servicios cs ON cs.cita_id = c.id
        JOIN servicios s ON s.id = cs.servicio_id
        WHERE c.estado = 'completada'
        AND c.fecha = CURRENT_DATE
    """)

    return render_template("dashboard.html", stats=stats, ingresos_hoy=ingresos_hoy)


# =========================
# LISTADO DE CITAS
# =========================
@app.route("/admin/citas")
@admin_required
def admin_citas():

    citas = fetch_all("""
        SELECT
            c.id,
            c.fecha,
            c.hora_inicio,
            c.hora_fin,
            c.estado,
            u.nombre AS cliente_nombre,
            u.telefono,
            m.nombre AS manicurista_nombre,
            STRING_AGG(s.nombre, ', ') AS servicios
        FROM citas c
        JOIN usuarios u ON u.id = c.cliente_id
        JOIN manicuristas m ON m.id = c.manicurista_id
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
        GROUP BY c.id, u.nombre, u.telefono, m.nombre
        ORDER BY c.fecha DESC, c.hora_inicio DESC
    """)

    ingresos_hoy = fetch_one("""
        SELECT COALESCE(SUM(s.precio),0) as total
        FROM citas c
        JOIN cita_servicios cs ON cs.cita_id = c.id
        JOIN servicios s ON s.id = cs.servicio_id
        WHERE c.estado = 'completada'
        AND c.fecha = CURRENT_DATE
    """)

    return render_template(
        "admin_citas.html",
        citas=citas,
        ingresos_hoy=ingresos_hoy
    )


# =========================
# CONFIRMAR
# =========================
@app.route("/admin/citas/<int:cita_id>/confirmar", methods=["POST"])
@admin_required
def confirmar_cita(cita_id):

    execute_query(
        "UPDATE citas SET estado = 'confirmada' WHERE id = %s",
        (cita_id,)
    )

    flash("Cita confirmada", "success")
    return redirect(url_for("admin_citas"))


# =========================
# RECHAZAR
# =========================
@app.route("/admin/citas/<int:cita_id>/rechazar", methods=["POST"])
@admin_required
def rechazar_cita(cita_id):

    execute_query(
        "UPDATE citas SET estado = 'rechazada' WHERE id = %s",
        (cita_id,)
    )

    flash("Cita rechazada", "info")
    return redirect(url_for("admin_citas"))


# =========================
# COMPLETAR (💸 CLAVE)
# =========================
@app.route("/admin/citas/<int:cita_id>/completar", methods=["POST"])
@admin_required
def completar_cita(cita_id):

    execute_query(
        "UPDATE citas SET estado = 'completada' WHERE id = %s",
        (cita_id,)
    )

    flash("Cita completada 💸", "success")
    return redirect(url_for("admin_citas"))


# =========================
# CANCELAR
# =========================
@app.route("/admin/citas/<int:cita_id>/cancelar", methods=["POST"])
@admin_required
def cancelar_cita_admin(cita_id):

    execute_query(
        "UPDATE citas SET estado = 'cancelada_admin' WHERE id = %s",
        (cita_id,)
    )

    flash("Cita cancelada", "warning")
    return redirect(url_for("admin_citas"))


# =========================
# NO ASISTIÓ
# =========================
@app.route("/admin/citas/<int:cita_id>/no-asistio", methods=["POST"])
@admin_required
def marcar_no_asistio(cita_id):

    execute_query(
        "UPDATE citas SET estado = 'no_asistio' WHERE id = %s",
        (cita_id,)
    )

    flash("Cliente no asistió", "warning")
    return redirect(url_for("admin_citas"))


@app.route("/admin/servicios", methods=["GET", "POST"])
@admin_required
def admin_servicios():

    servicios = fetch_all("SELECT * FROM servicios ORDER BY id DESC")

    return render_template(
        "admin_servicios.html",
        servicios=servicios,
        categorias_servicio=[
            "Manicure", "Pedicure", "Extensión",
            "Kapping", "Pestañas", "Cejas", "Depilación"
        ],
        servicio_editar=None
    )


@app.route("/admin/servicios/<int:servicio_id>/editar", methods=["POST"])
@admin_required
def editar_servicio(servicio_id):

    nombre = request.form.get("nombre")
    categoria = request.form.get("categoria")
    descripcion = request.form.get("descripcion")
    duracion = request.form.get("duracion_min")
    precio = request.form.get("precio")

    execute_query("""
        UPDATE servicios
        SET nombre=%s, categoria=%s, descripcion=%s,
            duracion_min=%s, precio=%s
        WHERE id=%s
    """, (nombre, categoria, descripcion, duracion, precio, servicio_id))

    flash("Servicio actualizado", "success")
    return redirect(url_for("admin_servicios"))

@app.route("/admin/manicuristas", methods=["GET", "POST"])
@admin_required
def admin_manicuristas():

    if request.method == "POST":
        nombre = request.form.get("nombre")

        if nombre:
            execute_query("""
                INSERT INTO manicuristas (nombre, activo)
                VALUES (%s, TRUE)
                ON CONFLICT DO NOTHING
            """, (nombre,))

    manicuristas = fetch_all("""
        SELECT * FROM manicuristas ORDER BY nombre
    """)

    return render_template(
        "admin_manicuristas.html",
        manicuristas=manicuristas
    )

# =========================
# APP STARTUP
# =========================
init_db()


if __name__ == "__main__":
    app.run(debug=True)