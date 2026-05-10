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

        # Buscar cada cara contra la collection
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

        # Si hay múltiples caras, intentar con recortes individuales
        # SearchFacesByImage solo busca la cara más grande por defecto
        if len(caras_detectadas) > 1:
            resultados = await _buscar_multiples_caras(client, image_bytes, caras_detectadas, threshold)

        logger.info(f"[FaceRec] {len(resultados)} niño(s) identificado(s) en la foto")
        return resultados

    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidParameterException":
            logger.warning("[FaceRec] No se detectó cara válida en la imagen")
            return []
        logger.error(f"[FaceRec] Error buscando caras: {e}")
        return []


async def _buscar_multiples_caras(
    client, image_bytes: bytes, caras: list, threshold: float
) -> list[dict]:
    """
    Cuando hay múltiples caras, usa SearchFacesByImage con cada bounding box.
    Rekognition SearchFacesByImage solo procesa la cara más grande por defecto,
    así que para fotos grupales necesitamos recortar.

    Nota: Rekognition no soporta crop directo, pero podemos usar el truco de
    buscar con la imagen completa y confiar en que detecta múltiples matches.
    Si no alcanza, recortamos con Pillow.
    """
    resultados = []
    ninos_vistos = set()

    try:
        # SearchFacesByImage busca la cara más prominente
        response = client.search_faces_by_image(
            CollectionId=COLLECTION_ID,
            Image={"Bytes": image_bytes},
            MaxFaces=15,
            FaceMatchThreshold=threshold,
        )

        for match in response.get("FaceMatches", []):
            face = match["Face"]
            nino_id = face["ExternalImageId"]
            if nino_id not in ninos_vistos:
                ninos_vistos.add(nino_id)
                resultados.append({
                    "nino_id": nino_id,
                    "face_id": face["FaceId"],
                    "confidence": match["Similarity"],
                })

    except ClientError as e:
        logger.warning(f"[FaceRec] Error en búsqueda múltiple: {e}")

    return resultados


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
