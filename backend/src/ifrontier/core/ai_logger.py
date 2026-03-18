import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

# 专门用于记录 AI 代理行为的日志记录器
# 它会同时输出到 console (带颜色/前缀) 和 backend/logs/ai_behavior.log

LOG_DIR = os.path.join(os.getcwd(), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_file = os.path.join(LOG_DIR, "ai_behavior.log")

# 配置 logger
ai_logger = logging.getLogger("ai_behavior")
ai_logger.setLevel(logging.INFO)

# 文件处理器
fh = logging.FileHandler(log_file, encoding="utf-8")
fh.setLevel(logging.INFO)
fh_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
fh.setFormatter(fh_formatter)
ai_logger.addHandler(fh)

_console_enabled = str(os.getenv("IF_AI_LOG_TO_CONSOLE") or "").strip().lower() in {"1", "true", "yes", "on"}
if _console_enabled:
    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # 为控制台日志增加醒目的前缀和颜色（简单 ANSI）
    class AiConsoleFormatter(logging.Formatter):
        def format(self, record):
            prefix = "🤖 [AI_AGENT]"
            if record.levelname == "ERROR":
                color = "\033[91m" # Red
            elif record.levelname == "WARNING":
                color = "\033[93m" # Yellow
            else:
                color = "\033[92m" # Green
            
            reset = "\033[0m"
            return f"{color}{prefix} {record.getMessage()}{reset}"

    ch.setFormatter(AiConsoleFormatter())
    ai_logger.addHandler(ch)

def log_ai_action(agent_id: str, action_type: str, detail: str, context: dict = None):
    """记录 AI 的一次行为决策。"""
    msg = f"<{agent_id}> [{action_type}] {detail}"
    if context:
        msg += f" | CTX: {context}"
    ai_logger.info(msg)

def log_ai_thought(agent_id: str, news_context: str, decision: str):
    """记录 AI 的思维过程（针对新闻或社交输入）。"""
    msg = f"🧠 <{agent_id}> THINKING: {news_context[:100]}... -> DECISION: {decision}"
    ai_logger.info(msg)


def log_llm_metric(
    *,
    task: str,
    profile: str,
    model: str,
    duration_ms: float,
    success: bool,
    prompt_chars: int,
    max_tokens: int,
    extra: Optional[Dict[str, Any]] = None,
):
    payload = {
        "task": str(task),
        "profile": str(profile),
        "model": str(model),
        "duration_ms": round(float(duration_ms), 2),
        "success": bool(success),
        "prompt_chars": int(prompt_chars),
        "max_tokens": int(max_tokens),
    }
    if extra:
        payload.update(extra)
    ai_logger.info(f"[LLM_METRIC] {payload}")
