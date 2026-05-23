"""Genera página HTML de aviso cambio horario — solo familias con reserva 9:30."""
import json
import urllib.parse
import html as html_mod

# Datos de reservas 9:30 del sábado 23/5 (obtenidos de /api/reservas)
familias_930 = [
    {
        "padre": "Carlos Raúl",
        "madre": "Blanca Zunilda",
        "cell_padre": "0981-700075",
        "cell_madre": "0981-700076",
        "hijos": [{"nombre": "Arianna", "edad": 10}],
        "tipo": "inscripta",
    },
    {
        "padre": "Jorge Andrés",
        "madre": "JAZMIN",
        "cell_padre": "0981397589",
        "cell_madre": "0981683435",
        "hijos": [{"nombre": "Fiorella", "edad": 3}],
        "tipo": "inscripta",
    },
    {
        "padre": "Sixinio Cristobal",
        "madre": "",
        "cell_padre": "595971961717",
        "cell_madre": "",
        "hijos": [
            {"nombre": "Maria Isabella", "edad": 7},
            {"nombre": "Sixinio Cristobal", "edad": 10},
            {"nombre": "Pauka Arami", "edad": 4},
        ],
        "tipo": "prueba",
    },
    {
        "padre": "Nancy",
        "madre": "",
        "cell_padre": "595981980706",
        "cell_madre": "",
        "hijos": [{"nombre": "Sebastián", "edad": 4}],
        "tipo": "prueba",
    },
    {
        "padre": "Viviana",
        "madre": "",
        "cell_padre": "595983888277",
        "cell_madre": "",
        "hijos": [{"nombre": "Franco Manuel", "edad": 7}],
        "tipo": "prueba",
    },
]

OUTPUT_AGENT = "static/aviso-cambio-horario.html"
OUTPUT_WEB = "C:/Users/IVAN LAFUENTE/Projects/fenixkidsacademy-web/aviso-cambio-horario.html"


def normalize_phone(phone):
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("0"):
        digits = "595" + digits[1:]
    if not digits.startswith("595"):
        digits = "595" + digits
    return digits


def make_msg(nombre):
    primer = nombre.split()[0] if nombre else "Hola"
    return (
        f"Hola {primer}! queria avisarte que como este y el proximo sabado "
        f"anuncio mucho frio, y a las 9:30 el pasto sigue mojado, estaremos "
        f"teniendo Fenix Kids solo a las 11 y a las 15:30h\n\n"
        f"Te gustaria agendar para uno de esos dos horarios?"
    )


def make_wa_link(phone, nombre):
    return f"https://wa.me/{normalize_phone(phone)}?text={urllib.parse.quote(make_msg(nombre))}"


def edad_badge(edad):
    if edad is None:
        return '<span class="badge badge-gray">s/edad</span>'
    if edad <= 5:
        return f'<span class="badge badge-green">{edad} a</span>'
    elif edad <= 8:
        return f'<span class="badge badge-blue">{edad} a</span>'
    return f'<span class="badge badge-orange">{edad} a</span>'


def render_card(fam):
    padre = fam["padre"]
    madre = fam["madre"]
    cp = fam["cell_padre"]
    cm = fam["cell_madre"]

    hijos_html = " &bull; ".join(
        f"{html_mod.escape(h['nombre'])} {edad_badge(h['edad'])}" for h in fam["hijos"]
    )

    label = padre or madre or "?"
    if padre and madre:
        label = f"{padre} & {madre}"

    tipo_badge = ""
    if fam["tipo"] == "prueba":
        tipo_badge = ' <span class="badge badge-gray">PRUEBA</span>'

    links = []
    if cp and padre:
        link = make_wa_link(cp, padre)
        btn_label = html_mod.escape(padre.split()[0])
        links.append(
            f'<a href="{link}" target="_blank" class="btn-whatsapp btn-papa" '
            f'onclick="markSent(this)">Enviar a {btn_label} (papa)</a>'
        )
    if cm and madre:
        link = make_wa_link(cm, madre)
        btn_label = html_mod.escape(madre.split()[0])
        links.append(
            f'<a href="{link}" target="_blank" class="btn-whatsapp btn-mama" '
            f'onclick="markSent(this)">Enviar a {btn_label} (mama)</a>'
        )
    if not links:
        phone = cp or cm
        name = padre or madre or "?"
        if phone:
            link = make_wa_link(phone, name)
            btn_label = html_mod.escape(name.split()[0])
            links.append(
                f'<a href="{link}" target="_blank" class="btn-whatsapp" '
                f'onclick="markSent(this)">Enviar a {btn_label}</a>'
            )

    phones = []
    if cp:
        phones.append(f"P: {cp}")
    if cm:
        phones.append(f"M: {cm}")

    return f"""<div class="card">
    <div class="card-header">
        <div class="padre-name">{html_mod.escape(label)}{tipo_badge}</div>
    </div>
    <div class="hijos">{hijos_html}</div>
    <div class="telefono">{html_mod.escape(' | '.join(phones))}</div>
    <div class="buttons">{''.join(links)}</div>
</div>
"""


