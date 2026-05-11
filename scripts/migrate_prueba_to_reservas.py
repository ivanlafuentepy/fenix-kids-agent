"""Migra registros de PRUEBA FENIX a RESERVAS FENIX (inscriptos que se guardaron mal)."""
import asyncio, os, httpx
from dotenv import load_dotenv
load_dotenv()

async def main():
    token = os.environ['AIRTABLE_API_KEY']
    base = os.environ['AIRTABLE_BASE_ID']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    async with httpx.AsyncClient(timeout=30) as client:
        # Leer HORARIOS FENIX
        r = await client.get(f'https://api.airtable.com/v0/{base}/HORARIOS%20FENIX', headers=headers, params={'pageSize': '100'})
        horarios = r.json().get('records', [])
        horario_map = {}
        for h in horarios:
            f = h.get('fields', {})
            fecha = f.get('FECHA', '')
            hora = f.get('HORA', '')
            if fecha and hora:
                horario_map[f'{fecha}|{hora}'] = h['id']

        # Leer FAMILIAS para vincular por teléfono
        r3 = await client.get(f'https://api.airtable.com/v0/{base}/FAMILIAS%20FENIX', headers=headers, params={'pageSize': '100'})
        all_fam = r3.json().get('records', [])
        fam_by_phone = {}
        for fam in all_fam:
            f = fam.get('fields', {})
            for campo in ['CELL PADRE', 'CELL MADRE', 'CELL LIMPIO PADRE', 'CELL LIMPIO MADRE']:
                cell = (f.get(campo, '') or '').strip().replace('+','').replace(' ','').replace('-','')
                if cell.startswith('0'):
                    cell = '595' + cell[1:]
                if cell:
                    fam_by_phone[cell] = fam['id']

        # Migraciones con IDs completos (verificados manualmente)
        # (prueba_id, nino_id, telefono, fecha_iso, hora)
        migraciones = [
            ('recF5CkcEGSh3uSU6', 'recogiNWXLPxMSQT6', '595981700076', '2026-05-09', '9:30'),      # Arianna
            ('recGxLqxphIPG2axf', 'recy2dtJ20CJpQtn5', '595981683435', '2026-05-23', '9:30'),      # Fio (Fiorella González)
            ('recLT1TMyAJdjPWbc', 'receOZeU9wUprDIn5', '595981102495', '2026-05-09', '11:00'),     # Giuli (Giuliana Basomba)
            ('recLWzgmUpOpJgHtS', 'receOZeU9wUprDIn5', '595982844548', '2026-05-09', '11:00'),     # Giuliana (= Giuli, duplicado)
            ('recQCkpTJnW7CdNPF', 'recy2dtJ20CJpQtn5', '595981683435', '2026-05-09', '9:30'),      # Fio 9 mayo
            ('recXqIVz2P4IZqkPf', 'recklJ2AVNpDSzPgr', '595982935412', '2026-05-02', '15:30'),     # Ernesto
            ('recZMgxpwee4wjlDE', 'recEl02yRDzQyzezU', '595982844548', '2026-05-09', '11:00'),     # Isabella (Ichi)
            ('recgykthexHT839nd', 'recoHo4H32g9iWihN', '595971964001', '2026-05-30', '15:30'),     # Oli (Olivia Cuevas)
            ('rechE7n9b0XOMLrvv', 'rec8PgzQydVH2tVd7', '595981529457', '2026-05-09', '11:00'),     # Benjamin
            ('recjHDStVdumBzpd0', 'recCHnEwO2xQGnPbO', '595972816687', '2026-05-02', '11:00'),     # Helena
            ('recjnthXpJL6Mq9en', 'recMh8N1nCFCqhVLV', '595982935412', '2026-05-02', '15:30'),     # Catalina
            ('recxcmu5Bb35VK0ld', 'recEl02yRDzQyzezU', '595981102495', '2026-05-09', '11:00'),     # Ichi (=Isabella)
            ('recyFDnWELzac5OiF', 'rec7sG00QXl2VxyO8', '595982778542', '2026-05-02', '11:00'),     # Oli (Olivia Britez)
            ('recyVFEW6zxvsw2nu', 'recTFSrZElJgLJsGO', '595981529457', '2026-05-09', '11:00'),     # Luciana
        ]

        created = 0
        deleted = 0
        errors = 0

        for prueba_id, nino_id, tel, fecha_iso, hora in migraciones:
            familia_id = fam_by_phone.get(tel)
            if not familia_id:
                print(f'  SKIP — no familia para tel={tel}')
                errors += 1
                continue

            horario_key = f'{fecha_iso}|{hora}'
            horario_id = horario_map.get(horario_key)
            if not horario_id:
                print(f'  SKIP — no horario para {horario_key}')
                errors += 1
                continue

            # Crear RESERVA
            reserva_data = {
                'fields': {
                    'NINO': [nino_id],
                    'HORARIO': [horario_id],
                    'FAMILIAS': [familia_id],
                }
            }
            r_create = await client.post(
                f'https://api.airtable.com/v0/{base}/RESERVAS%20FENIX',
                headers=headers,
                json=reserva_data,
            )
            if r_create.status_code == 200:
                created += 1
                print(f'  OK RESERVA creada: nino={nino_id[:10]}... fecha={fecha_iso} {hora}')
            else:
                print(f'  ERROR creando: {r_create.status_code} {r_create.text[:150]}')
                errors += 1
                continue

            # Borrar de PRUEBA FENIX
            r_del = await client.delete(
                f'https://api.airtable.com/v0/{base}/PRUEBA%20FENIX/{prueba_id}',
                headers=headers,
            )
            if r_del.status_code == 200:
                deleted += 1
            else:
                print(f'  ERROR borrando {prueba_id}: {r_del.status_code}')

        # Borrar Demian (no tiene niño registrado en el sistema)
        r_dem = await client.delete(
            f'https://api.airtable.com/v0/{base}/PRUEBA%20FENIX/recehYyGNCEjYFdP4',
            headers=headers,
        )
        print(f'\nDemian borrado: {r_dem.status_code}')

        print(f'\n=== RESULTADO ===')
        print(f'Reservas creadas: {created}')
        print(f'Pruebas borradas: {deleted}')
        print(f'Errores/skips: {errors}')

asyncio.run(main())
