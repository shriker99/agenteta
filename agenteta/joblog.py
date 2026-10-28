"""Read the job log CSV into duration records. All extra columns are optional."""
import csv
import os
from datetime import datetime

COLUMNS = ["start_at", "done_at", "bot", "job", "job_type", "job_class", "outcome",
           "eta_quoted_s", "job_size", "steps", "review_rounds", "scope_adds",
           "wait_s", "errors", "token_count", "flags", "notes"]
EXCLUDE_FLAGS = {"dup", "multi_bot", "no_bot", "late_close", "grace_default", "synthetic"}
FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S")


def parse_ts(s):
    s = (s or "").strip()
    for f in FORMATS:
        try:
            return datetime.strptime(s, f).timestamp()
        except ValueError:
            pass
    return None


def flags_of(row):
    return {t for t in (row.get("flags") or "").replace(";", " ").replace(",", " ").split() if t}


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def jobs(rows):
    """Valid finished jobs: both times parse, done > start, no excluded flag."""
    out = []
    for r in rows:
        a, b = parse_ts(r.get("start_at")), parse_ts(r.get("done_at"))
        if a is None or b is None or b <= a or flags_of(r) & EXCLUDE_FLAGS:
            continue
        wait = float(r.get("wait_s") or 0)
        secs = max(1.0, b - a - wait)
        out.append({"bot": (r.get("bot") or "").strip().lower(),
                    "cls": (r.get("job_class") or "").strip().lower(),
                    "type": (r.get("job_type") or "").strip().lower(),
                    "start": a, "end": b, "secs": secs, "row": r})
    return out


def append_row(path, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLUMNS})
