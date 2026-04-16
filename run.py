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
    serv = execute_query("SELECT nombre FROM servicios WHERE id = %s", (f['servicio_id'],))
    nombre_s = serv[0]['nombre'] if serv else "Servicio"
    
    execute_query("INSERT INTO citas (nombre, telefono, servicio, fecha, hora, estado) VALUES (%s, %s, %s, %s, %s, 'pendiente')",
                  (f['nombre_cliente'], f['telefono'], nombre_s, f['fecha'], f['hora']))

    numero_wa = "56959257968"
    msg = f"Hola Kerly! Reservé {nombre_s} para el {f['fecha']} a las {f['hora']}."
    return redirect(f"https://wa.me/{numero_wa}?text={msg.replace(' ', '%20')}")

# --- ADMINISTRACIÓN (LOGIN POR VARIABLES DE ENTORNO) ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email_ingresado = request.form.get('username')
        pass_ingresada = request.form.get('password')
        
        # Obtenemos los valores reales de Render (tus capturas)
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
        
    return render_template("admin_dashboard.html", 
                           citas=execute_query("SELECT * FROM citas ORDER BY fecha DESC"),
                           servicios=execute_query("SELECT * FROM servicios ORDER BY id ASC"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)