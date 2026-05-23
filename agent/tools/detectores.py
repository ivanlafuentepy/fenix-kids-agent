# agent/tools/detectores.py — Detectores de intención del padre
# Funciones puras: reciben texto, retornan bool.
# Extraídas de main.py para preparar migración a Tool Use.


def padre_pregunta_horarios(texto: str) -> bool:
    """Detecta si el padre pregunta por horarios, frecuencia o días."""
    t = texto.lower().strip()
    patrones = [
        "cuantas veces", "cuántas veces", "que dias", "qué días", "que día",
        "horario", "horarios", "a la semana", "por semana", "frecuencia",
        "cuando es", "cuándo es", "cuando son", "cuándo son",
        "que dia", "qué dia", "dias de clase", "días de clase",
    ]
    return any(p in t for p in patrones)


def padre_pregunta_precios(texto: str) -> bool:
    """Detecta si el padre pregunta por precios, costos o planes."""
    t = texto.lower().strip()
    patrones = [
        "precio", "precios", "costo", "costos", "cuanto sale", "cuánto sale",
        "cuanto cuesta", "cuánto cuesta", "cuanto es", "cuánto es",
        "que sale", "qué sale", "tarifa", "tarifas", "planes", "mensualidad",
        "cuanto hay que pagar", "cuánto hay que pagar", "valor",
        "promo", "promocion", "promoción", "paquete", "paquetes",
    ]
    return any(p in t for p in patrones)


def padre_pregunta_hermanos(texto: str) -> bool:
    """Detecta si el padre pregunta por precios/descuentos para hermanos o tiene 2+ hijos."""
    t = texto.lower().strip()
    patrones = [
        "hermano", "hermanos", "hermana", "hermanas",
        "combo", "descuento familiar", "plan familiar",
        "plan hermano", "plan hermanos",
        "precio hermano", "precio hermanos",
        "2 hijos", "3 hijos", "dos hijos", "tres hijos",
        "dos nenes", "tres nenes", "dos nenas", "tres nenas",
        "varios hijos", "mas de un hijo", "más de un hijo",
        "familia", "descuento por hermano",
    ]
    return any(p in t for p in patrones)


def padre_pregunta_ubicacion(texto: str) -> bool:
    """Detecta si el padre pregunta por ubicación o dirección."""
    t = texto.lower().strip()
    patrones = [
        "ubicacion", "ubicación", "donde queda", "dónde queda",
        "donde es", "dónde es", "direccion", "dirección",
        "donde están", "donde estan", "dónde están",
        "como llego", "cómo llego", "lugar", "mapa",
    ]
    return any(p in t for p in patrones)


def padre_pregunta_duracion(texto: str) -> bool:
    """Detecta si el padre pregunta cuánto dura la clase."""
    t = texto.lower().strip()
    patrones = [
        "cuanto dura", "cuánto dura", "cuanto tiempo", "cuánto tiempo",
        "duracion", "duración", "cuantas horas", "cuántas horas",
        "cuanto es la clase", "cuánto es la clase", "cuanto rato", "cuánto rato",
    ]
    return any(p in t for p in patrones)


def padre_pregunta_que_llevar(texto: str) -> bool:
    """Detecta si el padre pregunta qué llevar o qué necesitan."""
    t = texto.lower().strip()
    patrones = [
        "que llevo", "qué llevo", "que llevar", "qué llevar",
        "que necesito", "qué necesito", "que tienen que traer", "qué tienen que traer",
        "que hay que llevar", "qué hay que llevar", "que traigo", "qué traigo",
        "que necesitan", "qué necesitan", "que debo llevar", "qué debo llevar",
    ]
    return any(p in t for p in patrones)


def padre_pregunta_devolucion(texto: str) -> bool:
    """Detecta si el padre pregunta por devolución o garantía."""
    t = texto.lower().strip()
    patrones = [
        "devolucion", "devolución", "devuelven", "reembolso",
        "si no le gusta", "si no les gusta", "garantia", "garantía",
        "se descuenta", "se puede descontar",
    ]
    return any(p in t for p in patrones)


def padre_pregunta_efectivo(texto: str) -> bool:
    """Detecta si el padre pregunta por medios de pago / efectivo."""
    t = texto.lower().strip()
    patrones = [
        "efectivo", "en efectivo", "pago en efectivo", "tarjeta",
        "medio de pago", "medios de pago", "como pago", "cómo pago",
        "forma de pago", "formas de pago", "puedo pagar",
    ]
    return any(p in t for p in patrones)


def padre_dice_ya_transfiri(texto: str) -> bool:
    """Detecta si el padre dice que ya transfirió pero sin enviar comprobante."""
    t = texto.lower().strip()
    patrones = [
        "ya transferi", "ya transferí", "ya hice la transferencia",
        "ya pague", "ya pagué", "ya deposite", "ya deposité",
        "ya envie", "ya envié", "listo ya pague", "listo ya pagué",
    ]
    return any(p in t for p in patrones)


def padre_pregunta_alias(texto: str) -> bool:
    """Detecta si el padre pregunta por el alias bancario."""
    t = texto.lower().strip()
    patrones = [
        "alias", "cual es el alias", "cuál es el alias",
        "el alias", "numero de alias", "número de alias",
    ]
    return any(p in t for p in patrones)
