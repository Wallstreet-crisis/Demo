import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.infra.llm.openrouter import OpenRouterClient, OpenRouterConfig, OpenRouterError, extract_first_message_text
from ifrontier.services.app_settings import get_runtime_llm_config

DEFAULT_MODELS = [
    "google/gemini-flash-1.5:nitro",
    "deepseek/deepseek-chat:nitro",
    "qwen/qwen-plus:nitro",
    "qwen/qwen-turbo:nitro",
    "openai/gpt-5.1-instant",
    "mistralai/mistral-tiny-2026",
    "anthropic/claude-4.6-sonnet",
]

LIGHT_TTFT_LIMIT_MS = 1800.0
STANDARD_TTFT_LIMIT_MS = 3500.0
HEAVY_TTFT_LIMIT_MS = 8000.0
LIGHT_TOTAL_LIMIT_MS = 4000.0
STANDARD_TOTAL_LIMIT_MS = 9000.0
HEAVY_TOTAL_LIMIT_MS = 20000.0

TEST_CASES = [
    {
        "name": "availability",
        "system": "You are a connectivity probe. Reply with exactly OK.",
        "user": "Reply with OK only.",
        "max_tokens": 4,
        "expect_json": False,
    },
    {
        "name": "zh_short",
        "system": "你是一个简洁的中文助手。请直接回答，不要解释过程。",
        "user": "用中文一句话解释什么是流动性风险，20字以内。",
        "max_tokens": 24,
        "expect_json": False,
    },
    {
        "name": "json_structured",
        "system": "你是一个JSON生成器。只能输出合法JSON，不允许输出Markdown或额外说明。",
        "user": "输出JSON：{\"action\":\"BUY|SELL|HOLD\",\"confidence\":0到1之间的数字,\"reason\":\"不超过20字中文\"}，基于新闻“银行流动性紧张但央行注入流动性”。",
        "max_tokens": 48,
        "expect_json": True,
    },
]


@dataclass
class CaseResult:
    case: str
    ok: bool
    first_event_ms: float
    ttft_ms: float
    latency_ms: float
    prompt_chars: int
    output_chars: int
    json_ok: bool
    error: str | None
    preview: str
    stream_event_samples: list[str]


@dataclass
class ModelResult:
    model: str
    ok_cases: int
    total_cases: int
    success_rate: float
    avg_ttft_ms: float
    avg_latency_ms: float
    json_success_rate: float
    realtime_pass_rate: float
    results: list[CaseResult]
    recommended_tier: str