inscriptas = [f for f in familias_930 if f["tipo"] == "inscripta"]
pruebas = [f for f in familias_930 if f["tipo"] == "prueba"]

cards_html = "".join(render_card(f) for f in familias_930)
total_hijos = sum(len(f["hijos"]) for f in familias_930)
total_links = sum(
    1
    for f in familias_930
    for phone, name in [(f["cell_padre"], f["padre"]), (f["cell_madre"], f["madre"])]
    if phone and name
)

msg_preview = make_msg("[nombre]")

page = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FENIX Kids — Aviso Cambio Horario</title>
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
            margin-bottom: 20px;
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
        .stat {{ text-align: center; }}
        .stat-num {{
            font-size: 2em;
            font-weight: bold;
            color: #ff6b00;
        }}
        .stat-label {{
            font-size: 0.8em;
            color: #888;
        }}
        .msg-template {{
            background: #111;
            border-left: 3px solid #ff6b00;
            padding: 14px 18px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
            font-size: 0.9em;
            color: #ccc;
            line-height: 1.5;
            white-space: pre-wrap;
        }}
        .card {{
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            transition: border-color 0.2s;
        }}
        .card:hover {{ border-color: #ff6b00; }}
        .card-header {{ margin-bottom: 10px; }}
        .padre-name {{
            font-size: 1.2em;
            font-weight: 600;
            color: #fff;
        }}
        .hijos {{
            margin-bottom: 8px;
            line-height: 1.8;
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
            margin-bottom: 12px;
        }}
        .buttons {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .btn-whatsapp {{
            flex: 1;
            min-width: 140px;
            text-align: center;
            background: #25d366;
            color: #fff;
            text-decoration: none;
            padding: 12px;
            border-radius: 10px;
            font-weight: 600;
            font-size: 0.9em;
            transition: background 0.2s, opacity 0.3s;
        }}
        .btn-whatsapp:hover {{ background: #1ea952; }}
        .btn-papa {{ background: #2196f3; }}
        .btn-papa:hover {{ background: #1976d2; }}
        .btn-mama {{ background: #e91e90; }}
        .btn-mama:hover {{ background: #c2185b; }}
        .btn-whatsapp.sent {{
            opacity: 0.4;
        }}
        .btn-whatsapp.sent::after {{
            content: ' ✓';
        }}
        .counter {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #ff6b00;
            color: #fff;
            padding: 10px 18px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9em;
            z-index: 100;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>FENIX Kids</h1>
        <p>Aviso Cambio Horario — Reservas 9:30 del Sab 23/5</p>
        <p style="color:#ff6b00; margin-top:8px; font-size:0.85em">Se cancela turno 9:30 — quedan 11:00 y 15:30</p>
        <div class="stats">
            <div class="stat">
                <div class="stat-num">{len(familias_930)}</div>
                <div class="stat-label">Familias</div>
            </div>
            <div class="stat">
                <div class="stat-num">{total_hijos}</div>
                <div class="stat-label">Niños</div>
            </div>
            <div class="stat">
                <div class="stat-num">{total_links}</div>
                <div class="stat-label">Mensajes</div>
            </div>
        </div>
    </div>

    <div class="msg-template">{html_mod.escape(msg_preview)}</div>

    {cards_html}

    <div class="counter" id="counter">0 enviados</div>

    <script>
        const sentKey = 'fenix-aviso-horario-23mayo';
        const sent = new Set(JSON.parse(localStorage.getItem(sentKey) || '[]'));

        document.querySelectorAll('.btn-whatsapp').forEach((btn, i) => {{
            btn.dataset.idx = i;
            if (sent.has(i)) btn.classList.add('sent');
        }});
        updateCounter();

        function markSent(btn) {{
            const idx = parseInt(btn.dataset.idx);
            setTimeout(() => {{
                btn.classList.add('sent');
                sent.add(idx);
                localStorage.setItem(sentKey, JSON.stringify([...sent]));
                updateCounter();
            }}, 500);
        }}

        function updateCounter() {{
            const total = document.querySelectorAll('.btn-whatsapp').length;
            const sentCount = document.querySelectorAll('.btn-whatsapp.sent').length;
            document.getElementById('counter').textContent = sentCount + '/' + total + ' enviados';
        }}
    </script>
</body>
</html>"""

for path in [OUTPUT_AGENT, OUTPUT_WEB]:
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Generado: {path}")

print(f"Familias: {len(familias_930)} ({len(inscriptas)} inscriptas + {len(pruebas)} pruebas)")
print(f"Niños: {total_hijos} | Links wa.me: {total_links}")
