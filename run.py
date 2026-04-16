from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
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
        print(f"Error: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# --- RUTAS ---
@app.route("/")
def home():
    servicios = execute_query("SELECT * FROM servicios WHERE activo = TRUE ORDER BY id ASC")
    return render_template("home.html", servicios=servicios)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form.get('username'), request.form.get('password')
        if u == os.environ.get('ADMIN_EMAIL') and p == os.environ.get('ADMIN_PASSWORD'):
            session.update({'user_id': 1, 'rol': 'admin'})
            return redirect(url_for('admin_dashboard'))
        flash("Credenciales incorrectas")
    return render_template("login.html")

@app.route("/reservar_sin_login", methods=["POST"])
def reservar_sin_login():
    f = request.form
    nombre_cliente = f.get('nombre_cliente')
    telefono = f.get('telefono')
    servicio_id = f.get('servicio_id')
    fecha = f.get('fecha')
    hora = f.get('hora')

    # Obtenemos el nombre del servicio para el mensaje
    servicio_info = execute_query("SELECT nombre FROM servicios WHERE id = %s", (servicio_id,))
    nombre_servicio = servicio_info[0]['nombre'] if servicio_info else "Servicio"

    # 1. Guardar en la base de datos
    execute_query("""
        INSERT INTO citas (nombre, telefono, servicio, fecha, hora, estado) 
        VALUES (%s, %s, %s, %s, %s, 'pendiente')
    """, (nombre_cliente, telefono, nombre_servicio, fecha, hora))

    # 2. Redirigir a WhatsApp con mensaje automático
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
    # Solo traemos horas de citas que estén 'confirmadas' o 'pendientes'
    citas = execute_query("SELECT hora FROM citas WHERE fecha = %s AND estado != 'cancelado'", (fecha,))
    horas_ocupadas = [c['hora'] for c in citas]
    return jsonify(horas_ocupadas)

@app.route("/admin")
def admin_dashboard():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    # Consulta segura: si 'hora' no existe, no romperá el sitio
    citas = execute_query("SELECT * FROM citas ORDER BY fecha DESC")
    servicios = execute_query("SELECT * FROM servicios ORDER BY id ASC")
    return render_template("admin_dashboard.html", citas=citas, servicios=servicios)

# --- ACCIONES CITAS ---
@app.route("/admin/update_servicio", methods=["POST"])
def update_servicio():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    f = request.form
    # Usamos 'imagen_url' que es la columna que confirmamos en tu tabla
    execute_query("""
        UPDATE servicios 
        SET nombre = %s, descripcion = %s, precio = %s, imagen_url = %s 
        WHERE id = %s
    """, (f['nombre'], f['descripcion'], f['precio'], f['imagen_url'], f['id']))
    
    flash("Servicio actualizado con éxito en el catálogo.")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_cita/<int:id>")
def delete_cita(id):
    execute_query("DELETE FROM citas WHERE id = %s", (id,))
    flash("Cita eliminada.")
    return redirect(url_for('admin_dashboard'))

# --- ACCIONES CATÁLOGO ---
@app.route("/admin/update_servicio", methods=["POST"])
def update_servicio():
    f = request.form
    execute_query("""
        UPDATE servicios SET nombre=%s, descripcion=%s, precio=%s, imagen_url=%s 
        WHERE id=%s""", (f['nombre'], f['descripcion'], f['precio'], f['imagen_url'], f['id']))
    flash("Servicio actualizado en el Home.")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete_servicio/<int:id>")
def delete_servicio(id):
    execute_query("DELETE FROM servicios WHERE id = %s", (id,))
    flash("Servicio eliminado del catálogo.")
    return redirect(url_for('admin_dashboard'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)