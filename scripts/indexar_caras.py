# scripts/indexar_caras.py — Carga inicial de caras en AWS Rekognition
# FENIX KIDS ACADEMY

"""
Lee la foto de referencia de cada niño en Airtable (NIÑOS FENIX + PRUEBA FENIX)
y la indexa en la collection de AWS Rekognition.

Uso:
  python scripts/indexar_caras.py           # indexa todos los que tengan FOTO sin FACE_ID
  python scripts/indexar_caras.py --all     # re-indexa todos (borra y vuelve a registrar)
  python scripts/indexar_caras.py --crear   # solo crea la collection (primera vez)

Prerequisitos:
  - Campo FOTO (attachment) + FACE_ID (text) en NIÑOS FENIX y PRUEBA FENIX
  - Variables AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION en .env
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from dotenv import load_dotenv

load_dotenv()

from agent.face_recognition import crear_collection, registrar_cara, actualizar_cara, contar_caras
from agent.airtable_client import _patch, _NINOS, _headers, _BASE_URL

_PRUEBAS = "PRUEBA FENIX"


async def _obtener_registros_con_foto(tabla: str, solo_sin_face_id: bool, campo_nombre: str = "NOMBRE") -> list[dict]:
    """
    Obtiene registros con campo FOTO de una tabla.
    campo_nombre: "NOMBRE" para NIÑOS, "NOMBRE HIJO" para PRUEBA.
    """
    url = f"{_BASE_URL}/{tabla}"
    params = {"maxRecords": 200}
    registros = []

    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(url, params=params, headers=_headers(), timeout=15)
            if r.status_code != 200:
                print(f"Error obteniendo {tabla}: {r.status_code} {r.text[:200]}")
                break

            data = r.json()
            for rec in data.get("records", []):
                fields = rec.get("fields", {})
                foto = fields.get("FOTO")
                if foto and len(foto) > 0:
                    if solo_sin_face_id and fields.get("FACE_ID"):
                        continue
                    registros.append({
                        "id": rec["id"],
                        "tabla": tabla,
                        "nombre": fields.get(campo_nombre, ""),
                        "apellido": fields.get("APELLIDO", fields.get("APELLIDO HIJO", "")),
                        "apodo": fields.get("APODO", ""),
                        "foto_url": foto[0]["url"],
                        "face_id": fields.get("FACE_ID", ""),
                    })

            offset = data.get("offset")
            if offset:
                params["offset"] = offset
            else:
                break

    return registros


async def descargar_foto(url: str) -> bytes | None:
    """Descarga los bytes de una foto desde su URL."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.content
            print(f"  Error descargando foto: {r.status_code}")
        except Exception as e:
            print(f"  Error descargando foto: {e}")
    return None


async def main():
    reindexar_todos = "--all" in sys.argv
    solo_crear = "--crear" in sys.argv

    print("=" * 50)
    print("  FENIX KIDS — Indexación de Caras")
    print("=" * 50)
    print()

    # Paso 1: crear collection
    print("[1/3] Verificando collection en Rekognition...")
    ok = await crear_collection()
    if not ok:
        print("ERROR: No se pudo crear/verificar la collection. Revisá las credenciales AWS.")
        return

    n_caras = await contar_caras()
    print(f"      Collection tiene {n_caras} cara(s) registradas.")
    print()

    if solo_crear:
        print("Listo. Collection creada/verificada.")
        return

    # Paso 2: obtener niños con foto de AMBAS tablas
    print("[2/3] Buscando niños con foto en Airtable...")
    sin_face = not reindexar_todos
    ninos = await _obtener_registros_con_foto(_NINOS, sin_face, campo_nombre="NOMBRE")
    pruebas = await _obtener_registros_con_foto(_PRUEBAS, sin_face, campo_nombre="NOMBRE HIJO")
    todos = ninos + pruebas
    print(f"      NIÑOS FENIX: {len(ninos)} | PRUEBA FENIX: {len(pruebas)} | Total: {len(todos)}")
    print()

    if not todos:
        print("No hay niños nuevos para indexar. Usá --all para re-indexar todos.")
        return

    # Paso 3: indexar cada uno
    print("[3/3] Indexando caras...")
    exitosos = 0
    fallidos = 0

    for i, nino in enumerate(todos, 1):
        nombre_display = nino["apodo"] or nino["nombre"]
        etiqueta = "NIÑO" if nino["tabla"] == _NINOS else "PRUEBA"
        print(f"  [{i}/{len(todos)}] [{etiqueta}] {nombre_display} {nino['apellido']}...", end=" ")

        image_bytes = await descargar_foto(nino["foto_url"])
        if not image_bytes:
            print("FALLO (descarga)")
            fallidos += 1
            continue

        if reindexar_todos and nino["face_id"]:
            face_id = await actualizar_cara(nino["id"], image_bytes)
        else:
            face_id = await registrar_cara(nino["id"], image_bytes)

        if face_id:
            await _patch(nino["tabla"], nino["id"], {"FACE_ID": face_id})
            print(f"OK (FaceId: {face_id[:8]}...)")
            exitosos += 1
        else:
            print("FALLO (no se detectó cara)")
            fallidos += 1

    # Resumen
    print()
    print("-" * 50)
    print(f"  Resultado: {exitosos} exitosos, {fallidos} fallidos")
    n_total = await contar_caras()
    print(f"  Collection total: {n_total} caras")
    print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())
