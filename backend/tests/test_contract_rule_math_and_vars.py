from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services.contract_rules import eval_condition


def test_math_expression_add_mul_in_condition() -> None:
    # (10 + 2 * 5) > 15
    expr = {
        "op": ">",
        "left": {
            "op": "add",
            "args": [10, {"op": "mul", "args": [2, 5]}],
        },
        "right": 15,
    }
    assert eval_condition(expr) is True


@pytest.mark.parametrize("var", [
    "book.depth_bid:BLUEGOLD",
    "vol.short:BLUEGOLD",
    "ext.index:SP500",
    "price.last:BLUEGOLD",
])
def test_unimplemented_variable_namespaces_raise(var: str) -> None:
    expr = {"op": "==", "left": {"var": var}, "right": 0}
    with pytest.raises(ValueError):
        eval_condition(expr)


def test_price_variable_reads_last_price() -> None:
    from ifrontier.infra.sqlite.market import record_trade

    record_trade(symbol="BLUEGOLD", price=12.5, quantity=1.0, occurred_at=datetime.now(timezone.utc), event_id="test")
    expr = {"op": "==", "left": {"var": "price:BLUEGOLD"}, "right": 12.5}
    assert eval_condition(expr) is True
