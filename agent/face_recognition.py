# agent/face_recognition.py — Reconocimiento facial con AWS Rekognition
# FENIX KIDS ACADEMY

"""
Identifica niños en fotos de clase usando AWS Rekognition.

Flujo:
  1. registrar_cara() indexa la foto de referencia de un niño en la collection.
  2. identificar_ninos() recibe una foto de clase y retorna los niños detectados.
  3. La collection se crea una sola vez con crear_collection().

Variables de entorno:
  AWS_ACCESS_KEY_ID      — credencial AWS
  AWS_SECRET_ACCESS_KEY  — credencial AWS
  AWS_REGION             — región (default: us-east-1)
"""

import os
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("agentkit")

COLLECTION_ID = os.getenv("REKOGNITION_COLLECTION_ID", "fenix-kids")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def _get_client():
    """Retorna un cliente de Rekognition configurado."""
    return boto3.client(
        "rekognition",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


async def crear_collection() -> bool:
    """
    Crea la collection de caras en Rekognition (una sola vez).
    Retorna True si se creó o ya existía.
    """
    client = _get_client()
    try:
        client.create_collection(CollectionId=COLLECTION_ID)
        logger.info(f"[FaceRec] Collection '{COLLECTION_ID}' creada")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
            logger.info(f"[FaceRec] Collection '{COLLECTION_ID}' ya existe")
            return True
        logger.error(f"[FaceRec] Error creando collection: {e}")
        return False


async def registrar_cara(nino_id: str, image_bytes: bytes) -> Optional[str]:
    """
    Indexa la cara de un niño en la collection.

    Args:
        nino_id: record_id de Airtable (NIÑOS FENIX) — se usa como ExternalImageId
        image_bytes: bytes de la foto de referencia

    Returns:
        FaceId asignado por Rekognition, o None si falla.
    """
    client = _get_client()
    try:
        response = client.index_faces(
            CollectionId=COLLECTION_ID,
            Image={"Bytes": image_bytes},
            ExternalImageId=nino_id,
            MaxFaces=1,
            QualityFilter="AUTO",
            DetectionAttributes=["DEFAULT"],
        )
        faces = response.get("FaceRecords", [])
        if not faces:
            logger.warning(f"[FaceRec] No se detectó cara en la foto para {nino_id}")
            return None

        face_id = faces[0]["Face"]["FaceId"]
        confidence = faces[0]["Face"]["Confidence"]
        logger.info(f"[FaceRec] Cara registrada: {nino_id} → FaceId={face_id} (conf={confidence:.1f}%)")
        return face_id

    except ClientError as e:
        logger.error(f"[FaceRec] Error indexando cara para {nino_id}: {e}")
        return None


async def identificar_ninos(image_bytes: bytes, threshold: float = 70.0) -> list[dict]:
    """
    Busca caras conocidas en una foto de clase.

    Args:
        image_bytes: bytes de la foto de clase
        threshold: confianza mínima para considerar un match (default 70%)

    Returns:
        Lista de matches: [{"nino_id": str, "confidence": float, "bounding_box": dict}]
        nino_id es el ExternalImageId (record_id de Airtable).
    """
    client = _get_client()
    resultados = []

    try:
        # Primero detectar todas las caras en la imagen
        detect_response = client.detect_faces(
            Image={"Bytes": image_bytes},
            Attributes=["DEFAULT"],
        )
        caras_detectadas = detect_response.get("FaceDetails", [])

        if not caras_detectadas:
            logger.info("[FaceRec] No se detectaron caras en la imagen")
            return []

        if len(caras_detectadas) > 1:
            # Foto grupal: SearchFacesByImage solo procesa la cara más grande,
            # así que se recorta cada cara y se busca por separado
            resultados = await _buscar_multiples_caras(client, image_bytes, caras_detectadas, threshold)
        else:
            response = client.search_faces_by_image(
                CollectionId=COLLECTION_ID,
                Image={"Bytes": image_bytes},
                MaxFaces=10,
                FaceMatchThreshold=threshold,
            )

            for match in response.get("FaceMatches", []):
                face = match["Face"]
                resultados.append({
                    "nino_id": face["ExternalImageId"],
                    "face_id": face["FaceId"],
                    "confidence": match["Similarity"],
                })

        logger.info(f"[FaceRec] {len(resultados)} niño(s) identificado(s) en la foto")
        return resultados

    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidParameterException":
            logger.warning("[FaceRec] No se detectó cara válida en la imagen")
            return []
        logger.error(f"[FaceRec] Error buscando caras: {e}")
        return []


def _recortar_cara(image_bytes: bytes, bbox: dict, margen: float = 0.35) -> Optional[bytes]:
    """
    Recorta una cara de la imagen según el BoundingBox de detect_faces
    (coordenadas relativas 0-1). Margen extra para que Rekognition pueda
    re-detectar la cara en el recorte.
    """
    from io import BytesIO
    from PIL import Image, ImageOps

    try:
        img = Image.open(BytesIO(image_bytes))
        # Rekognition corrige la orientación EXIF por su cuenta; Pillow no.
        # Sin esto los bounding boxes no calzan en fotos rotadas de celular.
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        ancho, alto = img.size
        x, y = bbox["Left"] * ancho, bbox["Top"] * alto
        w, h = bbox["Width"] * ancho, bbox["Height"] * alto
        mx, my = w * margen, h * margen
        caja = (
            max(0, int(x - mx)),
            max(0, int(y - my)),
            min(ancho, int(x + w + mx)),
            min(alto, int(y + h + my)),
        )
        crop = img.crop(caja)
        if crop.width < 80 or crop.height < 80:  # mínimo que acepta Rekognition
            factor = max(80 / crop.width, 80 / crop.height, 2.0)
            crop = crop.resize((int(crop.width * factor), int(crop.height * factor)))
        buf = BytesIO()
        crop.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[FaceRec] Error recortando cara: {e}")
        return None


async def _buscar_multiples_caras(
    client, image_bytes: bytes, caras: list, threshold: float
) -> list[dict]:
    """
    Foto grupal: recorta cada cara detectada con Pillow y la busca por separado
    contra la collection (SearchFacesByImage solo procesa la cara más grande).
    Deduplica por nino_id quedándose con la mejor confidence.
    """
    mejores: dict[str, dict] = {}

    # Filtrar caras dudosas (fondo/borrosas) y capear el costo por foto
    caras_utiles = [c for c in caras if c.get("Confidence", 0) >= 90][:15]

    for cara in caras_utiles:
        crop_bytes = _recortar_cara(image_bytes, cara["BoundingBox"])
        if not crop_bytes:
            continue
        try:
            response = client.search_faces_by_image(
                CollectionId=COLLECTION_ID,
                Image={"Bytes": crop_bytes},
                MaxFaces=1,
                FaceMatchThreshold=threshold,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidParameterException":
                continue  # el recorte no tiene cara detectable (perfil, borrosa)
            logger.warning(f"[FaceRec] Error buscando cara recortada: {e}")
            continue

        for match in response.get("FaceMatches", []):
            face = match["Face"]
            nino_id = face["ExternalImageId"]
            if nino_id not in mejores or match["Similarity"] > mejores[nino_id]["confidence"]:
                mejores[nino_id] = {
                    "nino_id": nino_id,
                    "face_id": face["FaceId"],
                    "confidence": match["Similarity"],
                }

    return list(mejores.values())


async def actualizar_cara(nino_id: str, image_bytes: bytes) -> Optional[str]:
    """
    Actualiza la foto de referencia de un niño (borra la vieja, indexa la nueva).

    Args:
        nino_id: record_id del niño en Airtable
        image_bytes: bytes de la nueva foto

    Returns:
        Nuevo FaceId, o None si falla.
    """
    # Buscar y borrar caras existentes con ese ExternalImageId
    await eliminar_cara(nino_id)
    # Registrar la nueva
    return await registrar_cara(nino_id, image_bytes)


async def eliminar_cara(nino_id: str) -> bool:
    """
    Elimina todas las caras de un niño de la collection.

    Args:
        nino_id: record_id del niño en Airtable
    """
    client = _get_client()
    try:
        # Listar caras con ese ExternalImageId
        response = client.list_faces(
            CollectionId=COLLECTION_ID,
            MaxResults=10,
        )

        face_ids_a_borrar = []
        for face in response.get("Faces", []):
            if face.get("ExternalImageId") == nino_id:
                face_ids_a_borrar.append(face["FaceId"])

        # Paginar si hay más
        while response.get("NextToken"):
            response = client.list_faces(
                CollectionId=COLLECTION_ID,
                MaxResults=100,
                NextToken=response["NextToken"],
            )
            for face in response.get("Faces", []):
                if face.get("ExternalImageId") == nino_id:
                    face_ids_a_borrar.append(face["FaceId"])

        if face_ids_a_borrar:
            client.delete_faces(
                CollectionId=COLLECTION_ID,
                FaceIds=face_ids_a_borrar,
            )
            logger.info(f"[FaceRec] Eliminadas {len(face_ids_a_borrar)} cara(s) de {nino_id}")
            return True

        return True  # No había caras, todo bien

    except ClientError as e:
        logger.error(f"[FaceRec] Error eliminando caras de {nino_id}: {e}")
        return False


async def listar_caras() -> list[dict]:
    """Lista todas las caras registradas en la collection."""
    client = _get_client()
    caras = []
    try:
        response = client.list_faces(CollectionId=COLLECTION_ID, MaxResults=100)
        caras.extend(response.get("Faces", []))
        while response.get("NextToken"):
            response = client.list_faces(
                CollectionId=COLLECTION_ID,
                MaxResults=100,
                NextToken=response["NextToken"],
            )
            caras.extend(response.get("Faces", []))

        return [
            {"face_id": f["FaceId"], "nino_id": f.get("ExternalImageId", ""), "confidence": f.get("Confidence", 0)}
            for f in caras
        ]
    except ClientError as e:
        logger.error(f"[FaceRec] Error listando caras: {e}")
        return []


async def contar_caras() -> int:
    """Retorna el número de caras en la collection."""
    client = _get_client()
    try:
        response = client.describe_collection(CollectionId=COLLECTION_ID)
        return response.get("FaceCount", 0)
    except ClientError as e:
        logger.error(f"[FaceRec] Error contando caras: {e}")
        return 0
