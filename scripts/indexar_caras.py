# scripts/indexar_caras.py — Carga inicial de caras en AWS Rekognition
# FENIX KIDS ACADEMY

"""
Lee la foto de referencia de cada niño en Airtable (campo FOTO en NIÑOS FENIX)
y la indexa en la collection de AWS Rekognition.

Uso:
  python scripts/indexar_caras.py           # indexa todos los que tengan FOTO sin FACE_ID
  python scripts/indexar_caras.py --all     # re-indexa todos (borra y vuelve a registrar)
  python scripts/indexar_caras.py --crear   # solo crea la collection (primera vez)

Prerequisitos:
  - Campo FOTO (attachment) en tabla NIÑOS FENIX de Airtable
  - Campo FACE_ID (single line text) en tabla NIÑOS FENIX
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
from agent.airtable_client import _get_records, _patch, _NINOS, _headers, _BASE_URL


async def obtener_ninos_con_foto(solo_sin_face_id: bool = True) -> list[dict]:
    """
    Obtiene todos los niños que tienen campo FOTO en Airtable.
    Si solo_sin_face_id=True, filtra los que ya tienen FACE_ID.
    """
    # Airtable no permite filtrar por attachment vacío con fórmulas,
    # así que obtenemos todos y filtramos en Python.
    url = f"{_BASE_URL}/{_NINOS}"
    params = {"maxRecords": 100}
    ninos = []

    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(url, params=params, headers=_headers(), timeout=15)
            if r.status_code != 200:
                print(f"Error obteniendo niños: {r.status_code} {r.text[:200]}")
                break

            data = r.json()
            for rec in data.get("records", []):
                fields = rec.get("fields", {})
                foto = fields.get("FOTO")  # Attachment field = lista de objetos
                if foto and len(foto) > 0:
                    if solo_sin_face_id and fields.get("FACE_ID"):
                        continue
                    ninos.append({
                        "id": rec["id"],
                        "nombre": fields.get("NOMBRE", ""),
                        "apellido": fields.get("APELLIDO", ""),
                        "apodo": fields.get("APODO", ""),
                        "foto_url": foto[0]["url"],  # Primera foto del attachment
                        "face_id": fields.get("FACE_ID", ""),
                    })

            # Paginación
            offset = data.get("offset")
            if offset:
                params["offset"] = offset
            else:
                break

    return ninos


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


async def guardar_face_id(nino_id: str, face_id: str) -> bool:
    """Guarda el FaceId en el campo FACE_ID del niño en Airtable."""
    return await _patch(_NINOS, nino_id, {"FACE_ID": face_id})


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

    # Paso 2: obtener niños con foto
    print("[2/3] Buscando niños con foto en Airtable...")
    ninos = await obtener_ninos_con_foto(solo_sin_face_id=not reindexar_todos)
    print(f"      {len(ninos)} niño(s) para indexar.")
    print()

    if not ninos:
        print("No hay niños nuevos para indexar. Usá --all para re-indexar todos.")
        return

    # Paso 3: indexar cada niño
    print("[3/3] Indexando caras...")
    exitosos = 0
    fallidos = 0

    for i, nino in enumerate(ninos, 1):
        nombre_display = nino["apodo"] or nino["nombre"]
        print(f"  [{i}/{len(ninos)}] {nombre_display} {nino['apellido']}...", end=" ")

        # Descargar foto
        image_bytes = await descargar_foto(nino["foto_url"])
        if not image_bytes:
            print("FALLO (descarga)")
            fallidos += 1
            continue

        # Indexar en Rekognition
        if reindexar_todos and nino["face_id"]:
            face_id = await actualizar_cara(nino["id"], image_bytes)
        else:
            face_id = await registrar_cara(nino["id"], image_bytes)

        if face_id:
            # Guardar FaceId en Airtable
            await guardar_face_id(nino["id"], face_id)
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
