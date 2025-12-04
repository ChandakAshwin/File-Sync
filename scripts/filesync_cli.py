#!/usr/bin/env python3
"""
A tiny CLI to interact with Wokelo File Sync locally.

Usage examples:
  python scripts/filesync_cli.py auth box-start
  python scripts/filesync_cli.py ccpair create --credential-id 1 --name "My Box" --connector-config '{"folder_ids":["0"],"include_exts":["pdf","docx"],"max_size_mb":50}'
  python scripts/filesync_cli.py sync backfill --ccpair 1
  python scripts/filesync_cli.py search --q "policy"

Notes:
- This CLI calls the local FastAPI server at http://localhost:8000.
- For complex JSON in --connector-config, prefer using single quotes around the entire JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
import requests

API_BASE = "http://localhost:8000"


def cmd_auth_box_start(args: argparse.Namespace) -> int:
    url = f"{API_BASE}/auth/box/start"
    params = {}
    if args.desired_return_url:
        params["desired_return_url"] = args.desired_return_url
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    print(data["redirect_url"])  # the authorization URL to open in browser
    return 0


def cmd_ccpair_create(args: argparse.Namespace) -> int:
    url = f"{API_BASE}/ccpairs/create"
    payload = {
        "connector_name": "box",
        "connector_source": "box",
        "credential_id": args.credential_id,
        "name": args.name,
    }
    if args.connector_config:
        try:
            payload["connector_config"] = json.loads(args.connector_config)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON for --connector-config: {e}", file=sys.stderr)
            return 2
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


def cmd_sync_backfill(args: argparse.Namespace) -> int:
    url = f"{API_BASE}/sync/{args.ccpair}/backfill"
    r = requests.post(url, timeout=15)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    url = f"{API_BASE}/api/v1/search"
    params = {"q": args.q, "size": args.size}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="filesync")
    sub = parser.add_subparsers(dest="cmd")

    p_auth = sub.add_parser("auth")
    sub_auth = p_auth.add_subparsers(dest="auth_cmd")
    p_auth_box = sub_auth.add_parser("box-start")
    p_auth_box.add_argument("--desired-return-url", dest="desired_return_url")
    p_auth_box.set_defaults(func=cmd_auth_box_start)

    p_cc = sub.add_parser("ccpair")
    sub_cc = p_cc.add_subparsers(dest="cc_cmd")
    p_cc_create = sub_cc.add_parser("create")
    p_cc_create.add_argument("--credential-id", type=int, required=True)
    p_cc_create.add_argument("--name", type=str, default=None)
    p_cc_create.add_argument("--connector-config", type=str, default=None)
    p_cc_create.set_defaults(func=cmd_ccpair_create)

    p_sync = sub.add_parser("sync")
    sub_sync = p_sync.add_subparsers(dest="sync_cmd")
    p_sync_backfill = sub_sync.add_parser("backfill")
    p_sync_backfill.add_argument("--ccpair", type=int, required=True)
    p_sync_backfill.set_defaults(func=cmd_sync_backfill)

    p_search = sub.add_parser("search")
    p_search.add_argument("--q", required=True)
    p_search.add_argument("--size", type=int, default=10)
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except requests.HTTPError as e:
        print(f"HTTP error: {e}\n{e.response.text if e.response is not None else ''}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
