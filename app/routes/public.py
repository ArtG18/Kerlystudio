from flask import Blueprint, render_template
from app.db import fetch_all

public_bp = Blueprint("public", __name__)

# =========================
# HOME
# =========================
@public_bp.route("/")
def home():
    servicios = fetch_all("""
        SELECT id, nombre, descripcion, precio, categoria
        FROM servicios
        WHERE activo = TRUE
        LIMIT 6
    """)

    return render_template("home.html", servicios=servicios)


# =========================
# CATÁLOGO
# =========================
@public_bp.route("/catalogo")
def catalogo():
    servicios_lista = fetch_all("""
        SELECT id, nombre, descripcion, duracion_min, precio, categoria
        FROM servicios
        WHERE activo = TRUE
        ORDER BY categoria ASC, nombre ASC
    """)

    servicios_agrupados = {}

    for s in servicios_lista:
        servicios_agrupados.setdefault(s["categoria"], []).append(s)

    return render_template("catalogo.html", servicios_agrupados=servicios_agrupados)