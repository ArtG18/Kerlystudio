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
        print(f"Error: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# --- RUTAS PÚBLICAS ---
@app.route("/")
def home():
    servicios = execute_query("SELECT * FROM servicios WHERE activo = TRUE ORDER BY id ASC")
    return render_template("home.html", servicios=servicios)

@app.route("/reservar_sin_login", methods=["POST"])
def reservar_sin_login():
    f = request.form
    fecha_sel = datetime.strptime(f['fecha'], '%Y-%m-%d').date()
    hora_sel = datetime.strptime(f['hora'], '%H:%M').time()
    
    # Registro y redirección a WhatsApp oficial: 56959257968
    serv = execute_query("SELECT nombre FROM servicios WHERE id = %s", (f['servicio_id'],))
    nombre_s = serv[0]['nombre'] if serv else "Servicio"
    
    execute_query("INSERT INTO citas (nombre, telefono, servicio, fecha, hora, estado) VALUES (%s, %s, %s, %s, %s, 'pendiente')",
                  (f['nombre_cliente'], f['telefono'], nombre_s, f['fecha'], f['hora']))

    numero_wa = "56959257968"
    msg = f"Hola Kerly! Reservé {nombre_s} para el {f['fecha']} a las {f['hora']}."
    return redirect(f"https://wa.me/{numero_wa}?text={msg.replace(' ', '%20')}")

# --- ADMINISTRACIÓN (LOGIN TEMPORAL) ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        form_user = request.form.get('username')
        form_pass = request.form.get('password')
        
        # Consultamos usando el nuevo nombre de columna
        try:
            user = execute_query("SELECT * FROM usuarios WHERE usuario_admin = %s", (form_user,))
            
            if user and len(user) > 0:
                # Comparación directa (temporal)
                if user[0]['password_hash'] == form_pass:
                    session.update({'user_id': user[0]['id'], 'rol': user[0]['rol']})
                    return redirect(url_for('admin_dashboard'))
            
            flash("Usuario o contraseña incorrectos.")
        except Exception as e:
            flash(f"Error de sistema: {str(e)}")
            
    return render_template("login.html")

@app.route("/admin")
def admin_dashboard():
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