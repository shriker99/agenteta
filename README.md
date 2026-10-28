# agenteta

History-based ETA quotes for AI agent jobs: a p50 ("likely") and p85 ("bad day") time from your own job log,
plus an overdue checker and a miss log. Standard library only.

## Install and run

    pip install -e .[test]
    agenteta --config examples/agenteta.toml quote bot-a --class lookup
    agenteta --config examples/agenteta.toml backtest
    agenteta --config examples/agenteta.toml miss bot-a --quoted 10m --actual 22m --type lookup
    agenteta --config examples/agenteta.toml overdue          # shadow: prints, sends nothing
    pytest

Settings come from `agenteta.toml` (or `$AGENTETA_CONFIG`) and can be overridden by env vars such as
`AGENTETA_LOG_PATH`. See `agenteta/config.py` for every field and its default.

## Job log

A CSV with `start_at, done_at, bot, job, job_type, job_class, eta_quoted_s` and optional columns for size, steps,
review rounds, scope adds, wait time, errors, token count, flags and notes. `examples/sample-jobs.csv` is made up.

## How it works

1. Valid rows have both times and done > start; wait time is subtracted; flagged rows (dup, late_close, ...) are skipped.
2. Outliers: a job more than 5x the median of earlier jobs in its class (at least `outlier_min_hist`, default 3) is
   dropped (past rows only, no look-ahead). Optional: `drop_over_s` (e.g. 28800 = 8 h) drops very long jobs; off by default.
3. Quote: recency-weighted (7-day half-life) quantiles of log seconds at the first level with at least 5 rows:
   bot+class, pool+class, bot+type, bot (only when no class is given, unless
   `bot_fallback_with_class`), pool. p85 is widened for small samples, never past the slowest real
   job, and optionally (`p85_cap = true`) capped at 3x p50.
4. Overdue: an open job is overdue when elapsed > quote + grace (p85 of past overruns, at least 5 minutes;
   `grace_by_class` sets per-class floors).
5. Miss: |actual - quote| > 25% of the quote and > 5 minutes, either direction.
6. A "done" with no finish time is asked once, then closed late, kept out of stats, and logged as a finding.

## Differences from reference implementation

- **Optional p85 cap** (`p85_cap`, default **off**; `p85_cap_x = 3.0`): when turned on (`p85_cap = true` or
  `AGENTETA_P85_CAP=1`), p85 is capped at 3x p50. The reference implementation has no such cap, so the default matches it.
- `drop_over_s` and `grace_by_class` are optional extras, off/empty by default.

Env overrides: `AGENTETA_<FIELD>`, e.g. `AGENTETA_P85_CAP=1`, `AGENTETA_DROP_OVER_S=28800`,
`AGENTETA_GRACE_BY_CLASS="build=900,lookup=300"`.
