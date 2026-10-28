"""Configuration: defaults < TOML file < environment variables.

Lookup order for the file: $AGENTETA_CONFIG, then ./agenteta.toml.
"""
import os
import sys
from dataclasses import dataclass, field, fields

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = None

ENV_PREFIX = "AGENTETA_"


@dataclass
class Config:
    log_path: str = "jobs.csv"          # the job log CSV
    miss_log_path: str = "eta-miss-log.md"  # human-readable miss log
    state_dir: str = ".agenteta"           # timers, nudge outbox
    half_life_days: float = 7.0            # recency weighting
    min_n: int = 5                          # rows needed before a level is used
    outlier_x: float = 5.0                  # drop past jobs > X times the class median
    p85_cap: bool = False                   # opt-in: cap p85 at p85_cap_x * p50 (not in reference; see README)
    p85_cap_x: float = 3.0                  # p85 never more than X times p50 (when p85_cap)
    outlier_min_hist: int = 3               # earlier class rows needed before the outlier rule applies
    bot_fallback_with_class: bool = False   # with a class given, fall back to the bot's own history
    drop_over_s: int = 0                    # drop jobs longer than this (e.g. 28800 = 8 h); 0 = off
    grace_by_class: dict = field(default_factory=dict)  # per-class grace floor overrides, seconds
    grace_min_s: int = 300                  # overdue grace floor
    miss_pct: float = 0.25                  # miss rule: gap > pct of quote ...
    miss_min_s: int = 300                   # ... AND gap > this many seconds
    owner: str = "owner"                    # who receives escalations
    reviewer: str = "reviewer"              # who receives missing-time findings
    bots: list = field(default_factory=list)  # optional known bot names


def load(path=None, env=None):
    env = os.environ if env is None else env
    cfg = Config()
    path = path or env.get(ENV_PREFIX + "CONFIG") or "agenteta.toml"
    if tomllib and os.path.exists(path):
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        for f in fields(cfg):
            if f.name in data:
                setattr(cfg, f.name, data[f.name])
    for f in fields(cfg):
        v = env.get(ENV_PREFIX + f.name.upper())
        if v is None:
            continue
        cur = getattr(cfg, f.name)
        if isinstance(cur, bool):
            v = v.lower() in ("1", "true", "yes")
        elif isinstance(cur, int):
            v = int(v)
        elif isinstance(cur, float):
            v = float(v)
        elif isinstance(cur, dict):
            v = {k.strip().lower(): int(x) for k, x in (p.split("=", 1) for p in v.split(",") if "=" in p)}
        elif isinstance(cur, list):
            v = [x.strip() for x in v.split(",") if x.strip()]
        setattr(cfg, f.name, v)
    return cfg
