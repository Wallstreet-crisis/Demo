"""项目统一日志模块。

所有后端模块应使用 `get_logger(__name__)` 获取 logger，
而非直接调用 print()。日志级别由环境变量 IF_LOG_LEVEL 控制。
"""
import logging
import os

_LOG_LEVEL = os.getenv("IF_LOG_LEVEL", "INFO").upper()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s — %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
    return logger
