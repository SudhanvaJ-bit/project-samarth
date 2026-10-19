"""
scripts/record_demo.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Record the online demo, then prove it replays with NO API key.

    python scripts/record_demo.py              # record all samples, then verify
    python scripts/record_demo.py --verify     # only re-check existing recordings
    python scripts/record_demo.py --only arjun-dyslexia

WHAT IT DOES
1. Copies the vector index rag/chroma_db → demo/chroma_db, so the demo
   searches exactly the index the recordings were made with.
2. Runs the real pipeline (live Gemini, your key from .env) for each sample
   in demo/samples.json, with "today" frozen to today's date. Every model
   response and every search embedding is saved to demo/recordings/.
3. Starts a SEPARATE Python process with the API key removed and
   SAMARTH_LLM_MODE=demo, and replays every sample. Only samples that
   complete there are listed as "verified" in demo/manifest.json — and only
   verified samples are offered on the website.

Step 3 is the point: if it passes on your machine, the deployed demo cannot
need Gemini, because it runs the same check's code path.

Takes about a minute per sample (live Gemini). Uses your API quota once.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT      = Path(__file__).resolve().parent.parent
DEMO_DIR  = ROOT / "demo"
RECORDING = DEMO_DIR / "recordings"
MANIFEST  = DEMO_DIR / "manifest.json"
SAMPLES   = DEMO_DIR / "samples.json"


def load_samples(only=None) -> list:
    samples = json.loads(SAMPLES.read_text(encoding="utf-8"))["samples"]
    if only:
        samples = [s for s in samples if s["id"] in only]
        missing = set(only) - {s["id"] for s in samples}
        if missing:
            sys.exit(f"Unknown sample id(s): {', '.join(sorted(missing))}")
    return samples


def read_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_manifest(data: dict) -> None:
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_samples(samples: list) -> dict:
    """Run the pipeline for each sample in THIS process. Returns {id: error or None}."""
    sys.path.insert(0, str(ROOT))
    from agents.graph import run_iep_pipeline
    from models.student import StudentInput
    from rag.retriever import initialize_retriever, get_retriever_stats

    initialize_retriever(docs_dir=str(ROOT / "rag" / "documents"))
    stats = get_retriever_stats()
    if not stats.get("ready") or not stats.get("total_chunks"):
        sys.exit("The vector index is empty. Build it first: python rag/build_index.py")

    results = {}
    for i, sample in enumerate(samples, 1):
        name = sample["student"]["student_name"]
        print(f"\n[{i}/{len(samples)}] {sample['id']} — {name}", flush=True)
        started = time.time()
        try:
            iep_id = f"demo-{sample['id']}"
            # Same validation and conversion as POST /iep/generate
            student = StudentInput(**sample["student"]).to_pipeline_input(iep_id)
            state   = run_iep_pipeline(student, iep_id)
            status = str(state.get("workflow_status", ""))
            if "completed" not in status.lower():
                raise RuntimeError(f"pipeline ended as {status}: {state.get('error_log')}")
            results[sample["id"]] = None
            print(f"   ✅ completed in {time.time() - started:.0f}s", flush=True)
        except Exception as e:
            results[sample["id"]] = str(e)[:300]
            print(f"   ❌ {str(e)[:300]}", flush=True)
    return results


def verify_in_clean_process(sample_ids: list) -> dict:
    """Replay in a fresh process with no API key and demo mode on."""
    env = dict(os.environ)
    env["SAMARTH_LLM_MODE"] = "demo"
    env["SAMARTH_DEMO_DIR"] = str(DEMO_DIR)
    env["GOOGLE_API_KEY"]   = ""          # an empty value stops .env from supplying it
    env.pop("SAMARTH_FIXED_DATE", None)   # demo mode must get the date from the manifest
    env.pop("SAMARTH_RECORDINGS_DIR", None)
    # Windows prints in its own encoding (cp1252) unless told otherwise;
    # force UTF-8 so log lines with "—" or emoji can be read back.
    env["PYTHONUTF8"]       = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    with tempfile.TemporaryDirectory() as tmp:   # PDFs land here, not in outputs/
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--_child", *sample_ids],
            cwd=tmp, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    marker = "@@RESULT@@"
    for line in stdout.splitlines():
        if line.startswith(marker):
            return json.loads(line[len(marker):])
    print(stdout[-3000:])
    print(stderr[-3000:])
    sys.exit("The verification process crashed — see the output above.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("━")[0])
    parser.add_argument("--verify", action="store_true", help="only verify existing recordings")
    parser.add_argument("--only", nargs="+", metavar="ID", help="sample ids to record")
    parser.add_argument("--_child", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # ── Child process: replay in demo mode, report back ──
    if args._child is not None:
        samples = [s for s in load_samples() if s["id"] in set(args._child)]
        results = run_samples(samples)
        print("@@RESULT@@" + json.dumps(results), flush=True)
        return

    manifest = read_manifest()

    # ── Record ──
    if not args.verify:
        # Load .env now so the key check below sees it
        sys.path.insert(0, str(ROOT))
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        if not os.getenv("GOOGLE_API_KEY"):
            sys.exit("GOOGLE_API_KEY is not set in .env — recording needs the real API.")

        today = date.today().isoformat()
        samples = load_samples(args.only)

        if args.only and manifest.get("recorded_on") not in (None, "", today):
            sys.exit(
                f"The existing demo was recorded on {manifest['recorded_on']}. Every sample "
                f"must share one date, so re-record all of them (run without --only)."
            )

        # Must be set before any agent module is imported
        os.environ["SAMARTH_LLM_MODE"]       = "live"
        os.environ["SAMARTH_RECORDINGS_DIR"] = str(RECORDING)
        os.environ["SAMARTH_FIXED_DATE"]     = today

        import agents.model_config as mc
        if Path(mc._RECORD_DIR).resolve() != RECORDING.resolve() or mc.LLM_MODE != "live":
            sys.exit("Agent settings were loaded before the recording settings were applied — "
                     "recordings would go to the wrong folder. Run this script directly.")

        if not args.only:
            shutil.rmtree(RECORDING, ignore_errors=True)
            src = ROOT / "rag" / "chroma_db"
            if not src.is_dir():
                sys.exit("rag/chroma_db not found. Build it first: python rag/build_index.py")
            shutil.rmtree(DEMO_DIR / "chroma_db", ignore_errors=True)
            shutil.copytree(src, DEMO_DIR / "chroma_db")
            print("Copied rag/chroma_db → demo/chroma_db")
        RECORDING.mkdir(parents=True, exist_ok=True)

        print(f"Recording {len(samples)} sample(s) with live Gemini, date frozen to {today}…")
        recorded = run_samples(samples)
        failed = {k: v for k, v in recorded.items() if v}
        if failed:
            print(f"\n⚠️  {len(failed)} sample(s) failed to record: {', '.join(failed)}. "
                  f"Run again later with --only {' '.join(failed)}")

        manifest = {"recorded_on": today,
                    "verified": [] if not args.only else manifest.get("verified", [])}
        write_manifest(manifest)

    # ── Verify ──
    all_ids = [s["id"] for s in load_samples()]
    print(f"\nVerifying {len(all_ids)} sample(s) in a separate process: no API key, demo mode…")
    results = verify_in_clean_process(all_ids)

    verified = [sid for sid in all_ids if results.get(sid) is None]
    manifest["verified"] = verified
    write_manifest(manifest)

    print("\n" + "=" * 60)
    for sid in all_ids:
        err = results.get(sid)
        print(f"  {'✅' if err is None else '❌'} {sid}" + ("" if err is None else f" — {err[:120]}"))
    print("=" * 60)
    print(f"{len(verified)}/{len(all_ids)} sample(s) replay with no API key "
          f"(recorded on {manifest.get('recorded_on')}).")
    print("Only these are offered on the website. Commit the demo/ folder to deploy them.")
    if len(verified) < len(all_ids):
        sys.exit(1)


if __name__ == "__main__":
    main()
