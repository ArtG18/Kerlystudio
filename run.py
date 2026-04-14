from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
# Clave secreta para manejar sesiones de Kerly Nails Studio
app.secret_key = os.environ.get('SECRET_KEY', 'kerly_studio_2026')

# --- CONEXIÓN A BASE DE DATOS ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    # Configuración local por si falla la de Render
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
        print(f"Error en la consulta: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# --- RUTAS PÚBLICAS ---
@app.route("/")
def home():
    # Obtiene servicios activos para Kerly Nails Studio
    servicios = execute_query("SELECT * FROM servicios WHERE activo = TRUE ORDER BY id ASC")
    return render_template("home.html", servicios=servicios)

@app.route("/reservar_sin_login", methods=["POST"])
def reservar_sin_login():
    f = request.form
    fecha_sel = datetime.strptime(f['fecha'], '%Y-%m-%d').date()
    hora_sel = datetime.strptime(f['hora'], '%H:%M').time()
    ahora = datetime.now()
    dia_semana = fecha_sel.weekday() 

    # VALIDACIÓN: No fechas pasadas
    if fecha_sel < ahora.date():
        flash("No puedes agendar en una fecha que ya pasó.")
        return redirect(url_for('home'))

    # VALIDACIÓN: Horarios Laborales de Kerly Nails Studio
    es_valido = False
    if 0 <= dia_semana <= 4: # Lunes a Viernes: 09:30 a 19:30
        if datetime.strptime("09:30", "%H:%M").time() <= hora_sel <= datetime.strptime("19:30", "%H:%M").time():
            es_valido = True
    elif dia_semana == 5: # Sábado: 09:30 a 14:00
        if datetime.strptime("09:30", "%H:%M").time() <= hora_sel <= datetime.strptime("14:00", "%H:%M").time():
            es_valido = True

    if not es_valido:
        flash("El estudio está cerrado en ese horario.")
        return redirect(url_for('home'))

    serv = execute_query("SELECT nombre FROM servicios WHERE id = %s", (f['servicio_id'],))
    nombre_s = serv[0]['nombre'] if serv else "Servicio"
    
    # Registro de la cita en la base de datos
    execute_query("INSERT INTO citas (nombre, telefono, servicio, fecha, hora, estado) VALUES (%s, %s, %s, %s, %s, 'pendiente')",
                  (f['nombre_cliente'], f['telefono'], nombre_s, f['fecha'], f['hora']))

    # WhatsApp automático al número oficial
    numero_wa = "56959257968"
    msg = f"Hola Kerly! Reservé {nombre_s} para el {f['fecha']} a las {f['hora']}. Mi nombre: {f['nombre_cliente']}."
    return redirect(f"https://wa.me/{numero_wa}?text={msg.replace(' ', '%20')}")

# --- ADMINISTRACIÓN ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # CORRECCIÓN: Consulta limpia sin comillas dobles en username
        user = execute_query("SELECT * FROM usuarios WHERE username = %s", (request.form['username'],))
        
        if user and len(user) > 0:
            if check_password_hash(user[0]['password_hash'], request.form['password']):
                session.update({'user_id': user[0]['id'], 'rol': user[0]['rol']})
                return redirect(url_for('admin_dashboard'))
        
        flash("Usuario o contraseña incorrectos.")
    return render_template("login.html")

@app.route("/admin")
def admin_dashboard():
    # Solo permite acceso a administradores
    if session.get('rol') != 'admin': 
        return redirect(url_for('login'))
        
    return render_template("admin_dashboard.html", 
                           citas=execute_query("SELECT * FROM citas ORDER BY fecha DESC"),
                           servicios=execute_query("SELECT * FROM servicios ORDER BY id ASC"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)