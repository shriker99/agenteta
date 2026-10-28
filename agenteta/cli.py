"""agenteta command line.

  agenteta quote <bot> [--class C] [--type T]
  agenteta backtest
  agenteta add <bot> <job> --start TS --done TS [--class C] [--type T] [--quoted DUR]
  agenteta miss <bot> --quoted DUR --actual DUR [--type T]
  agenteta overdue [--send]
Exit codes: 0 ok, 1 nothing to report / below threshold, 2 usage error.
"""
import argparse
import json
import sys

from . import config, joblog, miss, overdue, quote as Q


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agenteta")
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("quote"); p.add_argument("bot"); p.add_argument("--class", dest="cls"); p.add_argument("--type"); p.add_argument("--json", action="store_true")
    sub.add_parser("backtest")
    p = sub.add_parser("add"); p.add_argument("bot"); p.add_argument("job"); p.add_argument("--start", required=True)
    p.add_argument("--done", default=""); p.add_argument("--class", dest="cls", default=""); p.add_argument("--type", default=""); p.add_argument("--quoted", default="")
    p = sub.add_parser("miss"); p.add_argument("bot"); p.add_argument("--quoted", required=True); p.add_argument("--actual", required=True); p.add_argument("--type", default="")
    p = sub.add_parser("overdue"); p.add_argument("--send", action="store_true")
    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    rows = joblog.read_rows(cfg.log_path)
    removed = []
    jobs = Q.cap_outliers(Q.drop_long(joblog.jobs(rows), cfg.drop_over_s, removed),
                          cfg.outlier_x, cfg.outlier_min_hist, removed)

    if a.cmd == "quote":
        q = Q.quote(jobs, a.bot, a.cls, a.type, cfg=cfg)
        if not q:
            print("no history"); return 1
        if a.json:
            print(json.dumps(dict(q, outliers_removed=len(removed)))); return 0
        print("ETA %s: p50 %s, p85 %s (n=%d, %s)%s" % (a.bot, Q.fmt(q["p50"]), Q.fmt(q["p85"]), q["n"], q["level"],
                                                      ("; " + q["note"]) if q["note"] else ""))
        return 0
    if a.cmd == "backtest":
        print(json.dumps(Q.backtest(jobs, cfg))); return 0
    if a.cmd == "add":
        qs = miss.parse_dur(a.quoted) if a.quoted else None
        if a.quoted and qs is None:
            print("bad --quoted", file=sys.stderr); return 2
        joblog.append_row(cfg.log_path, {"start_at": a.start, "done_at": a.done, "bot": a.bot, "job": a.job,
                                         "job_class": a.cls, "job_type": a.type, "eta_quoted_s": "" if qs is None else int(qs)})
        print("added"); return 0
    if a.cmd == "miss":
        qs, acs = miss.parse_dur(a.quoted), miss.parse_dur(a.actual)
        if qs is None or acs is None or qs <= 0:
            print("durations like 90s, 12m, 1h05m", file=sys.stderr); return 2
        try:
            gap = miss.log_miss(cfg, a.bot, a.type, qs, acs)
        except ValueError as e:
            print(str(e)); return 1
        print("miss logged, gap %+ds" % gap); return 0
    if a.cmd == "overdue":
        items = overdue.check(rows, jobs, cfg, shadow=not a.send)
        for it in items:
            print(json.dumps(it))
        return 0 if items else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
