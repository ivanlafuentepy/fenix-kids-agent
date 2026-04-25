# tests/test_local.py — Simulador de chat en terminal
# FENIX KIDS ACADEMY — dual agente Profe Ivan + Nixie

"""
Probá el agente de Fenix Kids sin necesitar WhatsApp.
Replica el flujo de agent/main.py:webhook_handler pero en terminal,
sin Telegram (para no contaminar el grupo) y con Airtable + Calendar reales.

Comandos:
  salir   — terminar
  reset   — borrar conversación + lead en Airtable
  estado  — ver agente actual, modo, familia_id, etc.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.brain import generar_respuesta, extraer_datos_formulario
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial,
    limpiar_estado_completo,
)
from agent.ab_test import (
    asignar_variante, marcar_conversion, esta_convertido,
    obtener_agent_actual, actualizar_agent_actual,
    guardar_airtable_record_id, obtener_familia_id,
)
from agent.airtable_client import (
    crear_lead, actualizar_conversion_lead, actualizar_agent_lead,
    crear_familia_completa, eliminar_lead,
    buscar_familia_por_telefono, buscar_familia_por_nombre,
    obtener_ninos_de_familia,
)
# Importar las funciones de detección desde main (sin levantar el server)
from agent.main import (
    _detectar_activacion_nixie,
    _detectar_handoff_ivan_nixie,
    _detectar_confirmacion_nixie,
    _build_contexto_aurora,
)

TELEFONO_TEST = "595900000001"  # número de prueba — fácil de identificar y borrar
_MODO_PADRE = None  # familia simulada (record de Airtable)


async def mostrar_estado():
    agent, modo = await obtener_agent_actual(TELEFONO_TEST)
    familia_id = await obtener_familia_id(TELEFONO_TEST)
    convertido = await esta_convertido(TELEFONO_TEST)
    historial = await obtener_historial(TELEFONO_TEST, limite=100)
    print()
    print("─" * 55)
    print(f"  Telefono     : {TELEFONO_TEST}")
    print(f"  Agente       : {agent.upper()}")
    print(f"  Modo Nixie   : {modo or '-'}")
    print(f"  Mensajes     : {len(historial)}")
    print(f"  Convertido   : {convertido}")
    print(f"  Familia ID   : {familia_id or '-'}")
    print("─" * 55)
    print()


async def reset_completo():
    """Borra historial local + lead Airtable."""
    try:
        await eliminar_lead(TELEFONO_TEST)
        print("[reset] Lead Airtable eliminado")
    except Exception as e:
        print(f"[reset] Error eliminando lead Airtable: {e}")
    await limpiar_estado_completo(TELEFONO_TEST)
    print("[reset] Estado local borrado\n")


async def activar_modo_padre(nombre_apellido: str):
    """Busca familia por nombre (fuzzy) y activa modo Aurora simulando ser ese padre."""
    global _MODO_PADRE
    texto = nombre_apellido.strip()
    if not texto:
        print("[padre] Usá: padre Nombre (o Nombre Apellido)")
        return
    familia = await buscar_familia_por_nombre(texto)
    if not familia:
        print(f"[padre] No encontré familia con '{nombre} {apellido}' en FAMILIAS FENIX")
        return
    _MODO_PADRE = familia
    campos = familia.get("fields", {})
    hijos = await obtener_ninos_de_familia(familia["id"])
    nombres_hijos = [h.get("apodo") or h.get("nombre") for h in hijos]
    nombre_display = campos.get("APODO PADRE", "") or campos.get("NOMBRE PADRE", "") or campos.get("APODO MADRE", "") or campos.get("NOMBRE MADRE", "")
    print(f"[padre] Modo padre activado: {nombre_display}")
    print(f"[padre] Hijos: {', '.join(nombres_hijos) if nombres_hijos else 'ninguno'}")
    print(f"[padre] Aurora te va a saludar como si fueras este padre. Escribí 'hola' para empezar.")
    # Forzar agente a Aurora
    telefono = TELEFONO_TEST
    await actualizar_agent_actual(telefono, "aurora", "cliente_inscripto")
    # Limpiar historial para empezar limpio
    await limpiar_estado_completo(telefono)
    await asignar_variante(telefono)
    await actualizar_agent_actual(telefono, "aurora", "cliente_inscripto")
    print()


async def procesar_mensaje(texto: str):
    """Replica el flujo de webhook_handler en terminal (sin Telegram)."""
    global _MODO_PADRE
    telefono = TELEFONO_TEST

    # Estado actual
    agent_actual, modo_nixie = await obtener_agent_actual(telefono)

    # Detectar activación directa de Nixie
    if _detectar_activacion_nixie(texto) and agent_actual == "ivan":
        modo_nixie = "cliente_inscripto"
        agent_actual = "nixie"
        await actualizar_agent_actual(telefono, "nixie", modo_nixie)
        try:
            await actualizar_agent_lead(telefono, "NIXIE", modo_nixie)
        except Exception:
            pass

    # Historial
    historial = await obtener_historial(telefono)

    # Lead nuevo
    _, es_nuevo = await asignar_variante(telefono)
    if es_nuevo:
        try:
            record_id = await crear_lead(telefono, rompehielos="A")
            if record_id:
                await guardar_airtable_record_id(telefono, record_id)
                print("[airtable] LEAD creado")
        except Exception as e:
            print(f"[airtable] Error creando lead: {e}")

    # Contexto extra: modo padre simulado o cliente inscripto real
    contexto_extra = None
    if _MODO_PADRE and agent_actual == "aurora":
        try:
            # En modo test: forzar CONTROL_DATOS pendiente para probar onboarding
            contexto_extra = await _build_contexto_aurora(_MODO_PADRE)
            # NO hacemos check en CONTROL DATOS en modo test
        except Exception as e:
            print(f"[airtable] Error cargando familia simulada: {e}")
    elif agent_actual in ("nixie", "aurora") and modo_nixie == "cliente_inscripto":
        try:
            familia = await buscar_familia_por_telefono(telefono)
            if familia:
                contexto_extra = await _build_contexto_aurora(familia, telefono)
        except Exception as e:
            print(f"[airtable] Error buscando familia: {e}")

    # Generar respuesta
    respuesta = await generar_respuesta(
        mensaje=texto,
        historial=historial,
        agent_actual=agent_actual,
        contexto_extra=contexto_extra,
    )

    # Detectar handoff Ivan → Nixie
    if agent_actual == "ivan" and _detectar_handoff_ivan_nixie(respuesta):
        await actualizar_agent_actual(telefono, "nixie", "lead_nuevo")
        try:
            await actualizar_agent_lead(telefono, "NIXIE", "lead_nuevo")
        except Exception:
            pass
        print("[handoff] Ivan → Nixie (lead_nuevo)")

    # Si Nixie en modo lead_nuevo: intentar extraer formulario
    if agent_actual == "nixie" and (modo_nixie == "lead_nuevo" or not modo_nixie):
        historial_completo = historial + [
            {"role": "user", "content": texto},
            {"role": "assistant", "content": respuesta},
        ]
        try:
            datos = await extraer_datos_formulario(historial_completo)
            if datos.get("completo"):
                familia_id, nino_ids = await crear_familia_completa(telefono, datos)
                if familia_id:
                    await marcar_conversion(telefono)
                    try:
                        await actualizar_conversion_lead(telefono, "AGENDA")
                    except Exception:
                        pass
                    print(f"[airtable] FAMILIA + NIÑOS creados (familia_id={familia_id})")
        except Exception as e:
            print(f"[brain] Error extrayendo formulario: {e}")

    # Detectar confirmación de reserva
    confirmacion = _detectar_confirmacion_nixie(respuesta)
    if agent_actual == "nixie" and confirmacion:
        fecha_str = confirmacion.get("fecha", "")
        hora_str = confirmacion.get("hora", "")
        print(f"[reserva] Detectada confirmación: {fecha_str} {hora_str}")
        try:
            await actualizar_conversion_lead(telefono, "AGENDA")
        except Exception:
            pass

    # Guardar mensajes
    await guardar_mensaje(telefono, "user", texto)
    await guardar_mensaje(telefono, "assistant", respuesta)

    # Mostrar respuesta con label del agente
    label = "🌟 AURORA" if agent_actual in ("nixie", "aurora") else "👨‍🏫 IVAN"
    print(f"\n{label}: {respuesta}\n")


async def main():
    await inicializar_db()

    print()
    print("=" * 55)
    print("  FENIX KIDS — Test Local (Profe Ivan + Nixie)")
    print("=" * 55)
    print()
    print("  Escribí mensajes como si fueras un padre interesado.")
    print("  Comandos: 'reset', 'estado', 'salir', 'padre Nombre Apellido'")
    print(f"  Teléfono test: {TELEFONO_TEST}")
    print()
    print("-" * 55)
    print()

    while True:
        try:
            mensaje = input("Vos: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTest finalizado.")
            break

        if not mensaje:
            continue
        if mensaje.lower() == "salir":
            print("\nTest finalizado.")
            break
        if mensaje.lower() == "estado":
            await mostrar_estado()
            continue
        if mensaje.lower() == "reset":
            _MODO_PADRE = None
            await reset_completo()
            continue
        if mensaje.lower().startswith("padre "):
            await activar_modo_padre(mensaje[6:])
            continue

        await procesar_mensaje(mensaje)


if __name__ == "__main__":
    asyncio.run(main())