def build_client(model: str) -> OpenRouterClient:
    runtime = get_runtime_llm_config()
    api_key = str(runtime.get("api_key") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing OpenRouter API key. Configure settings or OPENROUTER_API_KEY first.")
    base_url = str(runtime.get("base_url") or os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1")
    timeout_seconds = float(runtime.get("timeout_seconds") or os.getenv("OPENROUTER_TIMEOUT_SECONDS") or "20")
    return OpenRouterClient(
        OpenRouterConfig(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    )


def _runtime_values() -> tuple[str, str, float]:
    runtime = get_runtime_llm_config()
    api_key = str(runtime.get("api_key") or os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing OpenRouter API key. Configure settings or OPENROUTER_API_KEY first.")
    base_url = str(runtime.get("base_url") or os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1")
    timeout_seconds = float(runtime.get("timeout_seconds") or os.getenv("OPENROUTER_TIMEOUT_SECONDS") or "20")
    return api_key, base_url, timeout_seconds


def _extract_delta_text(delta: Any) -> str:
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content") or ""
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "".join(parts)
        reasoning = delta.get("reasoning") or delta.get("reasoning_content") or ""
        if isinstance(reasoning, str):
            return reasoning
    return ""


def stream_completion(*, model: str, system: str, user: str, max_tokens: int) -> tuple[float, float, float, str, list[str]]:
    api_key, base_url, timeout_seconds = _runtime_values()
    url = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": int(max_tokens),
        "stream": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "ifrontier-model-benchmark",
    }
    req = request.Request(
        url=url,
        method="POST",
        headers=headers,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    )
    started = time.perf_counter()
    first_event_ms = 0.0
    ttft_ms = 0.0
    chunks: list[str] = []
    event_samples: list[str] = []
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="ignore").strip()
                if not decoded or not decoded.startswith("data:"):
                    continue
                payload = decoded[5:].strip()
                if first_event_ms <= 0.0:
                    first_event_ms = round((time.perf_counter() - started) * 1000.0, 2)
                if len(event_samples) < 5:
                    event_samples.append(payload[:200])
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                
                # 记录供应商信息用于诊断
                provider = obj.get("provider", "unknown")
                if provider != "unknown" and len(event_samples) < 5:
                    if f"provider:{provider}" not in event_samples:
                        event_samples.append(f"provider:{provider}")

                choices = obj.get("choices") or []
                delta = ((choices[0] or {}).get("delta") or {}) if choices else {}
                text = _extract_delta_text(delta)
                if text:
                    if ttft_ms <= 0.0:
                        ttft_ms = round((time.perf_counter() - started) * 1000.0, 2)
                    chunks.append(text)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
        message = f"HTTP {exc.code}: {body[:1000] or exc.reason}"
        raise OpenRouterError(message) from exc
    total_ms = round((time.perf_counter() - started) * 1000.0, 2)
    text = "".join(chunks).strip()
    return first_event_ms or total_ms, ttft_ms or total_ms, total_ms, text, event_samples


def run_case(client: OpenRouterClient, case: dict[str, Any]) -> CaseResult:
    prompt_chars = len(case["system"]) + len(case["user"])
    raw_text = ""
    json_ok = False
    error = None
    ok = False
    first_event_ms = 0.0
    ttft_ms = 0.0
    latency_ms = 0.0
    stream_event_samples: list[str] = []
    try:
        first_event_ms, ttft_ms, latency_ms, raw_text, stream_event_samples = stream_completion(
            model=client._cfg.model,
            system=case["system"],
            user=case["user"],
            max_tokens=int(case["max_tokens"]),
        )
        ok = bool(raw_text)
        if case["expect_json"]:
            try:
                cleaned = raw_text
                start_idx = cleaned.find("{")
                end_idx = cleaned.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                    cleaned = cleaned[start_idx:end_idx + 1]
                obj = json.loads(cleaned)
                json_ok = isinstance(obj, dict)
            except Exception as exc:
                error = f"json_parse_failed: {exc}"
                json_ok = False
                ok = False
        else:
            json_ok = True
    except OpenRouterError as exc:
        error = str(exc)[:500]
    except Exception as exc:
        error = f"unexpected_error: {exc}"
    return CaseResult(
        case=str(case["name"]),
        ok=ok,
        first_event_ms=round(first_event_ms, 2),
        ttft_ms=round(ttft_ms, 2),
        latency_ms=round(latency_ms, 2),
        prompt_chars=prompt_chars,
        output_chars=len(raw_text),
        json_ok=json_ok,
        error=error,
        preview=raw_text[:160],
        stream_event_samples=stream_event_samples,
    )


def choose_tier(model_result: ModelResult) -> str:
    if model_result.success_rate < 0.67:
        return "reject"
    if model_result.realtime_pass_rate < 0.67:
        return "reject"
    if (
        model_result.avg_ttft_ms <= LIGHT_TTFT_LIMIT_MS
        and model_result.avg_latency_ms <= LIGHT_TOTAL_LIMIT_MS
        and model_result.json_success_rate >= 0.99
    ):
        return "light"
    if (
        model_result.avg_ttft_ms <= STANDARD_TTFT_LIMIT_MS
        and model_result.avg_latency_ms <= STANDARD_TOTAL_LIMIT_MS
        and model_result.json_success_rate >= 0.67
    ):
        return "standard"
    if model_result.avg_ttft_ms <= HEAVY_TTFT_LIMIT_MS and model_result.avg_latency_ms <= HEAVY_TOTAL_LIMIT_MS:
        return "heavy"
    return "reject"


def _realtime_case_pass(case: CaseResult) -> bool:
    if not case.ok:
        return False
    if case.case == "availability":
        return case.ttft_ms <= LIGHT_TTFT_LIMIT_MS and case.latency_ms <= LIGHT_TOTAL_LIMIT_MS
    if case.case == "zh_short":
        return case.ttft_ms <= STANDARD_TTFT_LIMIT_MS and case.latency_ms <= STANDARD_TOTAL_LIMIT_MS
    if case.case == "json_structured":
        return case.json_ok and case.ttft_ms <= HEAVY_TTFT_LIMIT_MS and case.latency_ms <= HEAVY_TOTAL_LIMIT_MS
    return False


def benchmark_model(model: str) -> ModelResult:
    client = build_client(model)
    results: list[CaseResult] = []
    for case in TEST_CASES:
        results.append(run_case(client, case))
    ok_cases = sum(1 for x in results if x.ok)
    total_cases = len(results)
    success_rate = ok_cases / total_cases if total_cases else 0.0
    avg_ttft_ms = sum(x.ttft_ms for x in results) / total_cases if total_cases else 0.0
    avg_latency_ms = sum(x.latency_ms for x in results) / total_cases if total_cases else 0.0
    json_cases = [x for x in results if x.case == "json_structured"]
    json_success_rate = (sum(1 for x in json_cases if x.json_ok) / len(json_cases)) if json_cases else 0.0
    realtime_pass_rate = (sum(1 for x in results if _realtime_case_pass(x)) / total_cases) if total_cases else 0.0
    temp = ModelResult(
        model=model,
        ok_cases=ok_cases,
        total_cases=total_cases,
        success_rate=round(success_rate, 4),
        avg_ttft_ms=round(avg_ttft_ms, 2),
        avg_latency_ms=round(avg_latency_ms, 2),
        json_success_rate=round(json_success_rate, 4),
        realtime_pass_rate=round(realtime_pass_rate, 4),
        results=results,
        recommended_tier="pending",
    )
    temp.recommended_tier = choose_tier(temp)
    return temp


def print_summary(items: list[ModelResult]) -> None:
    print("\n=== OpenRouter Model Benchmark Summary ===")
    print(f"{'MODEL':48} {'OK':>4} {'TTFT_MS':>10} {'AVG_MS':>10} {'REALTIME':>10} {'JSON':>8} {'TIER':>10}")
    for item in items:
        print(
            f"{item.model[:48]:48} {item.ok_cases}/{item.total_cases:>1} {item.avg_ttft_ms:>10.2f} "
            f"{item.avg_latency_ms:>10.2f} {item.realtime_pass_rate:>10.2f} {item.json_success_rate:>8.2f} {item.recommended_tier:>10}"
        )


def main() -> None:
    models = sys.argv[1:] or DEFAULT_MODELS
    print(f"Benchmarking {len(models)} models...")
    results: list[ModelResult] = []
    for model in models:
        print(f"\n--- Testing {model} ---")
        try:
            item = benchmark_model(model)
            results.append(item)
            print(
                f"done: ttft={item.avg_ttft_ms:.2f}ms avg={item.avg_latency_ms:.2f}ms "
                f"rt={item.realtime_pass_rate:.2f} ok={item.ok_cases}/{item.total_cases} tier={item.recommended_tier}"
            )
        except Exception as exc:
            print(f"failed: {model} -> {exc}")
            results.append(
                ModelResult(
                    model=model,
                    ok_cases=0,
                    total_cases=len(TEST_CASES),
                    success_rate=0.0,
                    avg_ttft_ms=0.0,
                    avg_latency_ms=0.0,
                    json_success_rate=0.0,
                    realtime_pass_rate=0.0,
                    results=[],
                    recommended_tier="reject",
                )
            )

    print_summary(results)

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "models": [
            {
                **{k: v for k, v in asdict(item).items() if k != "results"},
                "results": [asdict(r) for r in item.results],
            }
            for item in results
        ],
    }
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_path = logs_dir / f"model_benchmark_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved report to: {output_path}")


if __name__ == "__main__":
    main()
