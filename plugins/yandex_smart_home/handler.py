from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import os
import http.client
import json
from urllib.parse import urlencode

AUTH_SERVICE_BASE = os.getenv('AUTH_SERVICE_BASE', 'http://127.0.0.1:8000')
INTERNAL_TOKEN = os.getenv('INTERNAL_SERVICE_TOKEN', 'internal-service-token')
YANDEX_OAUTH_AUTHORIZE = os.getenv('YANDEX_OAUTH_AUTHORIZE', 'https://oauth.yandex.ru/authorize')
YANDEX_OAUTH_TOKEN = os.getenv('YANDEX_OAUTH_TOKEN', 'https://oauth.yandex.ru/token')


def _call_auth_service_set_token(service: str, token: str) -> dict:
    """Call auth_service POST /api/tokens/cloud/{service} with internal token."""
    from urllib.parse import urljoin
    url = urljoin(AUTH_SERVICE_BASE, f"/api/tokens/cloud/{service}")
    parsed = http.client.urlsplit(url)
    conn_class = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    conn = conn_class(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), timeout=10)
    try:
        body = json.dumps({"service": service, "token": token})
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {INTERNAL_TOKEN}"}
        conn.request('POST', parsed.path, body=body.encode('utf-8'), headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        text = data.decode('utf-8') if data else ''
        if 200 <= resp.status < 300:
            return json.loads(text) if text else {"status": "ok"}
        raise Exception(f"Auth service returned {resp.status}: {text}")
    finally:
        try:
            conn.close()
        except:
            pass


def build_oauth_authorize_url(state: str | None = None) -> str:
    client_id = os.getenv('YANDEX_CLIENT_ID')
    redirect = os.getenv('YANDEX_REDIRECT_URI')
    scope = os.getenv('YANDEX_OAUTH_SCOPE', 'smart_home')
    if not client_id or not redirect:
        raise RuntimeError('YANDEX_CLIENT_ID and YANDEX_REDIRECT_URI must be set')
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect,
        'scope': scope,
    }
    if state:
        params['state'] = state
    return YANDEX_OAUTH_AUTHORIZE + '?' + urlencode(params)


