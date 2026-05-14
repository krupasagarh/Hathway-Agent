"""
Multi-operator Hathway partner portal credentials.

Single account: HATHWAY_USER / HATHWAY_PASS in .env.

Multiple accounts: HATHWAY_ACCOUNTS_FILE → JSON array of
{"id": "branch_a", "user": "...", "password": "..."}.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _abs_path(p: str) -> str:
    p = (p or "").strip()
    if not p:
        return ""
    if os.path.isabs(p):
        return p
    return os.path.normpath(os.path.join(ROOT_DIR, p))


def _read_json_array(path: str) -> List[Dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        rid = (row.get("id") or row.get("name") or "").strip()
        user = (row.get("user") or row.get("username") or "").strip()
        pw = (row.get("password") or row.get("pass") or "").strip()
        if not rid or not user or not pw:
            continue
        out.append({"id": rid, "user": user, "password": pw})
    return out


def _merge_default_from_env(
    file_accounts: List[Dict[str, Any]],
    env_user: Optional[str],
    env_pass: Optional[str],
) -> List[Dict[str, Any]]:
    u = (env_user or "").strip()
    p = (env_pass or "").strip()
    if not u or not p:
        return list(file_accounts)
    ids = {a["id"] for a in file_accounts}
    if "default" in ids:
        return list(file_accounts)
    merged = [{"id": "default", "user": u, "password": p}]
    merged.extend(file_accounts)
    return merged


def load_hathway_accounts() -> List[Dict[str, Any]]:
    path = _abs_path(os.getenv("HATHWAY_ACCOUNTS_FILE", "") or "")
    from_file = _read_json_array(path) if path else []
    if from_file:
        return _merge_default_from_env(from_file, os.getenv("HATHWAY_USER"), os.getenv("HATHWAY_PASS"))
    u = (os.getenv("HATHWAY_USER") or "").strip()
    p = (os.getenv("HATHWAY_PASS") or "").strip()
    if u and p:
        return [{"id": "default", "user": u, "password": p}]
    return []


def _pick_account(accounts: List[Dict[str, Any]], account_id: Optional[str], default_env: str) -> Dict[str, Any]:
    if not accounts:
        raise ValueError("No operator accounts configured.")
    aid = (account_id or os.getenv(default_env) or "").strip()
    if aid:
        for a in accounts:
            if a["id"] == aid:
                return a
        raise ValueError(f'Unknown account id {aid!r}. Known: {", ".join(a["id"] for a in accounts)}')
    return accounts[0]


def get_hathway_credentials(account_id: Optional[str] = None) -> Tuple[str, str, str]:
    accounts = load_hathway_accounts()
    a = _pick_account(accounts, account_id, "HATHWAY_DEFAULT_ACCOUNT_ID")
    return a["user"], a["password"], a["id"]


def list_hathway_account_ids() -> List[str]:
    return [a["id"] for a in load_hathway_accounts()]
