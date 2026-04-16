from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
# Clave de sesión para Kerly Nails Studio
app.secret_key = os.environ.get('SECRET_KEY', 'kerly_studio_2026')

# --- CONEXIÓN A BASE DE DATOS ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    # Configuración local de respaldo
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
        print(f"Error en consulta: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# --- RUTAS PÚBLICAS ---
@app.route("/")
def home():
    # Carga de servicios activos para la vista principal
    servicios = execute_query("SELECT * FROM servicios WHERE activo = TRUE ORDER BY id ASC")
    return render_template("home.html", servicios=servicios)

@app.route("/reservar_sin_login", methods=["POST"])
def reservar_sin_login():
    f = request.form
    fecha_sel = datetime.strptime(f['fecha'], '%Y-%m-%d').date()
    hora_sel = datetime.strptime(f['hora'], '%H:%M').time()
    
    # Obtener nombre del servicio para el mensaje
    serv = execute_query("SELECT nombre FROM servicios WHERE id = %s", (f['servicio_id'],))
    nombre_s = serv[0]['nombre'] if serv else "Servicio"
    
    # Registro en la tabla de citas
    execute_query("INSERT INTO citas (nombre, telefono, servicio, fecha, hora, estado) VALUES (%s, %s, %s, %s, %s, 'pendiente')",
                  (f['nombre_cliente'], f['telefono'], nombre_s, f['fecha'], f['hora']))

    # Redirección al WhatsApp oficial: 56959257968
    numero_wa = "56959257968"
    msg = f"Hola Kerly! Reservé {nombre_s} para el {f['fecha']} a las {f['hora']}."
    return redirect(f"https://wa.me/{numero_wa}?text={msg.replace(' ', '%20')}")

# --- ADMINISTRACIÓN ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get('username')
        p = request.form.get('password')
        
        # Usamos los nombres exactos de tu captura de pantalla
        res = execute_query("SELECT * FROM acceso_admin WHERE login_user = %s", (u,))
        
        if res and len(res) > 0:
            # Comparamos con 'login_pass' que es el nombre en tu imagen
            if res[0]['login_pass'] == p:
                session.update({'user_id': res[0]['id'], 'rol': res[0]['rol']})
                return redirect(url_for('admin_dashboard'))
        
        flash("Credenciales incorrectas")
    return render_template("login.html")

@app.route("/admin")
def admin_dashboard():
    # Verificación de rol administrativo
    if session.get('rol') != 'admin': 
        return redirect(url_for('login'))
        
    # Carga de datos para el panel de gestión
    citas = execute_query("SELECT * FROM citas ORDER BY fecha DESC")
    servicios = execute_query("SELECT * FROM servicios ORDER BY id ASC")
    return render_template("admin_dashboard.html", citas=citas, servicios=servicios)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)