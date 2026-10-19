"""
scripts/import_file_drafts.py — copy old file drafts into the database.

IEP drafts used to be saved as drafts/{iep_id}.json. They now live in the
iep_drafts table. Run this once on a machine that has old drafts:

    python scripts/import_file_drafts.py

SAFE TO RE-RUN
- Copies only: the JSON files are left untouched.
- Skips drafts already in the database, drafts with no owner (made before
  login existed) and drafts whose owner account no longer exists.
- Keeps each draft's original created/updated times, so "My IEPs" keeps
  its order.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session                       # noqa: E402

from app.db import DATABASE_URL, IEPDraft, User, engine, init_db   # noqa: E402

DRAFTS_DIR = Path("./drafts")


def _utc(text: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(text))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def main() -> None:
    init_db()
    files = sorted(DRAFTS_DIR.glob("*.json"))
    print(f"Database: {DATABASE_URL.split('@')[-1]}")   # never print a password
    print(f"Found {len(files)} file draft(s) in {DRAFTS_DIR.resolve()}")

    imported = skipped = 0
    with Session(engine) as session:
        for path in files:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  skip {path.name}: unreadable ({e})")
                skipped += 1
                continue

            iep_id   = str(record.get("iep_id") or path.stem)
            owner_id = record.get("owner_id")
            if owner_id is None:
                print(f"  skip {iep_id}: no owner (created before login)")
                skipped += 1
                continue
            if session.get(User, owner_id) is None:
                print(f"  skip {iep_id}: owner account {owner_id} not found")
                skipped += 1
                continue
            if session.get(IEPDraft, iep_id) is not None:
                skipped += 1
                continue

            session.add(IEPDraft(
                iep_id=iep_id, owner_id=owner_id, record=record,
                created_at=_utc(record.get("created_at", "")),
                updated_at=_utc(record.get("updated_at", "")),
            ))
            imported += 1
        session.commit()

    print(f"Imported {imported}, skipped {skipped}. The JSON files were not changed.")


if __name__ == "__main__":
    main()
