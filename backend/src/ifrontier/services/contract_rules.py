from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ifrontier.infra.sqlite.ledger import ContractTransfer, get_snapshot


@dataclass(frozen=True)
class RuleExecutionResult:
    rule_id: str
    evaluated: bool
    executed: bool
    reason: str | None = None


MAX_RULE_RUNS_HARD_LIMIT = 10000


def resolve_var(var: str) -> float:
    """Resolve variable in a safe whitelist way.

    Supported:
    - cash:<account_id>
    - pos:<account_id>:<symbol>
    """

    if not isinstance(var, str) or ":" not in var:
        raise ValueError("invalid var")

    kind, rest = var.split(":", 1)
    kind = kind.strip()
    if kind == "cash":
        account_id = rest
        snap = get_snapshot(account_id)
        return float(snap.cash)

    if kind == "pos":
        # pos:<account_id>:<symbol>  (account_id itself may contain ':')
        parts = var.split(":", 2)
        if len(parts) != 3:
            raise ValueError("pos var requires symbol")
        _, account_id, symbol = parts
        snap = get_snapshot(account_id)
        return float(snap.positions.get(symbol, 0.0))

    raise ValueError("invalid var")


def eval_condition(expr: Any) -> bool:
    """Evaluate a JSON condition expression.

    Grammar (subset):
    - {"op": "and", "args": [expr, ...]}
    - {"op": "or", "args": [expr, ...]}
    - {"op": "not", "arg": expr}
    - {"op": "=="|"!="|">"|">="|"<"|"<=", "left": value, "right": value}

    Value:
    - {"var": "cash:user:alice"} or {"var": "pos:user:alice:BLUEGOLD"}
    - number
    """

    if isinstance(expr, bool):
        return expr

    if not isinstance(expr, dict):
        raise ValueError("invalid condition")

    op = str(expr.get("op") or "")

    if op in {"and", "or"}:
        args = expr.get("args")
        if not isinstance(args, list) or not args:
            raise ValueError("invalid args")
        vals = [eval_condition(a) for a in args]
        return all(vals) if op == "and" else any(vals)

    if op == "not":
        return not eval_condition(expr.get("arg"))

    if op in {"==", "!=", ">", ">=", "<", "<="}:
        left = _eval_value(expr.get("left"))
        right = _eval_value(expr.get("right"))
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        return left <= right

    raise ValueError("unsupported op")


def _eval_value(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and "var" in v:
        return float(resolve_var(str(v["var"])))
    raise ValueError("invalid value")


def should_run(schedule: Dict[str, Any], state: Dict[str, Any]) -> bool:
    """Return True if schedule allows this rule run now.

    schedule:
    - {"type": "once"}
    - {"type": "interval", "interval_seconds": 60, "max_runs": 10}

    state:
    - {"runs": 0, "last_run_at": "..."}
    """

    stype = str(schedule.get("type") or "once")

    runs = int(state.get("runs") or 0)

    # 系统硬限制：任何规则最多执行 MAX_RULE_RUNS_HARD_LIMIT 次
    if runs >= MAX_RULE_RUNS_HARD_LIMIT:
        return False

    max_runs = schedule.get("max_runs")

    if stype == "interval" and max_runs is None:
        raise ValueError("max_runs required for interval schedule")

    if max_runs is not None:
        max_runs_i = int(max_runs)
        if max_runs_i < 1:
            raise ValueError("invalid max_runs")
        if max_runs_i > MAX_RULE_RUNS_HARD_LIMIT:
            raise ValueError("max_runs exceeds hard limit")
        if runs >= max_runs_i:
            return False

    if stype == "once":
        return runs == 0

    if stype == "interval":
        interval = int(schedule.get("interval_seconds") or 0)
        if interval <= 0:
            raise ValueError("invalid interval_seconds")

        last = state.get("last_run_at")
        if not last:
            return True

        last_dt = datetime.fromisoformat(str(last))
        now = datetime.now(timezone.utc)
        return (now - last_dt).total_seconds() >= interval

    raise ValueError("unsupported schedule type")


def parse_transfers(raw: Any) -> List[ContractTransfer]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("transfers must be list")

    transfers: List[ContractTransfer] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("invalid transfer")
        transfers.append(
            ContractTransfer(
                from_account_id=str(item.get("from")),
                to_account_id=str(item.get("to")),
                asset_type=str(item.get("asset_type")),
                symbol=str(item.get("symbol")),
                quantity=float(item.get("quantity")),
            )
        )
    return transfers
