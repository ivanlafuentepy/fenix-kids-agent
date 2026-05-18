"""
Genera la página HTML de follow-up para pruebas del 16 de mayo 2026.
Mensajes personalizados por edad del niño, con links wa.me listos para enviar.
"""

import urllib.parse
import json
from datetime import datetime

# Datos agrupados por teléfono (solo PRESENTE=true)
FAMILIAS = [
    {
        "padre": "Marco",
        "apellido": "Mernes",
        "tel": "595981614009",
        "hijos": [{"nombre": "Piero", "edad": "4,5", "rango": "3-5"}],
        "hora": "11:00"
    },
    # Genesis Yegros (595981130388) — INSCRIPTO, excluida
    {
        "padre": "Fabiana",
        "apellido": "Aguilera",
        "tel": "595985765996",
        "hijos": [
            {"nombre": "Amanda Milena", "edad": "4,10", "rango": "3-5"},
            {"nombre": "Alana", "edad": "4,10", "rango": "3-5"}
        ],
        "hora": "11:00"
    },
    # Janeth Paredes de Niz (595971886648) — INSCRIPTO, excluida
    {
        "padre": "Lee Jun",
        "apellido": "Yob",
        "tel": "595992247697",
        "hijos": [{"nombre": "Max Ki Bae", "edad": "7,8", "rango": "6-8"}],
        "hora": "15:30"
    },
    {
        "padre": "Debora",
        "apellido": "Aguiar",
        "tel": "595971115636",
        "hijos": [
            {"nombre": "Samuel", "edad": "5,5", "rango": "3-5"},
            {"nombre": "Fabrizio", "edad": "10,4", "rango": "9-12"}
        ],
        "hora": "9:30"
    },
    {
        "padre": "Alejandra",
        "apellido": "Alvarenga",
        "tel": "595961739906",
        "hijos": [{"nombre": "Ian José", "edad": "5,10", "rango": "3-5"}],
        "hora": "15:30"
    },
    {
        "padre": "Juan",
        "apellido": "Enrique Núñez",
        "tel": "595984417866",
        "hijos": [
            {"nombre": "Marcelo", "edad": "4,11", "rango": "3-5"},
            {"nombre": "Mateo", "edad": "3,11", "rango": "3-5"}
        ],
        "hora": "15:30"
    },
    {
        "padre": "César",
        "apellido": "Mendez",
        "tel": "595985296645",
        "hijos": [{"nombre": "César Emanuel", "edad": "8,4", "rango": "6-8"}],
        "hora": "15:30"
    },
    # Beatriz Benitez (595984842052) — INSCRIPTO, excluida
    {
        "padre": "Milagros",
        "apellido": "Maldonado",
        "tel": "595971462496",
        "hijos": [{"nombre": "Joaquín Eligio", "edad": "5,11", "rango": "3-5"}],
        "hora": "9:30"
    },
    {
        "padre": "Roque",
        "apellido": "Ojeda",
        "tel": "595971676325",
        "hijos": [{"nombre": "Facundo", "edad": "5,1", "rango": "3-5"}],
        "hora": "11:00"
    },
    # Biviana Bazán (595973686713) — INSCRIPTO, excluida
    {
        "padre": "Victor",
        "apellido": "Martinez",
        "tel": "595981634024",
        "hijos": [
            {"nombre": "Amira", "edad": "7,11", "rango": "6-8"},
            {"nombre": "Eladio Andrés", "edad": "3,11", "rango": "3-5"}
        ],
        "hora": "15:30"
    },
    {
        "padre": "Gilda",
        "apellido": "Noguera",
        "tel": "595981410283",
        "hijos": [{"nombre": "Sebastián", "edad": "", "rango": "general"}],
        "hora": "15:30"
    },
    # Erica Bogado (595961550099) — INSCRIPTO, excluida
    {
        "padre": "Solange",
        "apellido": "Recalde",
        "tel": "595991278888",
        "hijos": [
            {"nombre": "Hannah", "edad": "9,6", "rango": "9-12"},
            {"nombre": "Matheo", "edad": "4,1", "rango": "3-5"}
        ],
        "hora": "15:30"
    },
    {
        "padre": "Soraya",
        "apellido": "Chamorro",
        "tel": "595973564545",
        "hijos": [{"nombre": "Mateo", "edad": "9,9", "rango": "9-12"}],
        "hora": "11:00"
    },
]


def edad_texto(edad_str):
    """Convierte '4,5' a '4 años'."""
    if not edad_str:
        return ""
    partes = edad_str.split(",")
    anios = int(partes[0])
    return f"{anios} años"


