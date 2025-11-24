from typing import Any, Dict
import os
import asyncio
import json
from urllib.parse import urlencode

import http.client
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from sqlalchemy.orm import Session
from sqladmin import Admin, ModelView

from .db import engine, get_session
from .models import Base, Client, CommandLog, Enrollment


def _http_json(method: str, url: str, body: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None, timeout: float = 15.0) -> Any:
    base = os.getenv("CM_BASE_URL", "http://127.0.0.1:10000")
    from urllib.parse import urlparse as _parse
    b = _parse(base)
    scheme = (b.scheme or "http").lower()
    host = b.hostname or "127.0.0.1"
    port = b.port or (443 if scheme == "https" else 80)
    path = url
    if not path.startswith("/"):
        path = "/" + path
    if scheme == "https":
        import ssl
        ctx = ssl.create_default_context()
        # Dev-режим: отключаем проверку сертификата внутри docker-сети
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        payload = None
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        if body is not None:
            payload = json.dumps(body)
        conn.request(method.upper(), path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        text = data.decode("utf-8") if data else ""
        if 200 <= resp.status < 300:
            return json.loads(text) if text else None
        raise HTTPException(status_code=resp.status, detail=text or "Upstream error")
    except (TimeoutError, ConnectionError, OSError) as e:
        raise HTTPException(status_code=503, detail=f"Client manager unavailable: {str(e)}")
    finally:
        try:
            conn.close()
        except:
            pass


class ClientAdmin(ModelView, model=Client):
    column_list = [Client.id, Client.hostname, Client.ip, Client.port, Client.status, Client.last_heartbeat]
    name_plural = "Clients"


class CommandLogAdmin(ModelView, model=CommandLog):
    column_list = [CommandLog.id, CommandLog.client_id, CommandLog.command, CommandLog.status, CommandLog.exit_code, CommandLog.created_at]
    name_plural = "Command Logs"


class EnrollmentAdmin(ModelView, model=Enrollment):
    column_list = [Enrollment.id, Enrollment.status, Enrollment.created_at]
    name_plural = "Enrollments"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создание таблиц на запуске
    Base.metadata.create_all(bind=engine)
    yield


def create_admin_app(orchestrator) -> FastAPI:
    app = FastAPI(title="Core Admin Panel", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    # SQLAdmin панель на /admin
    admin = Admin(app, engine)
    admin.add_view(ClientAdmin)
    admin.add_view(CommandLogAdmin)
    admin.add_view(EnrollmentAdmin)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html = """
        <!doctype html>
        <html>
          <head>
            <meta charset=\"utf-8\" />
            <title>Core Admin</title>
            <style>
              body { font-family: -apple-system, Arial, sans-serif; margin: 24px; }
              h1 { margin-bottom: 8px; }
              .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
              .card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }
              .row { margin: 8px 0; }
              button { padding: 6px 10px; margin-right: 6px; }
              .ok { color: #065f46; }
              .bad { color: #991b1b; }
              code { background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }
              table { width: 100%; border-collapse: collapse; }
              th, td { border-bottom: 1px solid #eee; text-align: left; padding: 6px 4px; }
            </style>
          </head>
          <body>
            <h1>Core Admin</h1>
            <div class=\"grid\">
              <div class=\"card\">
                <h2>Сервисы</h2>
                <div id=\"services\">Загрузка...</div>
              </div>
              <div class=\"card\">
                <h2>Клиенты</h2>
                <div id=\"clients\">Загрузка...</div>
              </div>
            </div>
            <div class=\"card\" style=\"margin-top:24px\">
              <h2>История команд</h2>
              <div id=\"history\">Загрузка...</div>
            </div>
            <div class=\"card\" style=\"margin-top:24px\">
              <h2>Enrollment (TOFU)</h2>
              <div id=\"enrollments\">Загрузка...</div>
            </div>

            <script>
              async function fetchJSON(path, opts) {
                const res = await fetch(path, opts);
                if (!res.ok) throw new Error(await res.text());
                return await res.json();
              }

              async function loadServices() {
                const data = await fetchJSON('/api/services');
                const el = document.getElementById('services');
                const rows = Object.values(data).map(s => `
                  <tr>
                    <td><code>${s.name}</code></td>
                    <td class=\"${s.running === 'yes' ? 'ok' : 'bad'}\">${s.running}</td>
                    <td class=\"${s.healthy === 'yes' ? 'ok' : 'bad'}\">${s.healthy}</td>
                    <td>${s.pid}</td>
                    <td>
                      <button onclick=\"svcAction('restart','${s.name}')\">restart</button>
                      <button onclick=\"svcAction('stop','${s.name}')\">stop</button>
                      <button onclick=\"svcAction('start','${s.name}')\">start</button>
                    </td>
                  </tr>`).join('');
                el.innerHTML = `<table>
                  <thead><tr><th>name</th><th>running</th><th>healthy</th><th>pid</th><th>actions</th></tr></thead>
                  <tbody>${rows}</tbody>
                </table>`;
              }

              async function svcAction(action, name) {
                await fetchJSON(`/api/services/${action}/${name}`, { method: 'POST' });
                await loadServices();
              }

              async function loadClients() {
                const data = await fetchJSON('/api/clients');
                const el = document.getElementById('clients');
                el.innerHTML = data.map(c => `
                  <div class=\"row\">
                    <b>${c.hostname}</b> <code>(${c.id})</code> — ${c.status}
                    <div>
                      <input id=\"cmd_${c.id}\" placeholder=\"Команда\" />
                      <button onclick=\"sendCmd('${c.id}')\">Выполнить</button>
                      <button onclick=\"cancelCmd('${c.id}')\">Отменить</button>
                    </div>
                  </div>
                `).join('');
              }

              async function sendCmd(id) {
                const val = document.getElementById(`cmd_${id}`).value;
                if (!val) return;
                await fetchJSON(`/api/commands/${id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: val })});
                await loadHistory();
              }

              async function cancelCmd(id) {
                const cmdId = prompt('Введите command_id для отмены');
                if (!cmdId) return;
                const params = new URLSearchParams({ command_id: cmdId });
                await fetchJSON(`/api/commands/${id}/cancel?${params.toString()}`, { method: 'POST' });
                alert('Отмена отправлена');
              }

              async function loadEnrollments() {
                try {
                  const data = await fetchJSON('/api/enrollments/pending');
                  const el = document.getElementById('enrollments');
                  if (!data.length) { el.innerHTML = 'Нет ожидающих записей'; return; }
                  el.innerHTML = data.map(e => `
                    <div class=\"row\">
                      <code>${e.client_id || e.id || JSON.stringify(e)}</code>
                      <button onclick=\"approve('${e.client_id || e.id}')\">Approve</button>
                      <button onclick=\"reject('${e.client_id || e.id}')\">Reject</button>
                    </div>
                  `).join('');
                } catch (e) {
                  document.getElementById('enrollments').innerText = 'Недоступно (проверь ADMIN_TOKEN)';
                }
              }

              async function approve(id) {
                await fetchJSON(`/api/enrollments/${id}/approve`, { method: 'POST' });
                await loadEnrollments();
              }
              async function reject(id) {
                await fetchJSON(`/api/enrollments/${id}/reject`, { method: 'POST' });
                await loadEnrollments();
              }

              async function loadHistory() {
                try {
                  const items = await fetchJSON('/api/commands/history');
                  const el = document.getElementById('history');
                  if (!items || items.length === 0) { el.innerHTML = 'История пуста'; return; }
                  el.innerHTML = items.slice(-20).reverse().map(r => `
                    <div class="row">
                      <code>${r.command_id || r.id}</code> @ <b>${r.client_id}</b>
                      — <span>${r.success ? 'success' : 'failed'}</span>
                      ${r.result ? `<pre style="white-space:pre-wrap;background:#f9fafb;padding:6px;border-radius:6px">${String(r.result).substring(0,500)}</pre>`: ''}
                      ${r.error ? `<pre style="white-space:pre-wrap;background:#fff1f2;padding:6px;border-radius:6px">${String(r.error).substring(0,500)}</pre>`: ''}
                    </div>
                  `).join('');
                } catch(e) {
                  document.getElementById('history').innerText = 'Ошибка загрузки истории';
                }
              }

              async function tick() {
                await Promise.all([loadServices(), loadClients(), loadEnrollments(), loadHistory()]);
              }
              tick();
              setInterval(tick, 5000);
            </script>
          </body>
        </html>
        """
        return HTMLResponse(content=html)

    # --- Services ---
    @app.get("/api/services")
    async def services_status() -> JSONResponse:
        return JSONResponse(orchestrator.get_services_status())
    @app.get("/admin/api/services")
    async def services_status_compat() -> JSONResponse:
        return await services_status()

    @app.post("/api/services/restart/{name}")
    async def services_restart(name: str) -> JSONResponse:
        ok = orchestrator.restart(name)
        if not ok:
            raise HTTPException(status_code=404, detail="service not found")
        return JSONResponse({"message": "restarted", "name": name})
    @app.post("/admin/api/services/restart/{name}")
    async def services_restart_compat(name: str) -> JSONResponse:
        return await services_restart(name)

    @app.post("/api/services/stop/{name}")
    async def services_stop(name: str) -> JSONResponse:
        ok = orchestrator.stop(name)
        if not ok:
            raise HTTPException(status_code=404, detail="service not found")
        return JSONResponse({"message": "stopped", "name": name})
    @app.post("/admin/api/services/stop/{name}")
    async def services_stop_compat(name: str) -> JSONResponse:
        return await services_stop(name)

    @app.post("/api/services/start/{name}")
    async def services_start(name: str) -> JSONResponse:
        ok = orchestrator.start(name)
        if not ok:
            raise HTTPException(status_code=404, detail="service not found")
        return JSONResponse({"message": "started", "name": name})
    @app.post("/admin/api/services/start/{name}")
    async def services_start_compat(name: str) -> JSONResponse:
        return await services_start(name)

    # --- Clients proxy to client_manager ---
    @app.get("/api/clients")
    async def clients_list() -> JSONResponse:
        data = await asyncio.to_thread(_http_json, "GET", "/api/clients")
        # Обновим снапшот в БД
        def _upsert_clients(clients: list[dict[str, Any]]):
            with get_session() as db:  # type: Session
                for c in clients:
                    obj = db.get(Client, c.get("id"))
                    if obj is None:
                        obj = Client(id=c.get("id"))
                    obj.hostname = c.get("hostname")
                    obj.ip = c.get("ip")
                    obj.port = c.get("port")
                    obj.status = c.get("status")
                    # Преобразование ISO дат
                    def _parse(dt):
                        try:
                            return datetime.fromisoformat(dt) if dt else None
                        except Exception:
                            return None
                    from datetime import datetime
                    obj.connected_at = _parse(c.get("connected_at"))
                    obj.last_heartbeat = _parse(c.get("last_heartbeat"))
                    db.merge(obj)
        await asyncio.to_thread(_upsert_clients, data)
        return JSONResponse(data)

    @app.get("/admin/api/clients")
    async def clients_list_compat() -> JSONResponse:
        return await clients_list()

    @app.post("/api/commands/{client_id}")
    async def command_exec(client_id: str, payload: Dict[str, Any]) -> JSONResponse:
        # Сохраним команду как queued
        command_id: str | None = None
        if payload and isinstance(payload, dict):
            command_text = payload.get("command") or (str(payload.get("name")) + " " + str(payload.get("params")))
        else:
            command_text = None
        if command_text:
            from datetime import datetime
            def _prelog():
                with get_session() as db:
                    cid = f"cmd_{int(datetime.utcnow().timestamp())}"
                    log = CommandLog(id=cid, client_id=client_id, command=command_text, status="queued")
                    db.merge(log)
                    return cid
            command_id = await asyncio.to_thread(_prelog)

        data = await asyncio.to_thread(_http_json, "POST", f"/api/commands/{client_id}", body=payload)

        # Дообновим запись результатом, если знаем id
        if command_id and isinstance(data, dict):
            def _postlog():
                with get_session() as db:
                    log = db.get(CommandLog, command_id)
                    if log:
                        # Map fields from client_manager schema
                        success = data.get("success")
                        log.status = "success" if success else "failed"
                        log.stdout = data.get("result")
                        log.stderr = data.get("error")
                        log.exit_code = data.get("exit_code")
                        log.finished_at = __import__("datetime").datetime.utcnow()
                        db.add(log)
            await asyncio.to_thread(_postlog)

        return JSONResponse(data)

    @app.post("/admin/api/commands/{client_id}")
    async def command_exec_compat(client_id: str, payload: Dict[str, Any]) -> JSONResponse:
        return await command_exec(client_id, payload)

    @app.post("/api/commands/{client_id}/cancel")
    async def command_cancel(client_id: str, command_id: str) -> JSONResponse:
        # оригинальный endpoint ожидает body или query? используем query для простоты
        # прокинем как query в путь, внутри клиент-менеджера обработается из параметров
        path = f"/api/commands/{client_id}/cancel?" + urlencode({"command_id": command_id})
        data = await asyncio.to_thread(_http_json, "POST", path)
        return JSONResponse(data)

    @app.post("/admin/api/commands/{client_id}/cancel")
    async def command_cancel_compat(client_id: str, command_id: str) -> JSONResponse:
        return await command_cancel(client_id, command_id)

    # --- Enrollments proxy (requires ADMIN_TOKEN) ---
    def _admin_hdrs() -> Dict[str, str]:
        token = os.getenv("ADMIN_TOKEN", "")
        return {"Authorization": f"Bearer {token}"} if token else {}

    @app.get("/api/enrollments/pending")
    async def enrollments_pending() -> JSONResponse:
        data = await asyncio.to_thread(_http_json, "GET", "/api/enrollments/pending", headers=_admin_hdrs())
        return JSONResponse(data)
    @app.get("/admin/api/enrollments/pending")
    async def enrollments_pending_compat() -> JSONResponse:
        return await enrollments_pending()

    @app.post("/api/enrollments/{client_id}/approve")
    async def enroll_approve(client_id: str) -> JSONResponse:
        data = await asyncio.to_thread(_http_json, "POST", f"/api/enrollments/{client_id}/approve", headers=_admin_hdrs())
        return JSONResponse(data)
    @app.post("/admin/api/enrollments/{client_id}/approve")
    async def enroll_approve_compat(client_id: str) -> JSONResponse:
        return await enroll_approve(client_id)

    @app.post("/api/enrollments/{client_id}/reject")
    async def enroll_reject(client_id: str) -> JSONResponse:
        data = await asyncio.to_thread(_http_json, "POST", f"/api/enrollments/{client_id}/reject", headers=_admin_hdrs())
        return JSONResponse(data)
    @app.post("/admin/api/enrollments/{client_id}/reject")
    async def enroll_reject_compat(client_id: str) -> JSONResponse:
        return await enroll_reject(client_id)

    # --- Commands history/status proxy ---
    @app.get("/api/commands/history")
    async def commands_history() -> JSONResponse:
        data = await asyncio.to_thread(_http_json, "GET", "/api/commands/history")
        return JSONResponse(data)

    @app.get("/api/commands/{command_id}")
    async def command_result(command_id: str) -> JSONResponse:
        data = await asyncio.to_thread(_http_json, "GET", f"/api/commands/{command_id}")
        return JSONResponse(data)

    return app


