"""
Append-only JSONL log of STB / VC requests (Hathway agent).

Configure with BOT_REQUEST_LOG_PATH or default <agent_root>/logs/bot_requests.jsonl.
"""

import json
import os
import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def default_request_log_path():
    return os.path.join(_ROOT_DIR, "logs", "bot_requests.jsonl")


def request_log_path():
    p = (os.getenv("BOT_REQUEST_LOG_PATH") or "").strip()
    if p:
        return os.path.abspath(p)
    return default_request_log_path()


def log_bot_request(*, action, identifier, chat_id=None):
    ident = (identifier or "").strip()
    if not ident:
        return
    path = request_log_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "portal": "hathway",
        "action": action,
        "identifier": ident[:512],
    }
    if chat_id is not None:
        rec["chat_id"] = chat_id
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