def generar_mensaje(familia):
    """Genera mensaje personalizado según edad(es) del/los hijo(s)."""
    padre = familia["padre"]
    hijos = familia["hijos"]

    # Determinar nombres de hijos para el mensaje
    if len(hijos) == 1:
        h = hijos[0]
        nombre_hijo = h["nombre"].split()[0]  # Solo primer nombre
        rango = h["rango"]
        multi = False
    else:
        nombres = [h["nombre"].split()[0] for h in hijos]
        nombre_hijo = " y ".join(nombres)
        # Determinar rango predominante o mixto
        rangos = set(h["rango"] for h in hijos)
        if len(rangos) == 1:
            rango = rangos.pop()
        else:
            rango = "mixto"
        multi = True

    # Pregunta abierta según cantidad de hijos
    if multi:
        pregunta = f"Contame, ¿qué tal se sintieron {nombre_hijo} después del entrenamiento? ¿Qué dijeron? ¿Les gustó?"
    else:
        pregunta = f"Contame, ¿qué tal se sintió {nombre_hijo} después del entrenamiento? ¿Qué dijo? ¿Le gustó?"

    # Consejo personalizado por edad (voz de profe, desde la experiencia)
    consejos = {
        "3-5": (
            f"Te aconsejo vivamente que sigas haciendo este tipo de actividad con {nombre_hijo} al aire libre. "
            f"Cada vez que puedas, {'llevalos' if multi else f'llevá a {nombre_hijo}'} al parque, {'haceles' if multi else 'hacele'} trepar árboles, subir murallas, hacer cosas que {'les' if multi else 'le'} desafíen. "
            f"A esta edad eso {'les' if multi else 'le'} desarrolla muchísimo la coordinación, la confianza y la autoestima. "
            f"La valentía se construye desde chiquitos superando desafíos reales."
        ),
        "6-8": (
            f"Te aconsejo vivamente que sigas fomentando este tipo de actividad con {nombre_hijo}. "
            f"A esta edad {'necesitan' if multi else 'necesita'} desafíos físicos reales: trepar, saltar, correr, caerse y levantarse. "
            f"Eso {'les' if multi else 'le'} desarrolla la confianza, la independencia y la capacidad de superar miedos. "
            f"Es la mejor forma de canalizar toda esa energía de forma positiva."
        ),
        "9-12": (
            f"Te aconsejo vivamente que sigas fomentando este tipo de actividad con {nombre_hijo}. "
            f"A esta edad el entrenamiento funcional {'les' if multi else 'le'} desarrolla disciplina, fuerza mental y liderazgo. "
            f"Es la etapa perfecta para construir hábitos saludables, desconectar de las pantallas y fortalecer la autoestima a través del esfuerzo real. "
            f"Lo que {'construyan' if multi else 'construya'} ahora {'les' if multi else 'le'} queda para siempre."
        ),
        "mixto": (
            f"Te aconsejo vivamente que sigas haciendo este tipo de actividades con ellos. "
            f"Cada uno a su edad necesita cosas distintas: los más chiquitos desarrollan coordinación y confianza a través del juego y los desafíos físicos, "
            f"y los más grandes fortalecen la disciplina, la fuerza mental y hábitos saludables. "
            f"La valentía y la autoestima se construyen superando desafíos reales, y eso es exactamente lo que hacemos en FENIX."
        ),
        "general": (
            f"Te aconsejo vivamente que sigas fomentando este tipo de actividad con {nombre_hijo}. "
            f"El entrenamiento funcional al aire libre desarrolla la confianza, la coordinación y la autoestima de una forma que ninguna otra actividad logra. "
            f"La valentía se construye desde chicos superando desafíos reales."
        ),
    }

    consejo = consejos.get(rango, consejos["general"])

    msg = (
        f"Hola {padre} 😊 Soy Iván, profe de FENIX Kids.\n\n"
        f"Quería agradecerte por haber venido a probar el sábado con {nombre_hijo}. "
        f"{pregunta}\n\n"
        f"{consejo}\n\n"
        f"Te cuento que estoy teniendo mucha demanda y la promoción que tenemos de 12 clases a 750.000 guaraníes sin matrícula en estos días ya estaré cerrando.\n\n"
        f"Si te interesa asegurar el lugar de {nombre_hijo} con esa promo, avisame y te paso todos los datos 🙌\n\n"
        f"P.D: Las 12 clases que comprás con el paquete son sin vencimiento, solo cuando venís se descuentan 🎁"
    )
    return msg


