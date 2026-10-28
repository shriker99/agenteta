"""Miss rule: |actual - quote| > miss_pct * quote AND > miss_min_s (either direction)."""
import os
import re
from datetime import datetime

_DUR = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def parse_dur(t):
    """'90s', '12m', '1h', '1h05m', '2m30s', or a bare number of minutes."""
    t = (t or "").strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return float(t) * 60
    m = _DUR.fullmatch(t)
    if not t or not m or not any(m.groups()):
        return None
    h, mi, s = (int(x or 0) for x in m.groups())
    return float(h * 3600 + mi * 60 + s)


def is_miss(quoted_s, actual_s, cfg):
    gap = abs(actual_s - quoted_s)
    return gap > cfg.miss_pct * quoted_s and gap > cfg.miss_min_s


def log_miss(cfg, bot, job_type, quoted_s, actual_s, when=None):
    """Append one line to the miss log. Raises ValueError below threshold (writes nothing)."""
    if not is_miss(quoted_s, actual_s, cfg):
        raise ValueError("below miss threshold")
    from .quote import fmt
    when = when or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new = not os.path.exists(cfg.miss_log_path)
    gap = actual_s - quoted_s
    with open(cfg.miss_log_path, "a") as fh:
        if new:
            fh.write("# ETA miss log (gap > %d%% of quote and > %ds)\n\n" % (round(cfg.miss_pct * 100), cfg.miss_min_s))
            fh.write("| date | bot | job_type | quoted | actual | gap |\n|---|---|---|---|---|---|\n")
        fh.write("| %s | %s | %s | %s | %s | %s%s |\n" % (when, bot, job_type or "-", fmt(quoted_s), fmt(actual_s),
                                                      "+" if gap >= 0 else "-", fmt(abs(gap))))
    return gap
