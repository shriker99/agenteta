import os
import pytest
from agenteta import config, joblog, miss, overdue, quote as Q
from agenteta.cli import main

HERE = os.path.dirname(__file__)
SAMPLE = os.path.join(HERE, "..", "examples", "sample-jobs.csv")


def mk(bot, cls, start, secs):
    return {"bot": bot, "cls": cls, "type": cls, "start": start, "end": start + secs, "secs": secs, "row": {}}


def test_sample_loads():
    rows = joblog.read_rows(SAMPLE)
    assert len(joblog.jobs(rows)) == 60


def test_quote_levels_and_cap():
    cfg = config.Config()
    jobs = [mk("bot-a", "x", i * 1000, 100 + i) for i in range(6)]
    q = Q.quote(jobs, "bot-a", "x", cfg=cfg)
    assert q["level"] == "bot+class" and 100 <= q["p50"] <= 106 
    q2 = Q.quote(jobs, "bot-z", "x", cfg=cfg)
    assert q2["level"] == "pool+class"


def test_p85_cap_default_off():
    assert config.Config().p85_cap is False
    jobs = [mk("b", "x", i * 10000, s) for i, s in enumerate([60, 60, 60, 60, 60, 5000, 5000])]
    q = Q.quote(jobs, "b", "x", cfg=config.Config())
    assert q["p85"] > 3 * q["p50"] and "capped" not in q["note"]


def test_p85_capped_opt_in():
    cfg = config.Config(p85_cap=True)
    jobs = [mk("b", "x", i * 10000, s) for i, s in enumerate([60, 60, 60, 60, 60, 5000, 5000])]
    q = Q.quote(jobs, "b", "x", cfg=cfg)
    assert q["p85"] <= 3 * q["p50"] + 1e-6 and "capped" in q["note"]


def test_outlier_removed_past_only():
    jobs = [mk("b", "x", i * 1000, 100) for i in range(5)] + [mk("b", "x", 10000, 5000)]
    removed = []
    keep = Q.cap_outliers(jobs, 5.0, 3, removed)
    assert len(keep) == 5 and removed[0]["secs"] == 5000


CASES = [
    ("90s", 90),
    ("12m", 720),
    ("1h", 60 * 60),
    ("1h05m", 65 * 60),
    ("2", 120),
    ("x", None),
]


@pytest.mark.parametrize("t,s", CASES)
def test_parse_dur(t, s):
    assert miss.parse_dur(t) == s


def test_miss_rule_both_directions(tmp_path):
    cfg = config.Config(miss_log_path=str(tmp_path / "m.md"))
    assert miss.is_miss(600, 1000, cfg) and miss.is_miss(1600, 1000, cfg)
    assert not miss.is_miss(600, 900, cfg)       # gap exactly 300 s: not > 5 min
    assert not miss.is_miss(3600, 4400, cfg)     # 800 s but < 25%
    with pytest.raises(ValueError):
        miss.log_miss(cfg, "bot-a", "lookup", 600, 700)
    assert not os.path.exists(cfg.miss_log_path)
    miss.log_miss(cfg, "bot-a", "lookup", 600, 1200)
    txt = open(cfg.miss_log_path).read()
    assert "25%" in txt and "%%" not in txt and "bot-a" in txt


def test_overdue_shadow(tmp_path):
    cfg = config.Config(state_dir=str(tmp_path / "s"))
    rows = [{"start_at": "2026-01-01 10:00:00", "done_at": "", "bot": "bot-a", "job": "j", "eta_quoted_s": "60"}]
    now = joblog.parse_ts("2026-01-01 10:00:00") + 60 + 301
    items = overdue.check(rows, [], cfg, now=now, shadow=True)
    assert len(items) == 1 and not os.path.exists(cfg.state_dir)
    assert overdue.check(rows, [], cfg, now=now - 2) == []


def test_done_without_time_asks_once_then_closes(tmp_path):
    cfg = config.Config(state_dir=str(tmp_path / "s"), reviewer="rev")
    row = {"bot": "bot-b", "job": "j", "flags": ""}
    assert overdue.close_without_time(row, cfg, False) == ("ask", None)
    st, f = overdue.close_without_time(row, cfg, True, reason="forgot")
    assert st == "closed" and row["outcome"] == "closed_late" and "late_close" in row["flags"]
    assert f["to"] == "rev" and os.path.exists(os.path.join(cfg.state_dir, "missing-time.jsonl"))
    assert joblog.jobs([dict(row, start_at="2026-01-01 10:00:00")]) == []


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENTETA_LOG_PATH", SAMPLE)
    monkeypatch.setenv("AGENTETA_MISS_LOG_PATH", str(tmp_path / "m.md"))
    monkeypatch.setenv("AGENTETA_CONFIG", str(tmp_path / "none.toml"))
    assert main(["quote", "bot-a", "--class", "lookup"]) == 0
    assert "p50" in capsys.readouterr().out
    assert main(["backtest"]) == 0
    assert main(["miss", "bot-a", "--quoted", "10m", "--actual", "20m"]) == 0
    assert main(["miss", "bot-a", "--quoted", "10m", "--actual", "11m"]) == 1
    assert main(["miss", "bot-a", "--quoted", "zz", "--actual", "1m"]) == 2


