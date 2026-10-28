"""Overdue check: an open job is overdue when elapsed > quoted + grace. Shadow mode never sends."""
import json
import os
import time

from .joblog import parse_ts


def grace_s(jobs, cfg, cls=None):
    """p85 of overrun (actual - quoted) on finished jobs that carried a quote; floor grace_min_s,
    or grace_by_class[cls] when set for that class."""
    c = (cls or "").strip().lower()
    floor = float((cfg.grace_by_class or {}).get(c, cfg.grace_min_s))
    over = sorted(max(0.0, j["secs"] - float(j["row"]["eta_quoted_s"]))
                  for j in jobs if (j["row"].get("eta_quoted_s") or "").strip())
    if len(over) < cfg.min_n:
        return floor
    return max(floor, over[max(0, int(0.85 * len(over) + 0.999) - 1)])


def check(rows, jobs, cfg, now=None, shadow=True):
    """Return nudge items for open rows past quote + grace. Writes them to the outbox unless shadow."""
    now = time.time() if now is None else now
    items = []
    for r in rows:
        if (r.get("done_at") or "").strip():
            continue
        a = parse_ts(r.get("start_at"))
        q = (r.get("eta_quoted_s") or "").strip()
        if a is None or not q:
            continue
        late = now - a - float(q) - grace_s(jobs, cfg, r.get("job_class"))
        if late > 0:
            items.append({"bot": r.get("bot", ""), "job": r.get("job", ""), "late_s": round(late), "to": r.get("bot", "")})
    if items and not shadow:
        os.makedirs(cfg.state_dir, exist_ok=True)
        with open(os.path.join(cfg.state_dir, "outbox.jsonl"), "a") as fh:
            for it in items:
                fh.write(json.dumps(it) + "\n")
    return items


def close_without_time(row, cfg, asked_already, reason=""):
    """A 'done' with no finish time: ask once, then close as late and record a missing-time finding.
    Returns ('ask', None) or ('closed', finding). Never blocks."""
    if not asked_already:
        return "ask", None
    row["done_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    row["outcome"] = "closed_late"
    row["flags"] = ((row.get("flags") or "") + " late_close").strip()
    finding = {"kind": "missing_time", "bot": row.get("bot", ""), "job": row.get("job", ""),
               "reason": reason, "to": cfg.reviewer}
    try:
        os.makedirs(cfg.state_dir, exist_ok=True)
        with open(os.path.join(cfg.state_dir, "missing-time.jsonl"), "a") as fh:
            fh.write(json.dumps(finding) + "\n")
    except OSError:
        pass  # a findings write error never blocks the close
    return "closed", finding
