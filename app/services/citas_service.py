from app.db import fetch_all, fetch_one, execute_query

# =========================
# SERVICIOS
# =========================
def obtener_servicios_activos():
    return fetch_all("""
        SELECT id, nombre, duracion_min, precio, categoria
        FROM servicios
        WHERE activo = TRUE
        ORDER BY categoria, nombre
    """)

# =========================
# CREAR CITA
# =========================
def crear_cita(cliente_id, manicurista_id, fecha, hora_inicio, hora_fin, notas):
    return execute_query("""
        INSERT INTO citas (cliente_id, manicurista_id, fecha, hora_inicio, hora_fin, estado, notas)
        VALUES (%s, %s, %s, %s, %s, 'pendiente', %s)
        RETURNING id
    """, (cliente_id, manicurista_id, fecha, hora_inicio, hora_fin, notas), fetchone=True)