def test_outlier_min_hist_default_3():
    assert config.Config().outlier_min_hist == 3
    jobs = [mk("b", "x", i * 1000, 100) for i in range(3)] + [mk("b", "x", 10000, 5000)]
    assert len(Q.cap_outliers(jobs, 5.0, 3)) == 3
    assert len(Q.cap_outliers(jobs, 5.0, 4)) == 4


def test_no_bot_fallback_when_class_given():
    jobs = [mk("b", "y", i * 1000, 100) for i in range(6)] + [mk("c", "z", 9000 + i, 50) for i in range(2)]
    q = Q.quote(jobs, "b", "x", cfg=config.Config())
    assert q["level"] == "pool"
    q2 = Q.quote(jobs, "b", "x", cfg=config.Config(bot_fallback_with_class=True))
    assert q2["level"] == "bot"
    assert Q.quote(jobs, "b", None, cfg=config.Config())["level"] == "bot"


def test_backtest_no_lookahead(monkeypatch):
    jobs = [mk("b", "x", i * 1000, 100 + i) for i in range(10)]
    seen = []
    real = Q.quote
    def spy(hist, bot, cls, jt, now=None, cfg=None):
        seen.append((now, max(h["end"] for h in hist)))
        return real(hist, bot, cls, jt, now=now, cfg=cfg)
    monkeypatch.setattr(Q, "quote", spy)
    r = Q.backtest(jobs, min_hist=3)
    assert r["n"] == len(seen) > 0
    assert all(end <= now for now, end in seen)


def _qjob(cls, secs, quoted):
    j = mk("b", cls, 0, secs)
    j["row"] = {"eta_quoted_s": str(quoted)}
    return j


def test_grace_floor_and_p85():
    cfg = config.Config()
    assert overdue.grace_s([], cfg) == 300
    jobs = [_qjob("x", 100 + o, 100) for o in [0, 0, 0, 0, 0, 0, 1000, 1000, 2000, 2000]]
    # p85 of 10 overruns = 9th smallest = 2000
    assert overdue.grace_s(jobs, cfg) == 2000
    small = [_qjob("x", 110, 100) for _ in range(6)]
    assert overdue.grace_s(small, cfg) == 300
    cfg2 = config.Config(grace_by_class={"build": 900})
    assert overdue.grace_s(small, cfg2, "build") == 900 and overdue.grace_s(small, cfg2, "x") == 300


def test_env_override(tmp_path):
    env = {"AGENTETA_CONFIG": str(tmp_path / "none.toml"), "AGENTETA_P85_CAP": "1",
           "AGENTETA_DROP_OVER_S": "28800", "AGENTETA_OUTLIER_MIN_HIST": "4",
           "AGENTETA_GRACE_MIN_S": "120", "AGENTETA_GRACE_BY_CLASS": "Build=900,lookup=60",
           "AGENTETA_HALF_LIFE_DAYS": "3.5", "AGENTETA_BOTS": "a, b"}
    c = config.load(env=env)
    assert c.p85_cap is True and c.drop_over_s == 28800 and c.outlier_min_hist == 4
    assert c.grace_min_s == 120 and c.grace_by_class == {"build": 900, "lookup": 60}
    assert c.half_life_days == 3.5 and c.bots == ["a", "b"]
    assert config.load(env={"AGENTETA_CONFIG": "x", "AGENTETA_P85_CAP": "0"}).p85_cap is False


def test_drop_8h():
    jobs = [mk("b", "x", 0, 100), mk("b", "x", 1000, 8 * 3600), mk("b", "x", 50000, 8 * 3600 + 1)]
    assert len(Q.drop_long(jobs, 0)) == 3          # off by default
    assert config.Config().drop_over_s == 0
    removed = []
    keep = Q.drop_long(jobs, 28800, removed)
    assert len(keep) == 2 and removed[0]["secs"] == 28801


def test_cap_outliers_excludes_self():
    # zero-duration rows end == start, so each is in its own "past" window unless excluded
    jobs = [dict(cls="a", start=100.0, end=100.0, secs=s) for s in (10, 10, 1000)]
    # with self excluded, the 1000s row sees only 2 peers (< min_n=3) -> kept
    assert len(Q.cap_outliers(jobs, 5.0, 3)) == 3
    removed = []
    keep = Q.cap_outliers(jobs, 5.0, 2, removed)
    assert [j["secs"] for j in removed] == [1000] and len(keep) == 2
