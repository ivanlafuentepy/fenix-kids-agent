import asyncio, httpx, os, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

async def test():
    pid = os.getenv("META_PHONE_NUMBER_ID")
    token = os.getenv("META_ACCESS_TOKEN")
    print(f"PHONE_NUMBER_ID: {pid}")
    print(f"TOKEN (primeros 20): {token[:20] if token else 'VACÍO'}...")

    url = f"https://graph.facebook.com/v21.0/{pid}/messages"
    async with httpx.AsyncClient() as client:
        r = await client.post(url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"messaging_product":"whatsapp","to":"595982534337","type":"text","text":{"body":"test"}},
            timeout=15
        )
    print(f"\nHTTP: {r.status_code}")
    print(r.text)

asyncio.run(test())
