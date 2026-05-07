"""
Windows PC local_agent combined runner.
WS agent + UI server in same process — default_store shared.
UI server port: 18082
"""
import sys, threading, logging
from pathlib import Path

REPO = str(Path(__file__).resolve().parent)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger(__name__)


def run_ui_thread():
    from local_agent.user_present_ui_server import run_server
    from local_agent.user_present_state_store import default_store
    log.info("UI server starting on 127.0.0.1:18082")
    run_server(host="127.0.0.1", port=18082, store=default_store)


def run_ws_agent():
    from local_agent import desktop_config as _desk_cfg
    from local_agent import token_store as _ts
    from local_agent import config, websocket_client

    cfg = _desk_cfg.load_config()
    agent_id = cfg.agent_id
    server_url = cfg.server_url or config.SERVER_BASE_URL

    device_token = _ts.load_device_token(server_url, agent_id)
    if not device_token:
        log.error("device_token 없음 — 등록을 먼저 완료하세요.")
        sys.exit(1)

    log.info("WS agent starting | agent_id=%s server_url=%s", agent_id, server_url)

    import os
    os.environ["HAEHAN_AGENT_WS_ENABLED"] = "true"
    os.environ["HAEHAN_AGENT_SERVER"] = server_url
    # config reload after env set
    import importlib
    importlib.reload(config)
    websocket_client.connect(agent_id=agent_id, device_token=device_token)


if __name__ == "__main__":
    t_ui = threading.Thread(target=run_ui_thread, daemon=True, name="ui-server")
    t_ui.start()
    run_ws_agent()
