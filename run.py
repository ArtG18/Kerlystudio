from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'kerly_studio_2026')

# --- CONEXIÓN A BASE DE DATOS ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return psycopg2.connect(
        host="localhost", database="kerlystudio", user="postgres",
        password="180105.", cursor_factory=RealDictCursor
    )

def execute_query(query, params=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        conn.commit()
        return cur.fetchall() if cur.description else None
    except Exception as e:
        print(f"Error en base de datos: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# --- RUTAS DE CLIENTE ---
@app.route("/")
def home():
    # Obtenemos servicios con sus URL de imagen
    servicios = execute_query("SELECT * FROM servicios WHERE activo = TRUE ORDER BY id ASC")
    return render_template("home.html", servicios=servicios)

@app.route("/reservar_sin_login", methods=["POST"])
def reservar_sin_login():
    f = request.form
    nombre_cliente = f.get('nombre_cliente')
    telefono = f.get('telefono')
    servicio_id = f.get('servicio_id')
    fecha = f.get('fecha')
    hora = f.get('hora')

    servicio_info = execute_query("SELECT nombre FROM servicios WHERE id = %s", (servicio_id,))
    nombre_servicio = servicio_info[0]['nombre'] if servicio_info else "Servicio"

    execute_query("""
        INSERT INTO citas (nombre, telefono, servicio, fecha, hora, estado) 
        VALUES (%s, %s, %s, %s, %s, 'pendiente')
    """, (nombre_cliente, telefono, nombre_servicio, fecha, hora))

    numero_wa = "56959257968"
    mensaje = (f"¡Hola Kerly! ✨ Quiero agendar una cita:\n\n"
               f"👤 *Cliente:* {nombre_cliente}\n"
               f"💅 *Servicio:* {nombre_servicio}\n"
               f"📅 *Fecha:* {fecha}\n"
               f"⏰ *Hora:* {hora}\n\n"
               f"¿Está disponible?")
    
    return redirect(f"https://wa.me/{numero_wa}?text={mensaje.replace(' ', '%20').replace('\n', '%0A')}")

@app.route("/get_horas_ocupadas/<fecha>")
def get_horas_ocupadas(fecha):
    citas = execute_query("SELECT hora FROM citas WHERE fecha = %s AND estado != 'cancelado'", (fecha,))
    horas_ocupadas = [c['hora'] for c in citas] if citas else []
    return jsonify(horas_ocupadas)

# --- RUTAS DE ADMINISTRACIÓN ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form.get('username'), request.form.get('password')
        if u == os.environ.get('ADMIN_EMAIL') and p == os.environ.get('ADMIN_PASSWORD'):
            session.update({'user_id': 1, 'rol': 'admin'})
            return redirect(url_for('admin_dashboard'))
        flash("Credenciales incorrectas")
    return render_template("login.html")

@app.route("/admin")
def admin_dashboard():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    citas = execute_query("SELECT * FROM citas ORDER BY fecha DESC")
    servicios = execute_query("SELECT * FROM servicios ORDER BY id ASC")
    return render_template("admin_dashboard.html", citas=citas, servicios=servicios)

@app.route("/admin/update_servicio", methods=["POST"])
def update_servicio():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    f = request.form
    # Actualización única de servicio con imagen_url
    execute_query("""
        UPDATE servicios 
        SET nombre = %s, descripcion = %s, precio = %s, imagen_url = %s, duracion_min = %s
        WHERE id = %s
    """, (f['nombre'], f['descripcion'], f['precio'], f['imagen_url'], f.get('duracion_min', 60), f['id']))
    flash("Catálogo actualizado.")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_cita/<int:id>")
def delete_cita(id):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    execute_query("DELETE FROM citas WHERE id = %s", (id,))
    flash("Cita eliminada.")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_servicio/<int:id>")
def delete_servicio(id):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    execute_query("DELETE FROM servicios WHERE id = %s", (id,))
    flash("Servicio eliminado.")
    return redirect(url_for('admin_dashboard'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)