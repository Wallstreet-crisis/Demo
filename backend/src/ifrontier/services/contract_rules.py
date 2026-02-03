from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import json
from neo4j import Driver

from ifrontier.infra.neo4j.driver import create_driver
from ifrontier.infra.sqlite.ledger import ContractTransfer, get_snapshot
from ifrontier.infra.sqlite.market import get_last_price


@dataclass(frozen=True)
class RuleExecutionResult:
    rule_id: str
    evaluated: bool
    executed: bool
    reason: str | None = None


MAX_RULE_RUNS_HARD_LIMIT = 10000


_NEO4J_DRIVER: Driver | None = None


def _get_neo4j_driver() -> Driver:
    global _NEO4J_DRIVER
    if _NEO4J_DRIVER is None:
        _NEO4J_DRIVER = create_driver()
    return _NEO4J_DRIVER


def resolve_var(var: str) -> float:
    """Resolve variable in a safe whitelist way.

    Supported:
    - cash:<account_id>
    - pos:<account_id>:<symbol>
    """

    if not isinstance(var, str) or ":" not in var:
        raise ValueError("invalid var")

    # 特判 contract.* 变量（使用点号命名空间）：
    # - contract.status:<contract_id>
    # - contract.runs:<contract_id>:<rule_id>
    if var.startswith("contract.status:"):
        # status 本身在 eval_condition 中按字符串处理，这里返回 NaN 仅用于占位，防止被当作数值使用
        # 真正的状态字符串由 _eval_contract_status 获取
        return float("nan")

    if var.startswith("contract.runs:"):
        # var 形如 "contract.runs:<cid>:<rule_id>"
        driver = _get_neo4j_driver()
        try:
            _prefix, cid, rule_id = var.split(":", 2)
        except ValueError as exc:
            raise ValueError("invalid contract.runs var") from exc

        with driver.session() as session:
            record = session.execute_read(
                _load_contract_rule_state_tx,
                {"contract_id": cid},
            )
        if record is None:
            raise ValueError("contract not found")
        state_json = str(record.get("rule_state_json") or "{}")
        try:
            state = json.loads(state_json) if state_json else {}
        except json.JSONDecodeError as exc:
            raise ValueError("invalid contract rule_state_json") from exc
        if not isinstance(state, dict):
            raise ValueError("invalid contract rule_state_json")
        runs = 0
        rule_state = state.get(rule_id)
        if isinstance(rule_state, dict) and "runs" in rule_state:
            runs = int(rule_state.get("runs") or 0)
        return float(runs)

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

    # 预留空间：价格/盘口/波动率/外部数据等，由上层数据网关实现
    if kind == "price":
        symbol = rest
        last = get_last_price(symbol)
        if last is None:
            raise ValueError("price not available")
        return float(last)
    if kind == "book":
        raise ValueError("order book variables not implemented yet")
    if kind == "vol":
        raise ValueError("volatility variables not implemented yet")
    if kind == "ext":
        raise ValueError("external data variables not implemented yet")

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
        left_raw = expr.get("left")
        right_raw = expr.get("right")

        # 特判字符串比较（例如 contract.status）
        if isinstance(left_raw, dict) and "var" in left_raw and str(left_raw["var"]).startswith("contract.status:"):
            left_val = _eval_contract_status(str(left_raw["var"]))
            right_val = right_raw
        elif isinstance(right_raw, dict) and "var" in right_raw and str(right_raw["var"]).startswith("contract.status:"):
            right_val = _eval_contract_status(str(right_raw["var"]))
            left_val = left_raw
        else:
            left_val = _eval_value(left_raw)
            right_val = _eval_value(right_raw)

        left = left_val
        right = right_val
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


def _eval_contract_status(var: str) -> str:
    # var 形如 "contract.status:<contract_id>"
    if ":" not in var:
        raise ValueError("invalid contract.status var")
    _, rest = var.split(":", 1)
    if ":" not in rest:
        contract_id = rest
    else:
        # 允许错误多写，截断为第一个 ':' 之前
        contract_id = rest.split(":", 1)[0]

    driver = _get_neo4j_driver()
    with driver.session() as session:
        record = session.execute_read(
            _load_contract_status_tx,
            {"contract_id": contract_id},
        )
    if record is None or record.get("status") is None:
        raise ValueError("contract not found")
    return str(record["status"])


def _eval_value(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)

    if isinstance(v, dict):
        # 变量引用
        if "var" in v:
            return float(resolve_var(str(v["var"])))

        op = v.get("op")
        if op in {"add", "sub", "mul", "div", "min", "max"}:
            args = v.get("args")
            if not isinstance(args, list) or not args:
                raise ValueError("invalid args for op")
            vals = [_eval_value(a) for a in args]

            if op == "add":
                return float(sum(vals))
            if op == "sub":
                if len(vals) != 2:
                    raise ValueError("sub requires exactly 2 args")
                return float(vals[0] - vals[1])
            if op == "mul":
                res = 1.0
                for x in vals:
                    res *= x
                return float(res)
            if op == "div":
                if len(vals) != 2:
                    raise ValueError("div requires exactly 2 args")
                if vals[1] == 0:
                    raise ValueError("division by zero")
                return float(vals[0] / vals[1])
            if op == "min":
                return float(min(vals))
            if op == "max":
                return float(max(vals))

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


def _load_contract_status_tx(tx, params: Dict[str, Any]):
    rec = tx.run(
        """
        MATCH (c:Contract {contract_id: $contract_id})
        RETURN c.status AS status
        """,
        **params,
    ).single()
    return dict(rec) if rec is not None else None


def _load_contract_rule_state_tx(tx, params: Dict[str, Any]):
    rec = tx.run(
        """
        MATCH (c:Contract {contract_id: $contract_id})
        RETURN c.rule_state_json AS rule_state_json
        """,
        **params,
    ).single()
    return dict(rec) if rec is not None else None


def parse_transfers(raw: Any) -> List[ContractTransfer]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("transfers must be list")

    transfers: List[ContractTransfer] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("invalid transfer")

        q_raw = item.get("quantity")
        if isinstance(q_raw, dict) and "expr" in q_raw:
            qty = _eval_value(q_raw.get("expr"))
        else:
            qty = float(q_raw)

        transfers.append(
            ContractTransfer(
                from_account_id=str(item.get("from")),
                to_account_id=str(item.get("to")),
                asset_type=str(item.get("asset_type")),
                symbol=str(item.get("symbol")),
                quantity=float(qty),
            )
        )
    return transfers
