from flask import Flask, render_template, request, redirect, session, url_for, flash
import psycopg2
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-render")

# ---------------- DATABASE ----------------

def get_connection():
    database_url = os.environ["DATABASE_URL"]

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return psycopg2.connect(database_url, sslmode="require")


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS citas (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(100),
        telefono VARCHAR(50),
        fecha DATE,
        hora TIME,
        servicio TEXT,
        manicurista VARCHAR(100),
        estado VARCHAR(20) DEFAULT 'Pendiente'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """)

    cursor.execute("SELECT 1 FROM usuarios WHERE username = %s", ("admin",))
    if not cursor.fetchone():
        admin_password = os.environ.get("ADMIN_PASSWORD", "K2026$")
        password_hash = generate_password_hash(admin_password)
        cursor.execute(
            "INSERT INTO usuarios (username, password_hash) VALUES (%s, %s)",
            ("admin", password_hash)
        )

    conn.commit()
    cursor.close()
    conn.close()


init_db()

# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("home.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        user = request.form["username"].strip()
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM usuarios WHERE username = %s", (user,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result and check_password_hash(result[0], password):
            session["user"] = user
            return redirect(url_for("dashboard"))
        else:
            flash("Usuario o contraseña incorrectos", "danger")

    return render_template("login.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente", "success")
    return redirect("/")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        accion = request.form.get("accion")

        if accion == "agendar":
            nombre = request.form["nombre"].strip()
            telefono = request.form["telefono"].strip()
            fecha = request.form["fecha"]
            hora = request.form["hora"]
            manicurista = request.form["manicurista"]
            servicios = request.form.getlist("servicios")
            servicio_final = ", ".join(servicios)

            cursor.execute("""
            SELECT COUNT(*) FROM citas
            WHERE fecha = %s AND hora = %s AND manicurista = %s AND estado = 'Confirmada'
            """, (fecha, hora, manicurista))

            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                INSERT INTO citas (nombre, telefono, fecha, hora, servicio, manicurista)
                VALUES (%s, %s, %s, %s, %s, %s)
                """, (nombre, telefono, fecha, hora, servicio_final, manicurista))
                conn.commit()
                flash("Cita agendada correctamente", "success")
            else:
                flash("Ese horario ya está ocupado por una cita confirmada", "warning")

        elif accion == "confirmar":
            cursor.execute(
                "UPDATE citas SET estado = 'Confirmada' WHERE id = %s",
                (request.form["cita_id"],)
            )
            conn.commit()
            flash("Cita confirmada correctamente", "success")

        elif accion == "cancelar":
            cursor.execute(
                "UPDATE citas SET estado = 'Cancelada' WHERE id = %s",
                (request.form["cita_id"],)
            )
            conn.commit()
            flash("Cita cancelada correctamente", "warning")

        elif accion == "eliminar":
            cursor.execute(
                "DELETE FROM citas WHERE id = %s",
                (request.form["cita_id"],)
            )
            conn.commit()
            flash("Cita eliminada correctamente", "danger")

    cursor.execute("""
    SELECT id, nombre, telefono, fecha, hora, servicio, manicurista, estado
    FROM citas
    ORDER BY fecha, hora
    """)
    citas = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM citas WHERE fecha = CURRENT_DATE")
    citas_hoy = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM citas WHERE estado = 'Confirmada'")
    confirmadas = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM citas WHERE estado = 'Cancelada'")
    canceladas = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    eventos = []
    for c in citas:
        eventos.append({
            "title": f"{c[1]} - {c[6]}",
            "start": f"{c[3]}T{c[4]}",
            "color": "#28a745" if c[7] == "Confirmada"
                     else "#ffc107" if c[7] == "Pendiente"
                     else "#dc3545"
        })

    return render_template(
        "dashboard.html",
        citas=citas,
        citas_hoy=citas_hoy,
        confirmadas=confirmadas,
        canceladas=canceladas,
        eventos=json.dumps(eventos)
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)