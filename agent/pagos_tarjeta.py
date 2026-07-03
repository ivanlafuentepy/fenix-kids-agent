# agent/pagos_tarjeta.py — Link de pago con tarjeta (pasarela Bancard)
# FENIX KIDS ACADEMY

"""
Genera el link firmado a la pasarela central de pagos (repo pagos-bancard).
La firma cubre negocio+monto para que el cliente no pueda editar el monto en
la URL. LINK_SECRET es el MISMO valor que en pagos-bancard (`firmar_link` en
app/main.py). La confirmación del pago vuelve por POST /pago-confirmado.
"""

import hashlib
import hmac
import os
from urllib.parse import urlencode


def _base_url() -> str:
    return os.getenv("PAGOS_BASE_URL", "https://pago.ivanlafuente.com").rstrip("/")


def tarjeta_habilitada() -> bool:
    """Sin LINK_SECRET no se pueden firmar links → no se ofrece tarjeta."""
    return bool(os.getenv("LINK_SECRET", ""))


def link_pago_fenix(monto: int, concepto: str = "", telefono: str = "") -> str:
    """Arma el link firmado de pago con tarjeta de Fenix Kids.

    firma = HMAC(LINK_SECRET, "fenix:{monto}") primeros 16 hex — idéntica a la
    que valida la pasarela. `telefono` va como ?cliente= para que la pasarela
    nos avise por /pago-confirmado y podamos vincular el pago a la familia.
    """
    secret = os.getenv("LINK_SECRET", "")
    sig = hmac.new(secret.encode(), f"fenix:{int(monto)}".encode(), hashlib.sha256).hexdigest()[:16]
    params = {"monto": int(monto), "sig": sig}
    if concepto:
        params["concepto"] = concepto
    if telefono:
        params["cliente"] = telefono
    return f"{_base_url()}/pagar/fenix?{urlencode(params)}"
