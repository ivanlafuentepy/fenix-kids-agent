# scripts/taggear_fotos_web.py — Tagueo batch de las fotos del catálogo web con Rekognition
# FENIX KIDS ACADEMY

"""
Recorre las fotos públicas del catálogo web (fenixkidsacademy-web/fotos/assets/full),
identifica qué niños aparecen en cada una (agent/face_recognition, pipeline con
recorte por cara) y guarda el mapeo PRIVADO foto→nino_id en Postgres de Railway
(tablas fotos_web_tags / fotos_web_procesadas de agent/juego_endpoints.py).

Uso (local, con DATABASE_PUBLIC_URL del servicio Postgres en el .env o el entorno):
  python scripts/taggear_fotos_web.py                     # dry-run: procesa fotos nuevas y genera reporte
  python scripts/taggear_fotos_web.py --aplicar           # además escribe tags en la DB
  python scripts/taggear_fotos_web.py --todas             # re-procesa también las ya procesadas
  python scripts/taggear_fotos_web.py --reporte out.html  # dónde dejar el reporte (default scratch)

Los tags se guardan desde threshold 70 (auditables); el endpoint público sirve
solo confidence >= 80 (FOTOS_MIN_CONF en juego_endpoints.py).
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

REPO_WEB_DEFAULT = Path("C:/Users/IVAN LAFUENTE/Projects/fenixkidsacademy-web")
THRESHOLD_DEFAULT = 70.0


def _engine_publico():
    """Engine contra el Postgres de Railway usando DATABASE_PUBLIC_URL (la
    DATABASE_URL interna .railway.internal no resuelve fuera de Railway)."""
    from sqlalchemy.ext.asyncio import create_async_engine
    url = os.getenv("DATABASE_PUBLIC_URL", "")
    if not url:
        sys.exit("Falta DATABASE_PUBLIC_URL (sacala del servicio Postgres en Railway)")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url)


async def _ninos_airtable() -> dict[str, dict]:
    """nino_id → {nombre, face_id} de NIÑOS FENIX, paginando a mano
    (_get_records trunca a 100)."""
    import httpx
    from agent.airtable_client import _BASE_URL, _NINOS, _headers

    ninos: dict[str, dict] = {}
    params: dict = {"pageSize": 100}
    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(f"{_BASE_URL}/{_NINOS}", params=params, headers=_headers(), timeout=20)
            if r.status_code != 200:
                print(f"Error leyendo NIÑOS FENIX: {r.status_code} {r.text[:200]}")
                break
            data = r.json()
            for rec in data.get("records", []):
                f = rec.get("fields", {})
                nombre = (f.get("APODO") or f.get("NOMBRE") or "").strip()
                apellido = (f.get("APELLIDO") or "").strip()
                ninos[rec["id"]] = {
                    "nombre": f"{nombre} {apellido}".strip() or rec["id"],
                    "face_id": (f.get("FACE_ID") or "").strip(),
                }
            offset = data.get("offset")
            if not offset:
                break
            params["offset"] = offset
    return ninos


def _cargar_fechas(manifest_path: Path) -> dict[str, str]:
    """salida (foto-NNNN.jpg) → fecha 'YYYY-MM-DD' desde el manifest del repo web."""
    fechas = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for info in manifest.values():
            fecha = (info.get("fecha") or "")[:10]
            fechas[info["salida"]] = fecha or None
    return fechas


def _generar_reporte(path: Path, resultados: list[dict], ninos: dict, thumb_dir: Path, threshold: float):
    """HTML local para que Ivan revise los matches ANTES de aplicar."""
    por_nino: dict[str, list[dict]] = {}
    sin_match = []
    for r in resultados:
        if r["matches"]:
            for m in r["matches"]:
                por_nino.setdefault(m["nino_id"], []).append({**r, "confidence": m["confidence"]})
        else:
            sin_match.append(r)

    sin_face_id = {nid: n["nombre"] for nid, n in ninos.items() if not n["face_id"]}

    filas = []
    for nino_id, fotos in sorted(por_nino.items(), key=lambda kv: ninos.get(kv[0], {}).get("nombre", kv[0])):
        nombre = ninos.get(nino_id, {}).get("nombre", nino_id)
        thumbs = "".join(
            f'<div class="t"><img src="{(thumb_dir / f["archivo"]).as_uri()}">'
            f'<span class="{"ok" if f["confidence"] >= 80 else "rev"}">{f["archivo"]}<br>{f["confidence"]:.1f}%</span></div>'
            for f in sorted(fotos, key=lambda x: -x["confidence"])
        )
        filas.append(f'<section><h2>{nombre} <small>({nino_id}) — {len(fotos)} fotos</small></h2><div class="g">{thumbs}</div></section>')

    sm = "".join(
        f'<div class="t"><img src="{(thumb_dir / r["archivo"]).as_uri()}"><span>{r["archivo"]}<br>{r["caras"]} caras</span></div>'
        for r in sin_match
    )
    sf = "".join(f"<li>{n} ({nid})</li>" for nid, n in sorted(sin_face_id.items(), key=lambda kv: kv[1]))

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>Revision tagueo fotos — {datetime.now(ZoneInfo('America/Asuncion')):%d/%m/%Y %H:%M}</title>
<style>
body{{font-family:system-ui;background:#111;color:#eee;padding:20px}}
h2{{border-bottom:2px solid #f5a623;padding-bottom:4px}} small{{color:#888;font-weight:400}}
.g{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 30px}}
.t{{width:160px}} .t img{{width:100%;border-radius:8px}}
.t span{{font-size:11px;display:block;text-align:center}}
.ok{{color:#4ade80}} .rev{{color:#facc15}}
</style></head><body>
<h1>Revisión de tagueo — threshold {threshold:.0f} (verde ≥80 se publica, amarillo 70-80 queda en DB sin servir)</h1>
{"".join(filas) or "<p>Sin matches.</p>"}
<h2>Fotos sin ningún match ({len(sin_match)})</h2><div class="g">{sm or "—"}</div>
<h2>Niños sin FACE_ID ({len(sin_face_id)}) — no pueden aparecer; correr scripts/indexar_caras.py si tienen FOTO</h2>
<ul>{sf or "<li>—</li>"}</ul>
</body></html>"""
    path.write_text(html, encoding="utf-8")


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=REPO_WEB_DEFAULT / "fotos/assets/full")
    ap.add_argument("--manifest", type=Path, default=REPO_WEB_DEFAULT / "fotos/assets/manifest.json")
    ap.add_argument("--threshold", type=float, default=THRESHOLD_DEFAULT)
    ap.add_argument("--aplicar", action="store_true", help="Escribir tags en la DB (default: dry-run)")
    ap.add_argument("--todas", action="store_true", help="Re-procesar tambien las ya procesadas")
    ap.add_argument("--reporte", type=Path, default=None)
    args = ap.parse_args()

    if not args.dir.is_dir():
        sys.exit(f"No existe: {args.dir}")

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from agent.memory import Base
    from agent.juego_endpoints import FotoWebTag, FotoWebProcesada
    from agent.face_recognition import identificar_ninos, _get_client

    engine = _engine_publico()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        procesadas = set((await session.execute(select(FotoWebProcesada.archivo))).scalars())

    ninos = await _ninos_airtable()
    fechas = _cargar_fechas(args.manifest)
    archivos = sorted(p for p in args.dir.iterdir() if p.suffix.lower() == ".jpg")
    pendientes = [p for p in archivos if args.todas or p.name not in procesadas]
    print(f"{len(archivos)} fotos en el catálogo, {len(pendientes)} a procesar "
          f"({len(procesadas)} ya procesadas), {len(ninos)} niños en Airtable")

    client = _get_client()
    resultados = []
    for i, p in enumerate(pendientes, 1):
        data = p.read_bytes()
        try:
            det = client.detect_faces(Image={"Bytes": data}, Attributes=["DEFAULT"])
            caras = len(det.get("FaceDetails", []))
        except Exception as e:
            print(f"  {p.name}: ERROR detect ({str(e)[:80]})")
            continue
        matches = await identificar_ninos(data, threshold=args.threshold) if caras else []
        resultados.append({"archivo": p.name, "caras": caras, "matches": matches})
        nombres = ", ".join(f"{ninos.get(m['nino_id'], {}).get('nombre', m['nino_id'])} {m['confidence']:.0f}%" for m in matches)
        print(f"  [{i}/{len(pendientes)}] {p.name}: {caras} caras → {nombres or 'sin match'}")

    reporte = args.reporte or Path(os.getenv("TEMP", ".")) / "reporte_tagueo_fotos.html"
    _generar_reporte(reporte, resultados, ninos, args.dir.parent / "thumb", args.threshold)
    print(f"\nReporte: {reporte}")

    if not args.aplicar:
        print("Dry-run: NO se escribió nada. Revisar el reporte y correr con --aplicar.")
        return

    nuevos_tags = 0
    async with Session() as session:
        for r in resultados:
            for m in r["matches"]:
                existente = (await session.execute(
                    select(FotoWebTag).where(FotoWebTag.archivo == r["archivo"],
                                             FotoWebTag.nino_id == m["nino_id"])
                )).scalar_one_or_none()
                if existente:
                    if m["confidence"] > existente.confidence:
                        existente.confidence = m["confidence"]
                else:
                    session.add(FotoWebTag(archivo=r["archivo"], nino_id=m["nino_id"],
                                           confidence=m["confidence"],
                                           fecha_foto=fechas.get(r["archivo"])))
                    nuevos_tags += 1
            proc = await session.get(FotoWebProcesada, r["archivo"])
            if proc:
                proc.caras_detectadas = r["caras"]
                proc.matches = len(r["matches"])
            else:
                session.add(FotoWebProcesada(archivo=r["archivo"], caras_detectadas=r["caras"],
                                             matches=len(r["matches"])))
        await session.commit()
    print(f"Aplicado: {nuevos_tags} tags nuevos, {len(resultados)} fotos registradas como procesadas.")


if __name__ == "__main__":
    asyncio.run(main())
