from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os

app = Flask(__name__)
# Clave de sesión segura para Kerly Nails Studio
app.secret_key = os.environ.get('SECRET_KEY', 'kerly_studio_2026')

# --- CONEXIÓN A BASE DE DATOS ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    # Respaldo para desarrollo local
    return psycopg2.connect(
        host="localhost",
        database="kerlystudio",
        user="postgres",
        password="180105.",
        cursor_factory=RealDictCursor
    )

def execute_query(query, params=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        conn.commit()
        result = cur.fetchall() if cur.description else None
        return result
    except Exception as e:
        print(f"Error en base de datos: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# --- RUTAS PÚBLICAS (HOME) ---
@app.route("/")
def home():
    # Carga de servicios para mostrar en la web principal
    servicios = execute_query("SELECT * FROM servicios WHERE activo = TRUE ORDER BY id ASC")
    return render_template("home.html", servicios=servicios)

@app.route("/reservar_sin_login", methods=["POST"])
def reservar_sin_login():
    f = request.form
    # Buscamos el nombre del servicio para el mensaje de WhatsApp
    serv = execute_query("SELECT nombre FROM servicios WHERE id = %s", (f['servicio_id'],))
    nombre_s = serv[0]['nombre'] if serv else "Servicio"
    
    # Registro de la cita en la base de datos
    execute_query("""
        INSERT INTO citas (nombre, telefono, servicio, fecha, hora, estado) 
        VALUES (%s, %s, %s, %s, %s, 'pendiente')
    """, (f['nombre_cliente'], f['telefono'], nombre_s, f['fecha'], f['hora']))

    # Redirección al WhatsApp oficial
    numero_wa = "56959257968"
    msg = f"Hola Kerly! Reservé {nombre_s} para el {f['fecha']} a las {f['hora']}."
    return redirect(f"https://wa.me/{numero_wa}?text={msg.replace(' ', '%20')}")

# --- ADMINISTRACIÓN (LOGIN Y PANEL) ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email_ingresado = request.form.get('username')
        pass_ingresada = request.form.get('password')
        
        # Validación mediante variables de entorno de Render
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_pass = os.environ.get('ADMIN_PASSWORD')
        
        if email_ingresado == admin_email and pass_ingresada == admin_pass:
            session.update({'user_id': 1, 'rol': 'admin'})
            return redirect(url_for('admin_dashboard'))
        
        flash("Correo o contraseña de administradora incorrectos.")
    return render_template("login.html")

@app.route("/admin")
def admin_dashboard():
    if session.get('rol') != 'admin': 
        return redirect(url_for('login'))
        
    try:
        citas = execute_query("SELECT * FROM citas ORDER BY fecha DESC")
        servicios = execute_query("SELECT * FROM servicios ORDER BY id ASC")
        

        if citas and len(citas) > 0:
            print(f"DEBUG - Columnas encontradas en citas: {citas[0].keys()}")
            
        return render_template("admin_dashboard.html", citas=citas, servicios=servicios)
    except Exception as e:
        print(f"Error detectado: {e}")
        return f"Error en columnas: {e}. Revisa los logs de Render."

# --- ACCIONES DEL PANEL ---

@app.route("/admin/update_servicio", methods=["POST"])
def update_servicio():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    f = request.form
    # Actualiza nombre, descripción, precio e imagen (URL de ImgBB)
    execute_query("""
        UPDATE servicios 
        SET nombre = %s, descripcion = %s, precio = %s, imagen_url = %s 
        WHERE id = %s
    """, (f['nombre'], f['descripcion'], f['precio'], f['imagen_url'], f['id']))
    
    flash(f"Servicio '{f['nombre']}' actualizado correctamente.")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/update_cita/<int:id>/<estado>")
def update_cita(id, estado):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    # Permite confirmar o cancelar citas desde la tabla
    execute_query("UPDATE citas SET estado = %s WHERE id = %s", (estado, id))
    flash(f"Cita marcada como {estado}.")
    return redirect(url_for('admin_dashboard'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)