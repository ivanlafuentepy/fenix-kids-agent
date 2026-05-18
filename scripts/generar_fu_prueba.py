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
    {
        "padre": "Genesis",
        "apellido": "Yegros",
        "tel": "595981130388",
        "hijos": [{"nombre": "Mathias", "edad": "4,11", "rango": "3-5"}],
        "hora": "11:00"
    },
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
    {
        "padre": "Janeth",
        "apellido": "Paredes de Niz",
        "tel": "595971886648",
        "hijos": [
            {"nombre": "Mauro Jesus", "edad": "4,4", "rango": "3-5"},
            {"nombre": "Bruno Marcelo", "edad": "9,5", "rango": "9-12"}
        ],
        "hora": "9:30"
    },
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
    {
        "padre": "Beatriz",
        "apellido": "Benitez",
        "tel": "595984842052",
        "hijos": [{"nombre": "Mateo Daniel", "edad": "10,0", "rango": "9-12"}],
        "hora": "9:30"
    },
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
    {
        "padre": "Biviana",
        "apellido": "Bazán",
        "tel": "595973686713",
        "hijos": [{"nombre": "Christopher", "edad": "4,11", "rango": "3-5"}],
        "hora": "11:00"
    },
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
    {
        "padre": "Erica",
        "apellido": "Bogado",
        "tel": "595961550099",
        "hijos": [{"nombre": "Tomás Benjamín", "edad": "5,0", "rango": "3-5"}],
        "hora": "11:00"
    },
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

    # Bloques según rango de edad
    comentarios = {
        "3-5": [
            f"Se notó que {'disfrutaron' if multi else 'disfrutó'} mucho del movimiento libre y los juegos.",
            f"A esta edad, lo que más trabajan es la coordinación, la motricidad y la conexión con su cuerpo a través del juego.",
            f"Es la etapa donde más impacto tiene el movimiento en su desarrollo emocional: autoestima, seguridad y vínculos con otros niños.",
        ],
        "6-8": [
            f"Se {'notaron muy comprometidos' if multi else 'notó muy comprometido/a'} con los desafíos del entrenamiento.",
            f"A esta edad, lo que más trabajamos es la confianza, la coordinación y la superación de miedos a través de desafíos físicos reales.",
            f"Es una etapa clave para canalizar toda esa energía de forma positiva, y generar hábitos de independencia y actividad física.",
        ],
        "9-12": [
            f"Se {'notaron con mucha actitud' if multi else 'notó con mucha actitud'} durante el entrenamiento.",
            f"A esta edad, lo que más trabajamos es la disciplina, el liderazgo y la fuerza mental a través del entrenamiento funcional.",
            f"Es la etapa perfecta para fortalecer hábitos saludables, desconectar de las pantallas y construir autoestima real a través del esfuerzo.",
        ],
        "mixto": [
            f"Se notó que cada uno disfrutó el entrenamiento a su manera — los más chiquitos en el juego y el movimiento libre, los más grandes en los desafíos físicos.",
            f"En FENIX trabajamos por edades justamente para respetar lo que cada etapa necesita: coordinación y autoestima en los más chicos, disciplina y liderazgo en los más grandes.",
            f"Es un espacio donde cada uno crece a su ritmo, y eso se nota desde la primera clase.",
        ],
        "general": [
            f"Se notó que disfrutó mucho del entrenamiento y conectó bien con el grupo.",
            f"En FENIX trabajamos la parte física y emocional: confianza, coordinación, autoestima y hábitos saludables.",
            f"Es un espacio donde los chicos crecen de verdad, y eso se nota desde la primera clase.",
        ],
    }

    bloque = comentarios.get(rango, comentarios["general"])

    msg = (
        f"Hola {padre} 😊 Soy Iván, profe de FENIX Kids.\n\n"
        f"Quería agradecerte por haber venido el sábado con {nombre_hijo} al entrenamiento. "
        f"{bloque[0]}\n\n"
        f"{bloque[1]}\n\n"
        f"{bloque[2]}\n\n"
        f"Te cuento que los cupos para este mes están casi completos — estamos cerrando los últimos lugares de la promoción de lanzamiento.\n\n"
        f"Si te interesa asegurar el lugar de {nombre_hijo}, avisame y te paso los detalles. Sin presión, pero no quiero que se queden afuera 🙌"
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
            opacity: 0.4;
        }}
        .sent .btn-whatsapp {{
            background: #444;
            pointer-events: none;
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
