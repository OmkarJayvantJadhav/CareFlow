"""Command line for the hospital simulator.

python -m simulator seed [--if-empty]       load the fictional hospital and upcoming bookings
python -m simulator reset                   demo reset: wipe operational data and reseed
python -m simulator replay-day [--date D]   simulate one full OPD day and check its invariants
python -m simulator history --days N        replay the N days before --end (training data)
"""

import argparse
import json
import sys
import time as wallclock
from contextlib import nullcontext
from datetime import date, timedelta

from app.config import get_settings
from app.db.session import session_scope
from app.queue.predictions import predictions_disabled
from app.safety.privacy import install_log_masking
from app.timeutil import now_ist
from simulator.day import history_days, replay_day
from simulator.seed import SEED_DAYS_AHEAD, is_seeded, reset_demo, seed_all, top_up_slots
from simulator.validate import validate_day


def _date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    install_log_masking()
    parser = argparse.ArgumentParser(prog="python -m simulator", description="CareFlow synthetic hospital simulator")
    parser.add_argument("--seed", type=int, default=get_settings().simulator_seed)
    sub = parser.add_subparsers(dest="command", required=True)
    seed_cmd = sub.add_parser("seed", help="load seed data")
    seed_cmd.add_argument("--if-empty", action="store_true", help="do nothing if the database is already seeded")
    sub.add_parser("reset", help="demo reset: truncate operational tables and reseed")
    replay = sub.add_parser("replay-day", help="simulate a full OPD day")
    replay.add_argument("--date", type=_date, default=None, help="YYYY-MM-DD (default: yesterday)")
    history = sub.add_parser("history", help="replay several past days")
    history.add_argument("--days", type=int, default=90)
    history.add_argument("--end", type=_date, default=None, help="first day NOT replayed (default: today)")
    args = parser.parse_args(argv)

    today = now_ist().date()
    if args.command in ("seed", "reset"):
        with session_scope() as db:
            if args.command == "seed" and is_seeded(db):
                if args.if_empty:
                    added = top_up_slots(db, today)
                    print(f"Database already seeded; {added} slots added to keep {SEED_DAYS_AHEAD} days bookable.")
                    return 0
                print("Database already seeded; use 'reset' to start again.", file=sys.stderr)
                return 1
            summary = reset_demo(db, today, args.seed) if args.command == "reset" else seed_all(db, today, args.seed)
        print(json.dumps({"command": args.command, "reference_day": today.isoformat(), **summary}, indent=2))
        return 0

    with session_scope() as db:
        if not is_seeded(db):
            print("Database is empty; run 'python -m simulator seed' first.", file=sys.stderr)
            return 1

    days = (
        [args.date or today - timedelta(days=1)]
        if args.command == "replay-day"
        else history_days(args.end or today, args.days)
    )
    failed = False
    for day in days:
        started = wallclock.perf_counter()
        # Training-data replays skip live predictions; a single replayed day keeps them, like the live system.
        quiet = predictions_disabled() if args.command == "history" else nullcontext()
        with session_scope() as db, quiet:
            replay = replay_day(db, day, args.seed)
        with session_scope() as db:
            report = validate_day(db, day)
        report["replayed_sessions"] = len(replay["sessions"])
        report["skipped_sessions"] = replay["skipped"]
        report["seconds"] = round(wallclock.perf_counter() - started, 1)
        if args.command == "replay-day":
            report["session_events"] = {s["doctor"]: s["events"] for s in replay["sessions"] if s["events"]}
            print(json.dumps(report, indent=2))
        else:
            median = report["wait_minutes"]["median"]
            print(
                f"{day}  sessions={report['sessions']:>2}  seen={report['patients_seen']:>3}  "
                f"wait_median={'-' if median is None else median:>5}  ok={report['ok']}  ({report['seconds']}s)"
            )
        failed |= not report["ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
