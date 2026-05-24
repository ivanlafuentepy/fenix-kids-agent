# agent/tools/escalacion.py — Escalada determinística a humano
# Reemplaza la "regla de silencio" (frase mágica) por un tool que
# Claude llama explícitamente cuando no sabe la respuesta.

import os
import logging
from urllib.parse import quote

logger = logging.getLogger("agentkit")

_MOTIVOS_DISPLAY = {
    "no_se_la_respuesta": "No supo la respuesta",
    "padre_pide_humano": "Padre pidió hablar con persona",
    "tema_sensible": "Tema sensible (diagnóstico, queja)",
    "fuera_de_ambito": "Pregunta fuera de FENIX",
    "queja_o_problema": "Queja o problema",
}


async def escalar_a_humano(telefono: str, motivo: str, resumen: str, **kwargs) -> dict:
    """
    Transfiere la conversación al Profe Ivan humano.
    Envía handoff estructurado a Telegram + WhatsApp admin.
    Silencia el agente para que Ivan responda.
    """
    from agent.telegram_bridge import (
        silenciar_dorita, notificar_llamada_urgente, obtener_topic,
    )
    from agent.memory import obtener_historial

    # Obtener contexto
    historial = await obtener_historial(telefono, limite=10)
    ultimo_msg_padre = ""
    for msg in reversed(historial):
        if msg["role"] == "user":
            ultimo_msg_padre = msg["content"][:200]
            break

    # Extraer nombre del padre del historial (best effort)
    nombre_padre = "Lead"
    for msg in historial:
        if msg["role"] == "user" and len(msg["content"].split()) <= 4:
            # Posible presentación corta
            palabras = msg["content"].strip().split()
            if 1 <= len(palabras) <= 3 and palabras[0][0].isupper():
                nombre_padre = msg["content"].strip()
                break

    primer_nombre = nombre_padre.split()[0] if nombre_padre != "Lead" else ""
    mensaje_pre = f"Que tal {primer_nombre}, soy el profe Ivan" if primer_nombre else "Que tal, soy el profe Ivan"
    wa_link = f"https://wa.me/{telefono}?text={quote(mensaje_pre)}"

    # Link al topic de Telegram
    tg_link = ""
    try:
        topic = await obtener_topic(telefono)
        if topic and topic.topic_id and topic.group_id:
            gid = str(topic.group_id).replace("-100", "", 1)
            tg_link = f"\n💬 https://t.me/c/{gid}/{topic.topic_id}"
    except Exception:
        pass

    motivo_display = _MOTIVOS_DISPLAY.get(motivo, motivo)

    # Handoff estructurado
    alerta = (
        f"🔴 ESCALACIÓN → IVAN\n\n"
        f"📋 Motivo: {motivo_display}\n"
        f"👤 Padre: {nombre_padre}\n"
        f"💬 Último msg: {ultimo_msg_padre}\n"
        f"📝 Resumen: {resumen}\n\n"
        f"📲 {wa_link}"
        f"{tg_link}"
    )

    # Canal 1: WhatsApp al admin
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    try:
        from agent.providers import obtener_proveedor
        proveedor = obtener_proveedor()
        await proveedor.enviar_mensaje(admin_phone, alerta)
        logger.info(f"[ESCALAR] WhatsApp admin: OK — {motivo}")
    except Exception as e:
        logger.error(f"[ESCALAR] Error WhatsApp admin: {e}")

    # Canal 2: Telegram
    try:
        await notificar_llamada_urgente(telefono, nombre_padre, wa_link)
        logger.info(f"[ESCALAR] Telegram: OK — {motivo}")
    except Exception as e:
        logger.error(f"[ESCALAR] Error Telegram: {e}")

    # Silenciar agente (5 min normal, 10 min urgente no implementado aún)
    await silenciar_dorita(telefono)
    logger.info(f"[ESCALAR] Agente silenciado para {telefono} — motivo: {motivo}")

    return {
        "texto": "Te respondo en un minuto 😊",
        "escalado": True,
        "motivo": motivo,
        "nombre_padre": nombre_padre,
    }
