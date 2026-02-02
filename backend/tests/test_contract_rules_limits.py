from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services.contract_rules import MAX_RULE_RUNS_HARD_LIMIT, should_run


def test_interval_requires_max_runs() -> None:
    with pytest.raises(ValueError):
        should_run({"type": "interval", "interval_seconds": 1}, {"runs": 0})


def test_max_runs_hard_limit_enforced() -> None:
    with pytest.raises(ValueError):
        should_run(
            {"type": "interval", "interval_seconds": 1, "max_runs": MAX_RULE_RUNS_HARD_LIMIT + 1},
            {"runs": 0},
        )


def test_runs_hard_cutoff_blocks_execution() -> None:
    ok = should_run(
        {"type": "interval", "interval_seconds": 1, "max_runs": MAX_RULE_RUNS_HARD_LIMIT},
        {"runs": MAX_RULE_RUNS_HARD_LIMIT},
    )
    assert ok is False
