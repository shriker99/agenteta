"""Class-based p50/p85 quotes with recency weighting, pooled fallback and outlier caps."""
import bisect
import math
import statistics
import time


def drop_long(jobs, max_s=0, removed=None):
    """Optional hard drop of jobs longer than max_s seconds (0 = off)."""
    if not max_s:
        return list(jobs)
    keep = []
    for j in jobs:
        if j["secs"] > max_s:
            if removed is not None:
                removed.append(j)
            continue
        keep.append(j)
    return keep


def cap_outliers(jobs, outlier_x=5.0, min_n=3, removed=None):
    """Drop a job whose duration > outlier_x * median of same-class jobs that ended before it started.
    Uses past rows only (no look-ahead). Removed jobs are appended to `removed` if given."""
    by = {}
    for i, j in enumerate(jobs):
        by.setdefault(j["cls"], []).append((j["end"], i, j))
    for v in by.values():
        v.sort(key=lambda t: (t[0], t[1]))
    keep = []
    for j in jobs:
        v = by[j["cls"]]
        cut = bisect.bisect_right([t[0] for t in v], j["start"])
        # exclude the job itself explicitly (live: `k is not j`)
        past = [k["secs"] for _, _, k in v[:cut] if k is not j]
        if len(past) >= min_n and j["secs"] > outlier_x * statistics.median(past):
            if removed is not None:
                removed.append(j)
            continue
        keep.append(j)
    return keep


def _w(j, now, half_life_days):
    return 0.5 ** (max(0.0, now - j["end"]) / 86400.0 / half_life_days)


def _wq(pairs, q):
    pairs = sorted(pairs)
    tot = sum(x for _, x in pairs)
    acc = 0.0
    for v, x in pairs:
        acc += x
        if acc >= q * tot - 1e-12:
            return v
    return pairs[-1][0]


def quote(jobs, bot, cls=None, jtype=None, now=None, cfg=None):
    """Return {'p50','p85','n','level','note'} in seconds, or None with no history.
    Levels: bot+class -> pool+class -> bot+type -> bot -> pool (first with >= min_n rows)."""
    from .config import Config
    cfg = cfg or Config()
    if not jobs:
        return None
    now = now if now is not None else max(j["end"] for j in jobs)
    b, c, t = (bot or "").lower(), (cls or "").lower(), (jtype or "").lower()
    levels = (("bot+class", lambda j: j["bot"] == b and c and j["cls"] == c),
              ("pool+class", lambda j: c and j["cls"] == c),
              ("bot+type", lambda j: j["bot"] == b and t and j["type"] == t),
              ("bot", lambda j: j["bot"] == b and (not c or cfg.bot_fallback_with_class)),
              ("pool", lambda j: True))
    for name, f in levels:
        g = [j for j in jobs if f(j)]
        if not (len(g) >= cfg.min_n or (name == "pool" and g)):
            continue
        pr = [(math.log(j["secs"]), _w(j, now, cfg.half_life_days)) for j in g]
        m50, m85 = _wq(pr, 0.5), _wq(pr, 0.85)
        tw = sum(x for _, x in pr)
        mu = sum(v * x for v, x in pr) / tw
        sd = math.sqrt(sum(x * (v - mu) ** 2 for v, x in pr) / tw)
        m85 = max(m85, m50) + 1.04 * sd / math.sqrt(len(g))
        m85 = max(m50, min(m85, max(v for v, _ in pr)))
        p50, p85 = math.exp(m50), math.exp(m85)
        note = ""
        if cfg.p85_cap and p85 > cfg.p85_cap_x * p50:
            p85, note = cfg.p85_cap_x * p50, "p85 capped at %gx p50" % cfg.p85_cap_x
        elif len(g) < 10 and abs(p85 - max(j["secs"] for j in g)) < 1:
            note = "p85 is the slowest job of %d" % len(g)
        return {"p50": p50, "p85": p85, "n": len(g), "level": name, "note": note}
    return None


def fmt(secs):
    secs = int(round(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return ("%dh%02dm%02ds" % (h, m, s)) if h else ("%dm%02ds" % (m, s))


def backtest(jobs, cfg=None, min_hist=5):
    """Walk forward: quote each job from jobs that ended before it started. Returns summary dict."""
    jobs = sorted(jobs, key=lambda j: j["start"])
    errs, inside = [], 0
    for j in jobs:
        hist = [h for h in jobs if h["end"] <= j["start"]]
        if len(hist) < min_hist:
            continue
        q = quote(hist, j["bot"], j["cls"], j["type"], now=j["start"], cfg=cfg)
        if not q:
            continue
        errs.append(abs(j["secs"] - q["p50"]))
        inside += j["secs"] <= q["p85"]
    if not errs:
        return {"n": 0}
    return {"n": len(errs), "median_abs_err_s": statistics.median(errs), "p85_coverage": inside / len(errs)}
