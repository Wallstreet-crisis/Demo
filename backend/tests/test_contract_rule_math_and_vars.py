from __future__ import annotations

import sys
from pathlib import Path

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
    "price.last:BLUEGOLD",
    "book.depth_bid:BLUEGOLD",
    "vol.short:BLUEGOLD",
    "ext.index:SP500",
])
def test_unimplemented_variable_namespaces_raise(var: str) -> None:
    expr = {"op": "==", "left": {"var": var}, "right": 0}
    with pytest.raises(ValueError):
        eval_condition(expr)