async def oauth_start():
    try:
        url = build_oauth_authorize_url()
        return JSONResponse({"auth_url": url})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def oauth_callback(request: Request):
    params = dict(request.query_params)
    code = params.get('code') or (await request.form()).get('code') if request.method == 'POST' else None
    if not code:
        raise HTTPException(status_code=400, detail='code required')

    # Exchange code for token
    client_id = os.getenv('YANDEX_CLIENT_ID')
    client_secret = os.getenv('YANDEX_CLIENT_SECRET')
    redirect = os.getenv('YANDEX_REDIRECT_URI')
    if not client_id or not client_secret or not redirect:
        raise HTTPException(status_code=500, detail='Missing YANDEX_CLIENT_ID/SECRET/REDIRECT settings')

    body = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect
    }

    parsed = http.client.urlsplit(YANDEX_OAUTH_TOKEN)
    conn_class = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    conn = conn_class(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), timeout=10)
    try:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        conn.request('POST', parsed.path, body=urlencode(body), headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        text = data.decode('utf-8') if data else ''
        if not (200 <= resp.status < 300):
            raise HTTPException(status_code=502, detail=f'Failed exchanging token: {resp.status} {text}')
        token_resp = json.loads(text)
    finally:
        try:
            conn.close()
        except:
            pass

    access_token = token_resp.get('access_token') or token_resp.get('token')
    if not access_token:
        raise HTTPException(status_code=502, detail='No access_token in token response')

    # Save access + refresh token to auth_service if present
    refresh_token = token_resp.get('refresh_token')
    try:
        # send both token and refresh_token as part of body
        parsed = http.client.urlsplit(AUTH_SERVICE_BASE + f"/api/tokens/cloud/yandex_smart_home")
        conn_class = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
        conn = conn_class(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), timeout=10)
        body = json.dumps({"service": 'yandex_smart_home', "token": access_token, "refresh_token": refresh_token})
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {INTERNAL_TOKEN}"}
        conn.request('POST', parsed.path, body=body.encode('utf-8'), headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        text = data.decode('utf-8') if data else ''
        if not (200 <= resp.status < 300):
            raise HTTPException(status_code=502, detail=f'Auth service save failed: {resp.status} {text}')
    finally:
        try:
            conn.close()
        except:
            pass

    return JSONResponse({"status": "ok", "saved": True})


async def list_devices_proxy():
    # Fetch tokens dict from auth_service /api/tokens/cloud and extract yandex_smart_home token
    from urllib.parse import urljoin
    url = urljoin(AUTH_SERVICE_BASE, '/api/tokens/cloud')
    parsed = http.client.urlsplit(url)
    conn_class = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    conn = conn_class(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), timeout=10)
    try:
        headers = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}
        conn.request('GET', parsed.path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        text = data.decode('utf-8') if data else ''
        if resp.status != 200:
            raise HTTPException(status_code=502, detail='Failed to fetch tokens from auth_service')
        tokens = json.loads(text) if text else {}
        ytoken = tokens.get('yandex_smart_home')
        if not ytoken:
            raise HTTPException(status_code=400, detail='Yandex token not configured')
        access_token = ytoken if isinstance(ytoken, str) else ytoken.get('token')
    finally:
        try:
            conn.close()
        except:
            pass

    # Call Yandex Smart Home API devices endpoint
    api_base = os.getenv('YANDEX_API_BASE', 'https://api.iot.yandex.net')
    devices_path = os.getenv('YANDEX_DEVICES_PATH', '/v1.0/user/devices')
    parsed_api = http.client.urlsplit(api_base)
    conn_class = http.client.HTTPSConnection if parsed_api.scheme == 'https' else http.client.HTTPConnection
    conn = conn_class(parsed_api.hostname, parsed_api.port or (443 if parsed_api.scheme == 'https' else 80), timeout=10)
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        conn.request('GET', devices_path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        text = data.decode('utf-8') if data else ''
        if resp.status != 200:
            # return raw error from Yandex
            raise HTTPException(status_code=502, detail=f'Yandex API error: {resp.status} {text}')
        devices = json.loads(text) if text else []
        # Normalize devices to id/name/type list when possible
        normalized = []
        if isinstance(devices, dict) and devices.get('devices'):
            for d in devices.get('devices'):
                normalized.append({ 'id': d.get('id') or d.get('device_id') or d.get('instance_id'), 'name': d.get('name') or d.get('id'), 'type': d.get('type') or d.get('device_type') })
        elif isinstance(devices, list):
            for d in devices:
                if isinstance(d, dict):
                    normalized.append({ 'id': d.get('id') or d.get('device_id'), 'name': d.get('name'), 'type': d.get('type') })
        else:
            normalized = devices
        return JSONResponse({ 'devices': normalized })
    finally:
        try:
            conn.close()
        except:
            pass


async def execute_action(payload: dict):
    # payload: { action: 'yandex.switch.toggle', device_id: '...', on: true }
    # For MVP, we will check token presence and return ok (no real call)
    # TODO: implement mapping to Yandex Smart Home API
    # Check token presence quickly
    from urllib.parse import urljoin
    url = urljoin(AUTH_SERVICE_BASE, '/api/tokens/cloud/yandex_smart_home')
    parsed = http.client.urlsplit(url)
    conn_class = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    conn = conn_class(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), timeout=10)
    try:
        headers = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}
        conn.request('GET', parsed.path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        if resp.status != 200:
            raise HTTPException(status_code=400, detail='Yandex token not configured')
    finally:
        try:
            conn.close()
        except:
            pass

    # For MVP: send a POST to Yandex devices actions endpoint if possible
    device_id = payload.get('device_id')
    if not device_id:
        raise HTTPException(status_code=400, detail='device_id required')

    # retrieve token as above
    from urllib.parse import urljoin
    url = urljoin(AUTH_SERVICE_BASE, '/api/tokens/cloud')
    parsed = http.client.urlsplit(url)
    conn_class = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
    conn = conn_class(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), timeout=10)
    try:
        headers = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}
        conn.request('GET', parsed.path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        text = data.decode('utf-8') if data else ''
        if resp.status != 200:
            raise HTTPException(status_code=502, detail='Failed to fetch tokens from auth_service')
        tokens = json.loads(text) if text else {}
        ytoken = tokens.get('yandex_smart_home')
        if not ytoken:
            raise HTTPException(status_code=400, detail='Yandex token not configured')
        access_token = ytoken if isinstance(ytoken, str) else ytoken.get('token')
    finally:
        try:
            conn.close()
        except:
            pass

    api_base = os.getenv('YANDEX_API_BASE', 'https://api.iot.yandex.net')
    action_path_template = os.getenv('YANDEX_ACTION_PATH', '/v1.0/devices/{device_id}/actions')
    target_path = action_path_template.replace('{device_id}', str(device_id))
    parsed_api = http.client.urlsplit(api_base)
    conn_class = http.client.HTTPSConnection if parsed_api.scheme == 'https' else http.client.HTTPConnection
    conn = conn_class(parsed_api.hostname, parsed_api.port or (443 if parsed_api.scheme == 'https' else 80), timeout=10)
    try:
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        body = json.dumps(payload.get('params') or payload)
        conn.request('POST', target_path, body=body.encode('utf-8'), headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        text = data.decode('utf-8') if data else ''
        if not (200 <= resp.status < 300):
            raise HTTPException(status_code=502, detail=f'Yandex action error: {resp.status} {text}')
        return JSONResponse({ 'status': 'ok', 'yandex_response': json.loads(text) if text else {} })
    finally:
        try:
            conn.close()
        except:
            pass
