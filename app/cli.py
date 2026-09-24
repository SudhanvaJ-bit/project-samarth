"""
app/cli.py — account management from the command line.

There is no public sign-up, so the FIRST admin account has to be created
here. After that, an admin can also create accounts through the API.

Run from the project root (D:\\SAMARTH) with the venv active:

    python -m app.cli create-user --email admin@samarth.in --name "Admin" --role admin
    python -m app.cli create-user --email priya@school.in --name "Priya Nair"
    python -m app.cli list-users
    python -m app.cli set-password --email priya@school.in

Passwords are typed at a hidden prompt, never passed as arguments — anything
on the command line is saved in your shell history.
"""

import argparse
import getpass
import sys

from sqlmodel import Session, select

from app.db import User, engine, init_db
from app.services.auth import create_user, get_user_by_email, normalise_email, set_password


def _prompt_password() -> str:
    first  = getpass.getpass("Password (min 8 characters): ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        sys.exit("✗ Passwords do not match.")
    return first


def cmd_create_user(args) -> None:
    password = _prompt_password()
    with Session(engine) as session:
        try:
            user = create_user(session, args.email, args.name, password, args.role)
        except ValueError as e:
            sys.exit(f"✗ {e}")
    print(f"✓ Created {user.role} account: {user.email} (id {user.id})")


def cmd_list_users(_args) -> None:
    with Session(engine) as session:
        users = session.exec(select(User).order_by(User.created_at)).all()
    if not users:
        print("No accounts yet. Create an admin with: python -m app.cli create-user --role admin ...")
        return
    print(f"{'ID':<4} {'ROLE':<9} {'ACTIVE':<7} {'EMAIL':<32} NAME")
    for u in users:
        print(f"{u.id:<4} {u.role:<9} {'yes' if u.is_active else 'no':<7} {u.email:<32} {u.full_name}")


def cmd_set_password(args) -> None:
    with Session(engine) as session:
        try:
            user = get_user_by_email(session, normalise_email(args.email))
        except ValueError as e:
            sys.exit(f"✗ {e}")
        if user is None:
            sys.exit("✗ No account with that email.")
        password = _prompt_password()
        try:
            set_password(session, user, password)
        except ValueError as e:
            sys.exit(f"✗ {e}")
    print(f"✓ Password updated for {args.email}")


def main() -> None:
    init_db()
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="SAMARTH accounts")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-user", help="Create an account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True, help="Full name, in quotes if it has spaces")
    p.add_argument("--role", default="educator", choices=["educator", "admin"])
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("list-users", help="List all accounts")
    p.set_defaults(func=cmd_list_users)

    p = sub.add_parser("set-password", help="Reset an account's password")
    p.add_argument("--email", required=True)
    p.set_defaults(func=cmd_set_password)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()