def generar_html():
    """Genera la página HTML completa."""
    cards_html = ""
    for i, fam in enumerate(FAMILIAS):
        msg = generar_mensaje(fam)
        wa_link = f"https://wa.me/{fam['tel']}?text={urllib.parse.quote(msg)}"

        hijos_info = []
        for h in fam["hijos"]:
            edad = edad_texto(h["edad"])
            badge_class = {
                "3-5": "badge-green",
                "6-8": "badge-blue",
                "9-12": "badge-orange",
                "general": "badge-gray",
            }.get(h["rango"], "badge-gray")
            hijos_info.append(
                f'<span class="hijo">{h["nombre"]} '
                f'<span class="badge {badge_class}">{edad or "s/edad"}</span></span>'
            )

        hijos_html = " &bull; ".join(hijos_info)

        cards_html += f"""
        <div class="card">
            <div class="card-header">
                <div class="padre-name">{fam["padre"]} {fam["apellido"]}</div>
                <div class="turno">Turno {fam["hora"]}</div>
            </div>
            <div class="hijos">{hijos_html}</div>
            <div class="telefono">+{fam["tel"]}</div>
            <div class="mensaje-preview">{msg[:150]}...</div>
            <a href="{wa_link}" target="_blank" class="btn-whatsapp">
                Enviar mensaje por WhatsApp
            </a>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FENIX Kids — Follow-up Prueba 16 Mayo</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 20px;
            max-width: 800px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid #ff6b00;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #ff6b00;
            font-size: 1.8em;
            margin-bottom: 8px;
        }}
        .header p {{
            color: #888;
            font-size: 0.95em;
        }}
        .stats {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin: 20px 0;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-num {{
            font-size: 2em;
            font-weight: bold;
            color: #ff6b00;
        }}
        .stat-label {{
            font-size: 0.8em;
            color: #888;
        }}
        .card {{
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            transition: border-color 0.2s;
        }}
        .card:hover {{
            border-color: #ff6b00;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .padre-name {{
            font-size: 1.2em;
            font-weight: 600;
            color: #fff;
        }}
        .turno {{
            background: #222;
            color: #ff6b00;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8em;
        }}
        .hijos {{
            margin-bottom: 8px;
        }}
        .hijo {{
            margin-right: 10px;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.75em;
            font-weight: 600;
        }}
        .badge-green {{ background: #1a3a1a; color: #4caf50; }}
        .badge-blue {{ background: #1a2a3a; color: #42a5f5; }}
        .badge-orange {{ background: #3a2a1a; color: #ff9800; }}
        .badge-gray {{ background: #2a2a2a; color: #999; }}
        .telefono {{
            color: #666;
            font-size: 0.85em;
            margin-bottom: 10px;
        }}
        .mensaje-preview {{
            background: #111;
            border-left: 3px solid #333;
            padding: 10px 14px;
            font-size: 0.85em;
            color: #999;
            margin-bottom: 14px;
            border-radius: 0 8px 8px 0;
            line-height: 1.4;
        }}
        .btn-whatsapp {{
            display: block;
            text-align: center;
            background: #25d366;
            color: #fff;
            text-decoration: none;
            padding: 14px;
            border-radius: 10px;
            font-weight: 600;
            font-size: 1em;
            transition: background 0.2s;
        }}
        .btn-whatsapp:hover {{
            background: #1ea952;
        }}
        .legend {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
            font-size: 0.85em;
        }}
        .legend span {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }}
        .dot-green {{ background: #4caf50; }}
        .dot-blue {{ background: #42a5f5; }}
        .dot-orange {{ background: #ff9800; }}
        .sent {{
            opacity: 0.7;
        }}
        .sent .btn-whatsapp {{
            background: #1a8a3e;
        }}
        .sent .btn-whatsapp::after {{
            content: ' (enviado)';
        }}
        .mark-sent {{
            display: block;
            text-align: center;
            margin-top: 8px;
            color: #666;
            font-size: 0.8em;
            cursor: pointer;
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>FENIX Kids</h1>
        <p>Follow-up — Prueba Sábado 16 de Mayo 2026</p>
        <div class="stats">
            <div class="stat">
                <div class="stat-num">{len(FAMILIAS)}</div>
                <div class="stat-label">Familias</div>
            </div>
            <div class="stat">
                <div class="stat-num">{sum(len(f['hijos']) for f in FAMILIAS)}</div>
                <div class="stat-label">Niños</div>
            </div>
        </div>
    </div>

    <div class="legend">
        <span><span class="dot dot-green"></span> 3-5 años</span>
        <span><span class="dot dot-blue"></span> 6-8 años</span>
        <span><span class="dot dot-orange"></span> 9-12 años</span>
    </div>

    {cards_html}

    <script>
        // Marcar como enviado (persiste en localStorage)
        const sentKey = 'fenix-fu-16mayo-sent';
        const sent = JSON.parse(localStorage.getItem(sentKey) || '[]');

        document.querySelectorAll('.card').forEach((card, i) => {{
            if (sent.includes(i)) card.classList.add('sent');

            const btn = card.querySelector('.btn-whatsapp');
            btn.addEventListener('click', () => {{
                if (!sent.includes(i)) {{
                    sent.push(i);
                    localStorage.setItem(sentKey, JSON.stringify(sent));
                }}
                setTimeout(() => card.classList.add('sent'), 1000);
            }});
        }});
    </script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    html = generar_html()
    output = "static/fu-prueba-16mayo.html"
    import os
    os.makedirs("static", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generado: {output}")
    print(f"Familias: {len(FAMILIAS)}")
    print(f"Niños: {sum(len(f['hijos']) for f in FAMILIAS)}")
