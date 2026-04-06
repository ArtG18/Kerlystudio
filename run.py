from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'kerly_studio_2026')

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
    cur.execute(query, params)
    conn.commit()
    result = cur.fetchall() if cur.description else None
    cur.close()
    conn.close()
    return result

@app.route("/")
def home():
    servicios = execute_query("SELECT * FROM servicios WHERE activo = TRUE ORDER BY id ASC")
    return render_template("home.html", servicios=servicios)

@app.route("/reservar_sin_login", methods=["POST"])
def reservar_sin_login():
    f = request.form
    try:
        fecha_sel = datetime.strptime(f['fecha'], '%Y-%m-%d').date()
        hora_sel = datetime.strptime(f['hora'], '%H:%M').time()
    except:
        flash("Error en el formato de fecha u hora.")
        return redirect(url_for('home'))
        
    ahora = datetime.now()
    dia_semana = fecha_sel.weekday() 

    if fecha_sel < ahora.date():
        flash("No puedes agendar en una fecha que ya pasó.")
        return redirect(url_for('home'))

    es_valido = False
    if 0 <= dia_semana <= 4: # L-V (09:30 - 19:30)
        if datetime.strptime("09:30", "%H:%M").time() <= hora_sel <= datetime.strptime("19:30", "%H:%M").time():
            es_valido = True
    elif dia_semana == 5: # Sábado (09:30 - 14:00)
        if datetime.strptime("09:30", "%H:%M").time() <= hora_sel <= datetime.strptime("14:00", "%H:%M").time():
            es_valido = True

    if not es_valido:
        flash("El horario seleccionado está fuera de nuestra jornada laboral.")
        return redirect(url_for('home'))

    serv = execute_query("SELECT nombre FROM servicios WHERE id = %s", (f['servicio_id'],))
    nombre_s = serv[0]['nombre'] if serv else "Servicio"
    
    execute_query("INSERT INTO citas (nombre, telefono, servicio, fecha, hora, estado) VALUES (%s, %s, %s, %s, %s, 'pendiente')",
                  (f['nombre_cliente'], f['telefono'], nombre_s, f['fecha'], f['hora']))

    msg = f"Hola Kerly! Reservé {nombre_s} para el {f['fecha']} a las {f['hora']}. Mi nombre: {f['nombre_cliente']}."
    return redirect(f"https://wa.me/56959257968?text={msg.replace(' ', '%20')}")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = execute_query("SELECT * FROM usuarios WHERE username = %s", (request.form['username'],))
        if user and check_password_hash(user[0]['password_hash'], request.form['password']):
            session.update({'user_id': user[0]['id'], 'rol': user[0]['rol']})
            return redirect(url_for('admin_dashboard'))
        flash("Credenciales incorrectas")
    return render_template("login.html")

@app.route("/admin")
def admin_dashboard():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    return render_template("admin_dashboard.html", 
                           citas=execute_query("SELECT * FROM citas ORDER BY fecha DESC"),
                           servicios=execute_query("SELECT * FROM servicios ORDER BY id ASC"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)