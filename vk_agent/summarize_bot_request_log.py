"""Summarize Hathway agent request log (JSONL). Run: python summarize_bot_request_log.py"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from request_log import default_request_log_path, request_log_path  # noqa: E402


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description='Summarize bot_requests JSONL (Hathway agent).')
    ap.add_argument('--file', '-f', help='Log file path')
    ap.add_argument('--since-hours', type=float, metavar='H', help='Only last H hours (UTC)')
    ap.add_argument('--raw', type=int, metavar='N', help='Print last N raw lines')
    args = ap.parse_args()

    path = (
        os.path.abspath(args.file.strip())
        if (args.file or '').strip()
        else request_log_path()
    )
    if not os.path.isfile(path):
        alt = default_request_log_path()
        print(f'No log file at:\n  {path}')
        if path != alt:
            print(f'(default would be:\n  {alt})')
        sys.exit(1)

    if args.raw is not None:
        n = max(1, args.raw)
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines[-n:]:
            print(line.rstrip('\n'))
        return

    cutoff = None
    if args.since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=args.since_hours)

    counts = Counter()
    skipped = 0
    total = 0

    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if cutoff is not None:
                ts = _parse_ts(rec.get('ts', ''))
                if ts is None or ts < cutoff:
                    continue
            ident = (rec.get('identifier') or '').strip()
            if not ident:
                skipped += 1
                continue
            counts[ident] += 1

    filter_note = f' (last {args.since_hours:g} h, UTC)' if args.since_hours is not None else ''
    print(f'Hathway agent request log: {path}{filter_note}\n')
    print(f'Total: {sum(counts.values())} request(s)')
    for ident, n in counts.most_common():
        print(f'  {n}x  {ident}')
    if not counts:
        print('  (none)')
    if skipped:
        print(f'\nSkipped: {skipped} (lines read: {total})')


if __name__ == '__main__':
    main()
