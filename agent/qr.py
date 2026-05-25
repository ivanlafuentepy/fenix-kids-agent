# agent/qr.py — Generador de QR con logo FENIX KIDS
# Check-in por codigo QR: padre muestra, Ivan escanea, asistencia marcada

import os
import qrcode
from io import BytesIO
from PIL import Image

# Logo FENIX para el centro del QR
_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "marketing", "logos", "LOGO FENIX TRANSPARENTE OFICIAL.png"
)

# URL base del check-in (Railway en produccion)
_CHECKIN_BASE = os.getenv("CHECKIN_BASE_URL", "https://fenix-kids-agent-production.up.railway.app")


def generar_qr(record_id: str) -> bytes:
    """
    Genera imagen QR con logo FENIX en el centro.
    El QR apunta a /checkin/{record_id} para marcar PRESENTE.
    Retorna bytes PNG.
    """
    url = f"{_CHECKIN_BASE}/checkin/{record_id}"

    # QR con correccion de errores alta (permite logo encima)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    # Pegar logo en el centro si existe
    if os.path.exists(_LOGO_PATH):
        logo = Image.open(_LOGO_PATH).convert("RGBA")
        # Logo ocupa ~25% del QR (seguro con ERROR_CORRECT_H)
        logo_size = img.size[0] // 4
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

        # Posicion centrada
        pos_x = (img.size[0] - logo_size) // 2
        pos_y = (img.size[1] - logo_size) // 2

        # Fondo blanco detras del logo para mejor lectura
        bg = Image.new("RGBA", (logo_size + 10, logo_size + 10), "white")
        img.paste(bg, (pos_x - 5, pos_y - 5))
        img.paste(logo, (pos_x, pos_y), logo)

    # Convertir a PNG bytes
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
