"""Operations commands for a real deployment.

    python -m app.manage prepare                  # at start-up: demo data (demo mode only), then the first admin
    python -m app.manage create-admin --username U --name "Full Name"
    python -m app.manage reset-password --username U
    python -m app.manage new-data-key            # a DATA_KEY for encrypting patients' phone numbers

``prepare`` creates the first admin from INITIAL_ADMIN_USERNAME / INITIAL_ADMIN_PASSWORD (and optionally
INITIAL_ADMIN_NAME) when no active admin has a password yet, so a host without shell access (Render's free
plan) can be set up from its environment settings. That password must be changed at the first sign-in.
The other commands print a temporary password once.
"""

import argparse
import base64
import os
import secrets
import sys

from sqlalchemy import select

from app.api.passwords import check_new_password, hash_password, temporary_password
from app.config import get_settings
from app.db.models import AppUser
from app.db.session import session_scope
from app.timeutil import now_ist
from app.tools.accounts import USERNAME_RE
from app.tools.audit import record_audit
from app.tools.errors import ToolError
from app.tools.permissions import Actor

SYSTEM = Actor(user_id=None, role="system")


def _admin_with_password(db) -> bool:
    return (
        db.scalars(
            select(AppUser.id).where(
                AppUser.role == "admin", AppUser.active.is_(True), AppUser.password_hash.is_not(None)
            )
        ).first()
        is not None
    )


def ensure_admin(db, username: str, password: str, name: str) -> str:
    """Create (or give a password to) the first admin. Returns what happened."""
    if _admin_with_password(db):
        return "an admin with a password exists; nothing changed"
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        raise SystemExit("INITIAL_ADMIN_USERNAME: 3-30 lowercase letters, digits, dots, dashes or underscores")
    try:
        check_new_password(password)
    except ToolError as err:
        raise SystemExit(f"INITIAL_ADMIN_PASSWORD: {err}") from None
    user = db.scalars(select(AppUser).where(AppUser.username == username)).first()
    if user is not None and user.role != "admin":
        raise SystemExit(f"{username!r} exists and is not an admin account")
    if user is None:
        user = AppUser(username=username, display_name=name, role="admin", credentials_version=0)
        db.add(user)
    user.password_hash = hash_password(password)
    user.active = True
    user.must_change_password = True  # the password sat in the host's settings; replace it
    user.credentials_version += 1
    db.flush()
    record_audit(db, SYSTEM, "bootstrap_admin", {"username": username}, {"ok": True}, now_ist())
    return f"admin {username!r} ready; the password must be changed at the first sign-in"


def prepare() -> None:
    settings = get_settings()
    if settings.demo_mode:
        from simulator.__main__ import main as simulator_main

        simulator_main(["seed", "--if-empty"])
        from simulator.seed import ensure_demo_profile

        with session_scope() as db:
            if ensure_demo_profile(db):
                print("Added or updated the demo hospital's details.")
    username, password = os.environ.get("INITIAL_ADMIN_USERNAME"), os.environ.get("INITIAL_ADMIN_PASSWORD")
    if username and password:
        with session_scope() as db:
            print(ensure_admin(db, username, password, os.environ.get("INITIAL_ADMIN_NAME") or "Administrator"))
    elif not settings.demo_mode:
        with session_scope() as db:
            if not _admin_with_password(db):
                print("No admin can sign in yet: set INITIAL_ADMIN_USERNAME and INITIAL_ADMIN_PASSWORD.")


def _temporary(db, username: str, name: str | None, create: bool) -> str:
    username = username.strip().lower()
    user = db.scalars(select(AppUser).where(AppUser.username == username)).first()
    if create:
        if user is not None:
            raise SystemExit(f"{username!r} already exists")
        if not USERNAME_RE.match(username):
            raise SystemExit("usernames are 3-30 lowercase letters, digits, dots, dashes or underscores")
        user = AppUser(username=username, display_name=name or username, role="admin", credentials_version=0)
        db.add(user)
    elif user is None:
        raise SystemExit(f"there is no account {username!r}")
    password = temporary_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.active = True
    user.credentials_version += 1
    db.flush()
    tool = "create_admin" if create else "reset_account_password"
    record_audit(db, SYSTEM, tool, {"username": username}, {"ok": True}, now_ist())
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    create = sub.add_parser("create-admin")
    create.add_argument("--username", required=True)
    create.add_argument("--name")
    reset = sub.add_parser("reset-password")
    reset.add_argument("--username", required=True)
    sub.add_parser("new-data-key")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare()
        return 0
    if args.command == "new-data-key":
        print(base64.b64encode(secrets.token_bytes(32)).decode())
        return 0
    with session_scope() as db:
        password = _temporary(db, args.username, getattr(args, "name", None), args.command == "create-admin")
    print(f"Temporary password for {args.username}: {password}\nIt must be changed at the first sign-in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
