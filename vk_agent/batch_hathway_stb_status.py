"""
Standalone Hathway STB status checker (single login, many audits).

This reuses the same Playwright + portal scraping flow as the Telegram bot's
`/multi` mode:
- one `hathway_login_once(...)` call
- then many `audit_hathway_subscriber(page, stb_id)` calls on the same page
- finally `close_hathway_browser(...)` once at the end.
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterable, List

from hathway_portal import (
    audit_hathway_subscriber,
    close_hathway_browser,
    hathway_login_once,
    launch_hathway_browser,
    looks_like_hathway_stb_id,
)


def _split_stb_text(text: str) -> List[str]:
    if not text:
        return []
    # Accept commas, whitespace, and newlines.
    raw = (
        text.replace(",", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
    )
    parts = [p.strip() for p in raw.split(" ") if p.strip()]
    return parts


def _read_stb_file(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def parse_stbs(args: argparse.Namespace) -> List[str]:
    stbs: List[str] = []

    if args.stbs:
        for chunk in args.stbs:
            stbs.extend(_split_stb_text(chunk))

    if args.file:
        stbs.extend(_read_stb_file(args.file))

    if not stbs and not sys.stdin.isatty():
        stbs.extend(_split_stb_text(sys.stdin.read()))

    # Preserve order, remove duplicates.
    seen = set()
    out: List[str] = []
    for s in stbs:
        s2 = (s or "").replace("\ufeff", "").strip().upper()
        if not s2 or s2 in seen:
            continue
        seen.add(s2)
        out.append(s2)
    return out


def format_one(stb_id: str, audit: dict) -> str:
    if not (audit or {}).get("success"):
        err = (audit or {}).get("error") or ""
        err_l = err.lower()
        # Bot logic messages come from `_hathway_search_portal_user_message(...)`.
        if "terminated" in err_l and ("does not exist" in err_l or "not exist" in err_l or "or does not exist" in err_l):
            return f"{stb_id}: terminated / not found (VC terminated or does not exist)"
        if "stb is terminated" in err_l or "vc is terminated" in err_l or ("terminated" in err_l and "does not exist" in err_l):
            return f"{stb_id}: terminated / not found (VC terminated or does not exist)"
        if "not with your lco" in err_l or "lco id" in err_l:
            return f"{stb_id}: not in your LCO account (STB exists but no access)"
        # Fallback: keep previous generic message.
        return f"{stb_id}: no package present ({err})".strip()

    if audit.get("is_online"):
        valid_upto = (audit.get("expiry") or audit.get("hathway_valid_upto") or "").strip()
        if not valid_upto:
            valid_upto = "N/A"
        # Hathway portal normalizes "STB/Mac ID" into audit["mac"].
        stb_mac_id = (audit.get("mac") or audit.get("stb_no") or "").strip()
        if not stb_mac_id:
            stb_mac_id = "N/A"
        pack_name = (
            (audit.get("hathway_plan_name") or audit.get("hathway_scheme_name") or "").strip()
        )
        if not pack_name:
            pack_name = "N/A"
        lco_price = (
            (audit.get("hathway_bot_lco_display") or "").strip()
            or (audit.get("hathway_plan_lco_price") or "").strip()
            or (audit.get("hathway_total_lco_price") or "").strip()
        )
        if not lco_price:
            lco_price = "N/A"
        return (
            f"{stb_id}: Active — STB/Mac: {stb_mac_id}, Pack: {pack_name}, Valid upto: {valid_upto}, "
            f"LCO Price: {lco_price}"
        )

    # Inactive path: treat as "no package present" (per your requirement).
    return f"{stb_id}: no package present"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Hathway STB status for many IDs (single login)."
    )
    parser.add_argument(
        "stb_ids",
        nargs="*",
        help="STB/VC ids (N+11 digits or T+12 digits).",
    )
    parser.add_argument(
        "--file",
        help="Text file containing one STB/VC id per line (optional).",
    )
    parser.add_argument(
        "--account-id",
        default=None,
        help="Optional Hathway account id from HATHWAY_ACCOUNTS_FILE.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (default is headed).",
    )
    parser.add_argument(
        "--stbs",
        nargs="*",
        help="Alternative: provide STB ids as a single string or multiple chunks.",
    )

    args = parser.parse_args()

    # Support both positional `stb_ids` and optional `--stbs`.
    args.stbs = (args.stb_ids or []) + (args.stbs or [])
    stbs = parse_stbs(args)
    if not stbs:
        parser.error("Provide STB ids as args, --file, or via stdin.")

    # Basic validation warning only; we still try audits even if it doesn't match.
    invalid = [s for s in stbs if not looks_like_hathway_stb_id(s)]
    if invalid:
        print(
            f"Warning: {len(invalid)} id(s) don't match expected Hathway STB/VC formats: "
            + ", ".join(invalid[:10])
            + ("..." if len(invalid) > 10 else "")
        )

    playwright = browser = page = None
    try:
        playwright, browser, page = launch_hathway_browser(headless=bool(args.headless))
        if not hathway_login_once(page, account_id=args.account_id):
            print("Login failed. Check credentials and CAPTCHA (HATHWAY_USER/HATHWAY_PASS).")
            return 2

        for idx, stb_id in enumerate(stbs, start=1):
            try:
                audit = audit_hathway_subscriber(page, stb_id)
            except Exception as exc:
                # Keep going: one bad audit shouldn't stop the batch.
                print(f"{stb_id}: no package present (audit exception: {exc})")
                continue
            print(format_one(stb_id, audit))

            # Small pacing to keep portal UI responsive for long lists.
            # (Bot uses fixed sleeps too; this just avoids hammering.)
            if idx % 5 == 0:
                try:
                    page.wait_for_timeout(500)
                except Exception:
                    pass

        return 0
    finally:
        if playwright is not None and browser is not None:
            try:
                close_hathway_browser(playwright, browser)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

