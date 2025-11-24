#!/usr/bin/env python3
"""
Ядро-оркестратор: управляет запуском и мониторингом сервисов проекта
Запускает auth_service, api_gateway и client_manager, следит за их health,
перезапускает при сбоях, обеспечивает корректное завершение.
"""

import os
import sys
import time
import threading
import os
import uvicorn
from .admin_app import create_admin_app
import signal
from .services import Orchestrator


def main() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    orch = Orchestrator(project_root=project_root)

    def handle_signal(signum, frame):
        print("\n🔻 Получен сигнал остановки, завершаем все сервисы...")
        orch.stop_all(graceful=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if not os.getenv("CORE_DISABLE_ORCHESTRATOR"):
        print("🚦 Старт ядра-оркестратора...")
        orch.start_all()
    else:
        print("⏸ Оркестратор отключён (CORE_DISABLE_ORCHESTRATOR=1)")

    # Запуск админ-панели (FastAPI) на 127.0.0.1:11000
    app = create_admin_app(orch)

    def run_admin():
        uvicorn.run(app, host="0.0.0.0", port=11000, log_level="info")

    threading.Thread(target=run_admin, daemon=True).start()

    # Блокируем основной поток, пока не попросят остановиться
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_signal(signal.SIGINT, None)


if __name__ == "__main__":
    main()

