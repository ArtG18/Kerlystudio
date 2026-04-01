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
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(120) NOT NULL,
                    email VARCHAR(150) UNIQUE NOT NULL,
                    telefono VARCHAR(30),
                    password_hash TEXT NOT NULL,
                    rol VARCHAR(20) NOT NULL DEFAULT 'cliente',
                    activo BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS manicuristas (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(120) NOT NULL,
                    activo BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS servicios (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(150) NOT NULL,
                    descripcion TEXT,
                    duracion_min INTEGER NOT NULL,
                    precio NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    activo BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                ALTER TABLE servicios
                ADD COLUMN IF NOT EXISTS categoria VARCHAR(50) NOT NULL DEFAULT 'Manicure';
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS horarios_manicurista (
                    id SERIAL PRIMARY KEY,
                    manicurista_id INTEGER NOT NULL REFERENCES manicuristas(id) ON DELETE CASCADE,
                    dia_semana INTEGER NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
                    hora_inicio TIME NOT NULL,
                    hora_fin TIME NOT NULL,
                    activo BOOLEAN NOT NULL DEFAULT TRUE
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS citas (
                    id SERIAL PRIMARY KEY,
                    cliente_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    manicurista_id INTEGER NOT NULL REFERENCES manicuristas(id),
                    fecha DATE NOT NULL,
                    hora_inicio TIME NOT NULL,
                    hora_fin TIME NOT NULL,
                    estado VARCHAR(30) NOT NULL DEFAULT 'pendiente',
                    notas TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cita_servicios (
                    id SERIAL PRIMARY KEY,
                    cita_id INTEGER NOT NULL REFERENCES citas(id) ON DELETE CASCADE,
                    servicio_id INTEGER NOT NULL REFERENCES servicios(id)
                );
                """
            )

            cur.execute("""
                CREATE TABLE IF NOT EXISTS configuracion (
                    id SERIAL PRIMARY KEY,
                    clave TEXT UNIQUE,
                    valor TEXT
                );
                """)

            cur.execute("""
                INSERT INTO configuracion (clave, valor)
                VALUES ('whatsapp_numero', '56959257968')
                ON CONFLICT (clave) DO NOTHING;
             """)

            conn.commit()
    finally:
        conn.close()

    seed_initial_data()


def seed_initial_data():
    admin_email = os.getenv("ADMIN_EMAIL", "admin@kerlystudio.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "#Ks2026$")
    admin_nombre = os.getenv("ADMIN_NAME", "Administrador")

    existing_admin = fetch_one("SELECT id FROM usuarios WHERE rol = 'admin' LIMIT 1")

    if existing_admin:
        execute_query(
            """
            UPDATE usuarios
            SET nombre = %s,
                email = %s,
                password_hash = %s,
                activo = TRUE
            WHERE id = %s
            """,
            (
                admin_nombre,
                admin_email,
                generate_password_hash(admin_password),
                existing_admin["id"],
            ),
        )
    else:
        execute_query(
            """
            INSERT INTO usuarios (nombre, email, telefono, password_hash, rol, activo)
            VALUES (%s, %s, %s, %s, 'admin', TRUE)
            """,
            (
                admin_nombre,
                admin_email,
                "",
                generate_password_hash(admin_password),
            ),
        )

    has_services = fetch_one("SELECT id FROM servicios LIMIT 1")
    if not has_services:
        default_services = [
            ("Manicure Permanente", "Esmaltado permanente con preparación básica.", 90, 15000, "Manicure"),
            ("Kapping", "Refuerzo sobre uña natural.", 120, 20000, "Kapping"),
            ("Extensión de Uñas", "Set completo de extensión.", 180, 30000, "Extensiones"),
            ("Pedicure Spa", "Pedicure con exfoliación e hidratación.", 90, 18000, "Pedicure"),
        ]
        for service in default_services:
            execute_query(
                """
                INSERT INTO servicios (nombre, descripcion, duracion_min, precio, categoria)
                VALUES (%s, %s, %s, %s, %s)
                """,
                service,
            )

    has_manicurists = fetch_one("SELECT id FROM manicuristas LIMIT 1")
    if not has_manicurists:
        for nombre in ["Kerly", "Valentina", "Camila"]:
            execute_query(
                "INSERT INTO manicuristas (nombre) VALUES (%s)",
                (nombre,),
            )

        manicuristas = fetch_all("SELECT id FROM manicuristas")
        for m in manicuristas:
            for dia_semana in range(0, 6):  # lunes a sábado
                execute_query(
                    """
                    INSERT INTO horarios_manicurista (manicurista_id, dia_semana, hora_inicio, hora_fin)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (m["id"], dia_semana, "09:00", "19:00"),
                )


# =========================
# UTILS
# =========================
def parse_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def combine_date_time(base_date: date, base_time: time) -> datetime:
    return datetime.combine(base_date, base_time)


def get_selected_services(service_ids):
    if not service_ids:
        return []
    placeholders = ", ".join(["%s"] * len(service_ids))
    return fetch_all(
        f"""
        SELECT id, nombre, duracion_min, precio, categoria
        FROM servicios
        WHERE activo = TRUE AND id IN ({placeholders})
        """,
        tuple(service_ids),
    )


def calculate_total_duration(service_rows):
    return sum(service["duracion_min"] for service in service_rows)


def get_manicurista_schedule(manicurista_id, weekday):
    return fetch_one(
        """
        SELECT hora_inicio, hora_fin
        FROM horarios_manicurista
        WHERE manicurista_id = %s AND dia_semana = %s AND activo = TRUE
        LIMIT 1
        """,
        (manicurista_id, weekday),
    )


def get_booked_ranges(manicurista_id, target_date):
    return fetch_all(
        """
        SELECT hora_inicio, hora_fin
        FROM citas
        WHERE manicurista_id = %s
          AND fecha = %s
          AND estado IN ('pendiente', 'confirmada')
        ORDER BY hora_inicio
        """,
        (manicurista_id, target_date),
    )


def overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def is_slot_available(manicurista_id, target_date, start_time, end_time):
    booked_ranges = get_booked_ranges(manicurista_id, target_date)
    for booked in booked_ranges:
        if overlaps(start_time, end_time, booked["hora_inicio"], booked["hora_fin"]):
            return False
    return True


def generate_available_slots(manicurista_id, target_date, duration_min, interval_min=30):
    weekday = target_date.weekday()
    schedule = get_manicurista_schedule(manicurista_id, weekday)
    if not schedule:
        return []

    start_dt = combine_date_time(target_date, schedule["hora_inicio"])
    end_dt = combine_date_time(target_date, schedule["hora_fin"])
    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=interval_min)

    slots = []
    cursor = start_dt
    while cursor + duration <= end_dt:
        slot_start = cursor.time()
        slot_end = (cursor + duration).time()
        if is_slot_available(manicurista_id, target_date, slot_start, slot_end):
            slots.append(
                {
                    "hora_inicio": slot_start.strftime("%H:%M"),
                    "hora_fin": slot_end.strftime("%H:%M"),
                }
            )
        cursor += step
    return slots


def validate_future_date(target_date):
    return target_date >= date.today()


def agrupar_servicios_por_categoria(servicios_lista):
    servicios_agrupados = defaultdict(list)

    for s in servicios_lista:
        categoria = s.get("categoria") or "Otros"
        servicios_agrupados[categoria].append(s)

    return dict(servicios_agrupados)


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

            servicios_lista = fetch_all(
                """
                SELECT id, nombre, duracion_min, precio, categoria
                FROM servicios
                WHERE activo = TRUE
                ORDER BY categoria ASC, nombre ASC
                """
            )

            servicios_agrupados = agrupar_servicios_por_categoria(servicios_lista)

            manicuristas = fetch_all(
                """
            SELECT id, nombre
            FROM manicuristas
            WHERE activo = TRUE
            ORDER BY nombre
            """
        )

            # 🔥 PRELLENADO
            servicios_pre = request.args.get("servicios", "")
            servicios_pre = servicios_pre.split(",") if servicios_pre else []

            manicurista_pre = request.args.get("manicurista_id")
            fecha_pre = request.args.get("fecha")

            if request.method == "POST":

                nombre = request.form.get("nombre", "").strip()
            email = request.form.get("email", "").strip().lower()
            telefono = request.form.get("telefono", "").strip()

            service_ids = request.form.getlist("servicios")
            manicurista_id = request.form.get("manicurista_id", type=int)
            fecha_raw = request.form.get("fecha", "")
            hora_inicio_raw = request.form.get("hora_inicio", "")
            notas = request.form.get("notas", "").strip()

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

    citas = fetch_all(
        """
        SELECT
            c.id,
            c.fecha,
            c.hora_inicio,
            c.hora_fin,
            c.estado,
            c.notas,
            m.nombre AS manicurista_nombre,
            STRING_AGG(s.nombre, ', ' ORDER BY s.nombre) AS servicios
        FROM citas c
        JOIN manicuristas m ON m.id = c.manicurista_id
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
        WHERE c.cliente_id = %s
        GROUP BY c.id, m.nombre
        ORDER BY c.fecha DESC, c.hora_inicio DESC
        """,
        (session["user_id"],),
    )
    return render_template("mis_citas.html", citas=citas)


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
@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = fetch_one(
        """
        SELECT
            COUNT(*) AS total_citas,
            COUNT(*) FILTER (WHERE estado = 'pendiente') AS pendientes,
            COUNT(*) FILTER (WHERE estado = 'confirmada') AS confirmadas,
            COUNT(*) FILTER (WHERE fecha = CURRENT_DATE) AS hoy
        FROM citas
        """
    )

    proximas_citas = fetch_all(
        """
        SELECT
            c.id,
            c.fecha,
            c.hora_inicio,
            c.hora_fin,
            c.estado,
            u.nombre AS cliente_nombre,
            u.telefono,
            m.nombre AS manicurista_nombre,
            STRING_AGG(s.nombre, ', ' ORDER BY s.nombre) AS servicios
        FROM citas c
        JOIN usuarios u ON u.id = c.cliente_id
        JOIN manicuristas m ON m.id = c.manicurista_id
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
        GROUP BY c.id, u.nombre, u.telefono, m.nombre
        ORDER BY c.fecha ASC, c.hora_inicio ASC
        LIMIT 20
        """
    )

    return render_template("dashboard.html", stats=stats, citas=proximas_citas)


@app.route("/admin/citas")
@admin_required
def admin_citas():
    q = request.args.get("q", "").strip()
    estado = request.args.get("estado", "").strip().lower()
    manicurista_id = request.args.get("manicurista_id", type=int)
    fecha = request.args.get("fecha", "").strip()

    filters = []
    params = []

    if q:
        filters.append("(u.nombre ILIKE %s OR u.email ILIKE %s OR COALESCE(u.telefono, '') ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if estado:
        filters.append("c.estado = %s")
        params.append(estado)

    if manicurista_id:
        filters.append("c.manicurista_id = %s")
        params.append(manicurista_id)

    if fecha:
        filters.append("c.fecha = %s")
        params.append(fecha)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    citas = fetch_all(
        f"""
        SELECT
            c.id,
            c.fecha,
            c.hora_inicio,
            c.hora_fin,
            c.estado,
            c.notas,
            u.nombre AS cliente_nombre,
            u.email AS cliente_email,
            u.telefono,
            m.nombre AS manicurista_nombre,
            STRING_AGG(s.nombre, ', ' ORDER BY s.nombre) AS servicios
        FROM citas c
        JOIN usuarios u ON u.id = c.cliente_id
        JOIN manicuristas m ON m.id = c.manicurista_id
        LEFT JOIN cita_servicios cs ON cs.cita_id = c.id
        LEFT JOIN servicios s ON s.id = cs.servicio_id
        {where_clause}
        GROUP BY c.id, u.nombre, u.email, u.telefono, m.nombre
        ORDER BY c.fecha DESC, c.hora_inicio DESC
        """,
        tuple(params),
    )

    manicuristas = fetch_all(
        "SELECT id, nombre FROM manicuristas WHERE activo = TRUE ORDER BY nombre"
    )
    return render_template("admin_citas.html", citas=citas, manicuristas=manicuristas)


@app.route("/admin/citas/<int:cita_id>/confirmar", methods=["POST"])
@admin_required
def confirmar_cita(cita_id):
    cita = fetch_one(
        "SELECT id, manicurista_id, fecha, hora_inicio, hora_fin, estado FROM citas WHERE id = %s",
        (cita_id,),
    )
    if not cita:
        flash("Cita no encontrada.", "danger")
        return redirect(url_for("admin_citas"))

    conflicting = fetch_one(
        """
        SELECT id
        FROM citas
        WHERE manicurista_id = %s
          AND fecha = %s
          AND estado = 'confirmada'
          AND id <> %s
          AND (%s < hora_fin AND hora_inicio < %s)
        LIMIT 1
        """,
        (
            cita["manicurista_id"],
            cita["fecha"],
            cita_id,
            cita["hora_inicio"],
            cita["hora_fin"],
        ),
    )

    if conflicting:
        flash("No se puede confirmar: hay conflicto con otra cita confirmada.", "danger")
        return redirect(url_for("admin_citas"))

    execute_query("UPDATE citas SET estado = 'confirmada' WHERE id = %s", (cita_id,))
    flash("Cita confirmada correctamente.", "success")
    return redirect(url_for("admin_citas"))


@app.route("/admin/citas/<int:cita_id>/rechazar", methods=["POST"])
@admin_required
def rechazar_cita(cita_id):
    execute_query("UPDATE citas SET estado = 'rechazada' WHERE id = %s", (cita_id,))
    flash("Cita rechazada.", "info")
    return redirect(url_for("admin_citas"))


@app.route("/admin/citas/<int:cita_id>/completar", methods=["POST"])
@admin_required
def completar_cita(cita_id):
    execute_query("UPDATE citas SET estado = 'completada' WHERE id = %s", (cita_id,))
    flash("Cita marcada como completada.", "success")
    return redirect(url_for("admin_citas"))


@app.route("/admin/citas/<int:cita_id>/cancelar", methods=["POST"])
@admin_required
def cancelar_cita_admin(cita_id):
    execute_query(
        "UPDATE citas SET estado = 'cancelada_admin' WHERE id = %s",
        (cita_id,),
    )
    flash("Cita cancelada por administración.", "info")
    return redirect(url_for("admin_citas"))


@app.route("/admin/citas/<int:cita_id>/no-asistio", methods=["POST"])
@admin_required
def marcar_no_asistio(cita_id):
    execute_query(
        "UPDATE citas SET estado = 'no_asistio' WHERE id = %s",
        (cita_id,),
    )
    flash("La cita fue marcada como no asistida.", "warning")
    return redirect(url_for("admin_citas"))


@app.route("/admin/servicios", methods=["GET", "POST"])
@admin_required
def admin_servicios():
    categorias_servicio = [
    "Manicure",
    "Pedicure",
    "Extensión",
    "Kapping",
    "Pestañas",
    "Cejas",
    "Depilación"
    ]

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    duracion_min = request.form.get("duracion_min", type=int)
    precio = request.form.get("precio", type=float)
    categoria = request.form.get("categoria", "").strip()

    if not nombre or duracion_min is None or precio is None or not categoria:
        flash("Completa nombre, categoría, duración y precio.", "danger")
        return redirect(url_for("admin_servicios"))

    if duracion_min <= 0:
        flash("La duración debe ser mayor que cero.", "danger")
        return redirect(url_for("admin_servicios"))

    if precio < 0:
        flash("El precio no puede ser negativo.", "danger")
        return redirect(url_for("admin_servicios"))

    execute_query(
        """
        INSERT INTO servicios (nombre, descripcion, duracion_min, precio, categoria)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (nombre, descripcion, duracion_min, precio, categoria),
    )
    flash("Servicio agregado correctamente.", "success")
    return redirect(url_for("admin_servicios"))

    servicios = fetch_all(
    "SELECT * FROM servicios ORDER BY activo DESC, categoria ASC, nombre ASC"
    )
    servicio_editar_id = request.args.get("editar", type=int)
    servicio_editar = None

    if servicio_editar_id:
        servicio_editar = fetch_one(
        "SELECT * FROM servicios WHERE id = %s",
        (servicio_editar_id,),
    )

    return render_template(
    "admin_servicios.html",
    servicios=servicios,
    servicio_editar=servicio_editar,
    categorias_servicio=categorias_servicio,
    )


@app.route("/admin/servicios/<int:servicio_id>/editar", methods=["POST"])
@admin_required
def editar_servicio(servicio_id):
    servicio = fetch_one("SELECT * FROM servicios WHERE id = %s", (servicio_id,))
    if not servicio:
        flash("Servicio no encontrado.", "danger")
        return redirect(url_for("admin_servicios"))

    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    duracion_min = request.form.get("duracion_min", type=int)
    precio = request.form.get("precio", type=float)
    categoria = request.form.get("categoria", "").strip()

    if not nombre or duracion_min is None or precio is None or not categoria:
        flash("Completa nombre, categoría, duración y precio.", "danger")
        return redirect(url_for("admin_servicios", editar=servicio_id))

    if duracion_min <= 0:
        flash("La duración debe ser mayor que cero.", "danger")
        return redirect(url_for("admin_servicios", editar=servicio_id))

    if precio < 0:
        flash("El precio no puede ser negativo.", "danger")
        return redirect(url_for("admin_servicios", editar=servicio_id))

    execute_query(
        """
        UPDATE servicios
        SET nombre = %s,
            descripcion = %s,
            duracion_min = %s,
            precio = %s,
            categoria = %s
        WHERE id = %s
        """,
        (nombre, descripcion, duracion_min, precio, categoria, servicio_id),
    )

    flash("Servicio actualizado correctamente.", "success")
    return redirect(url_for("admin_servicios"))


@app.route("/admin/servicios/<int:servicio_id>/toggle", methods=["POST"])
@admin_required
def toggle_servicio(servicio_id):
    servicio = fetch_one(
        "SELECT id, activo, nombre FROM servicios WHERE id = %s",
        (servicio_id,),
    )
    if not servicio:
        flash("Servicio no encontrado.", "danger")
        return redirect(url_for("admin_servicios"))

    nuevo_estado = not servicio["activo"]
    execute_query(
        "UPDATE servicios SET activo = %s WHERE id = %s",
        (nuevo_estado, servicio_id),
    )

    if nuevo_estado:
        flash(f"Servicio '{servicio['nombre']}' activado.", "success")
    else:
        flash(f"Servicio '{servicio['nombre']}' desactivado.", "info")

    return redirect(url_for("admin_servicios"))


@app.route("/admin/manicuristas", methods=["GET", "POST"])
@admin_required
def admin_manicuristas():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("Debes indicar el nombre.", "danger")
            return redirect(url_for("admin_manicuristas"))

        execute_query("INSERT INTO manicuristas (nombre) VALUES (%s)", (nombre,))
        flash("Manicurista agregada correctamente.", "success")
        return redirect(url_for("admin_manicuristas"))

    manicuristas = fetch_all(
        "SELECT * FROM manicuristas ORDER BY activo DESC, nombre ASC"
    )

    manicurista_editar_id = request.args.get("editar", type=int)
    manicurista_editar = None

    if manicurista_editar_id:
        manicurista_editar = fetch_one(
            "SELECT * FROM manicuristas WHERE id = %s",
            (manicurista_editar_id,),
        )

    return render_template(
        "admin_manicuristas.html",
        manicuristas=manicuristas,
        manicurista_editar=manicurista_editar,
    )


@app.route("/admin/manicuristas/<int:manicurista_id>/editar", methods=["POST"])
@admin_required
def editar_manicurista(manicurista_id):
    manicurista = fetch_one(
        "SELECT * FROM manicuristas WHERE id = %s",
        (manicurista_id,),
    )
    if not manicurista:
        flash("Manicurista no encontrada.", "danger")
        return redirect(url_for("admin_manicuristas"))

    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        flash("Debes indicar el nombre.", "danger")
        return redirect(url_for("admin_manicuristas", editar=manicurista_id))

    execute_query(
        "UPDATE manicuristas SET nombre = %s WHERE id = %s",
        (nombre, manicurista_id),
    )

    flash("Manicurista actualizada correctamente.", "success")
    return redirect(url_for("admin_manicuristas"))


@app.route("/admin/manicuristas/<int:manicurista_id>/toggle", methods=["POST"])
@admin_required
def toggle_manicurista(manicurista_id):
    manicurista = fetch_one(
        "SELECT id, nombre, activo FROM manicuristas WHERE id = %s",
        (manicurista_id,),
    )
    if not manicurista:
        flash("Manicurista no encontrada.", "danger")
        return redirect(url_for("admin_manicuristas"))

    nuevo_estado = not manicurista["activo"]
    execute_query(
        "UPDATE manicuristas SET activo = %s WHERE id = %s",
        (nuevo_estado, manicurista_id),
    )

    if nuevo_estado:
        flash(f"Manicurista '{manicurista['nombre']}' activada.", "success")
    else:
        flash(f"Manicurista '{manicurista['nombre']}' desactivada.", "info")

    return redirect(url_for("admin_manicuristas"))


@app.route("/admin/horarios")
@admin_required
def admin_horarios():
    manicurista_id = request.args.get("manicurista_id", type=int)

    manicuristas = fetch_all(
        "SELECT id, nombre FROM manicuristas ORDER BY activo DESC, nombre ASC"
    )

    selected_manicurista = None
    horarios = []

    if manicurista_id:
        selected_manicurista = fetch_one(
            "SELECT id, nombre FROM manicuristas WHERE id = %s",
            (manicurista_id,),
        )

        horarios = fetch_all(
            """
            SELECT id, manicurista_id, dia_semana, hora_inicio, hora_fin, activo
            FROM horarios_manicurista
            WHERE manicurista_id = %s
            ORDER BY dia_semana ASC
            """,
            (manicurista_id,),
        )

    dias_semana = {
        0: "Lunes",
        1: "Martes",
        2: "Miércoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sábado",
        6: "Domingo",
    }

    return render_template(
        "admin_horarios.html",
        manicuristas=manicuristas,
        manicurista_id=manicurista_id,
        selected_manicurista=selected_manicurista,
        horarios=horarios,
        dias_semana=dias_semana,
    )


@app.route("/admin/horarios/<int:horario_id>/actualizar", methods=["POST"])
@admin_required
def actualizar_horario_manicurista(horario_id):
    horario = fetch_one(
        "SELECT * FROM horarios_manicurista WHERE id = %s",
        (horario_id,),
    )
    if not horario:
        flash("Horario no encontrado.", "danger")
        return redirect(url_for("admin_horarios"))

    hora_inicio = request.form.get("hora_inicio", "").strip()
    hora_fin = request.form.get("hora_fin", "").strip()

    if not hora_inicio or not hora_fin:
        flash("Debes completar hora de inicio y fin.", "danger")
        return redirect(url_for("admin_horarios", manicurista_id=horario["manicurista_id"]))

    try:
        inicio = parse_time(hora_inicio)
        fin = parse_time(hora_fin)
    except ValueError:
        flash("Formato de hora inválido.", "danger")
        return redirect(url_for("admin_horarios", manicurista_id=horario["manicurista_id"]))

    if inicio >= fin:
        flash("La hora de inicio debe ser menor a la hora de fin.", "danger")
        return redirect(url_for("admin_horarios", manicurista_id=horario["manicurista_id"]))

    execute_query(
        """
        UPDATE horarios_manicurista
        SET hora_inicio = %s, hora_fin = %s
        WHERE id = %s
        """,
        (inicio, fin, horario_id),
    )

    flash("Horario actualizado correctamente.", "success")
    return redirect(url_for("admin_horarios", manicurista_id=horario["manicurista_id"]))


@app.route("/admin/horarios/<int:horario_id>/toggle", methods=["POST"])
@admin_required
def toggle_horario_manicurista(horario_id):
    horario = fetch_one(
        "SELECT id, manicurista_id, activo FROM horarios_manicurista WHERE id = %s",
        (horario_id,),
    )
    if not horario:
        flash("Horario no encontrado.", "danger")
        return redirect(url_for("admin_horarios"))

    nuevo_estado = not horario["activo"]

    execute_query(
        "UPDATE horarios_manicurista SET activo = %s WHERE id = %s",
        (nuevo_estado, horario_id),
    )

    if nuevo_estado:
        flash("Día activado correctamente.", "success")
    else:
        flash("Día desactivado correctamente.", "info")

    return redirect(url_for("admin_horarios", manicurista_id=horario["manicurista_id"]))


@app.route("/admin/calendario")
@admin_required
def admin_calendar_events():
    citas = fetch_all(
        """
        SELECT
            c.id,
            c.fecha,
            c.hora_inicio,
            c.hora_fin,
            c.estado,
            u.nombre AS cliente_nombre,
            m.nombre AS manicurista_nombre
        FROM citas c
        JOIN usuarios u ON u.id = c.cliente_id
        JOIN manicuristas m ON m.id = c.manicurista_id
        ORDER BY c.fecha, c.hora_inicio
        """
    )

    events = []
    for cita in citas:
        start_dt = datetime.combine(cita["fecha"], cita["hora_inicio"])
        end_dt = datetime.combine(cita["fecha"], cita["hora_fin"])
        events.append(
            {
                "id": cita["id"],
                "title": f"{cita['cliente_nombre']} - {cita['manicurista_nombre']} ({cita['estado']})",
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            }
        )

    return jsonify(events)


# =========================
# APP STARTUP
# =========================
init_db()


if __name__ == "__main__":
    app.run(debug=True)