import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from helixcare_scenarios import create_jwt_token

async def main():
    token = create_jwt_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    async with websockets.connect('ws://localhost:8039/ws/live') as ws:
        start_payload = {
            'jsonrpc': '2.0',
            'id': '1',
            'method': 'avatar/start_session',
            'params': {
                'patient_case': {
                    'chief_complaint': 'test pain',
                    'age': 45,
                    'gender': 'female',
                    'urgency': 'medium',
                },
                'persona': 'senior_internist',
            },
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post('http://localhost:8039/rpc', json=start_payload, headers=headers)
            print('start status', r.status_code)
            sid = r.json()['result']['session_id']

            msg_payload = {
                'jsonrpc': '2.0',
                'id': '2',
                'method': 'avatar/patient_message',
                'params': {
                    'session_id': sid,
                    'message': 'I have chest discomfort',
                },
            }
            r2 = await client.post('http://localhost:8039/rpc', json=msg_payload, headers=headers)
            print('msg status', r2.status_code)

        evt1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        evt2 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        evt3 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        print('events', evt1.get('type'), evt2.get('type'), evt3.get('type'))
        print('speech_keys', sorted((evt2.get('speech') or {}).keys()))

asyncio.run(main())
