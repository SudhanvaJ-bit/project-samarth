"""
scripts/cleanup_legacy.py — remove IEPs created before login existed.

Those drafts have no owner, so no account can see them. This deletes:
  - drafts/*.json with no owner_id
  - outputs/*.pdf not referenced by any remaining (owned) draft

It does NOT touch:
  - .llm_recordings/     (replay recordings — regenerating stays free)
  - .extraction_cache/   (cached PDF extractions)
  - samarth.db           (user accounts)

SAFE BY DEFAULT: without --delete it only prints what it WOULD remove.

    python scripts/cleanup_legacy.py            # preview
    python scripts/cleanup_legacy.py --delete   # actually delete
"""

import argparse
import json
from pathlib import Path

DRAFTS_DIR  = Path("./drafts")
OUTPUTS_DIR = Path("./outputs")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove pre-authentication IEPs")
    parser.add_argument("--delete", action="store_true",
                        help="Actually delete. Without this flag, nothing is removed.")
    args = parser.parse_args()

    orphan_drafts, kept_pdf_names = [], set()

    for path in sorted(DRAFTS_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            orphan_drafts.append(path)          # unreadable → treat as legacy
            continue
        if record.get("owner_id") is None:
            orphan_drafts.append(path)
        elif record.get("pdf_path"):
            kept_pdf_names.add(Path(record["pdf_path"]).name)

    orphan_pdfs = [p for p in sorted(OUTPUTS_DIR.glob("*.pdf")) if p.name not in kept_pdf_names]

    print(f"Drafts without an owner : {len(orphan_drafts)}")
    for p in orphan_drafts:
        print(f"   {p}")
    print(f"PDFs not linked to an owned draft : {len(orphan_pdfs)}")
    for p in orphan_pdfs:
        print(f"   {p}")
    print(f"Owned drafts kept       : "
          f"{len(list(DRAFTS_DIR.glob('*.json'))) - len(orphan_drafts)}")

    if not (orphan_drafts or orphan_pdfs):
        print("\nNothing to clean up.")
        return

    if not args.delete:
        print("\nPreview only — nothing deleted. Re-run with --delete to remove these files.")
        return

    for p in orphan_drafts + orphan_pdfs:
        p.unlink()
    print(f"\n✓ Deleted {len(orphan_drafts)} draft(s) and {len(orphan_pdfs)} PDF(s).")
    print("  Replay recordings and extraction cache were kept.")


if __name__ == "__main__":
    main()