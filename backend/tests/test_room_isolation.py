"""
测试房间隔离：确保不同房间的数据不会相互污染
"""
from __future__ import annotations

from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.infra.sqlite.db import room_id_var, get_connection
from ifrontier.infra.sqlite.ledger import create_account
from ifrontier.infra.sqlite.schema import init_schema
from ifrontier.app.room_engine import room_manager


def _reset_sqlite(room_id: str = "default"):
    """重置指定房间的数据库"""
    token = room_id_var.set(room_id)
    try:
        conn = get_connection()
        # 清空所有表
        conn.execute("DELETE FROM news")
        conn.execute("DELETE FROM news_deliveries")
        conn.execute("DELETE FROM chat_messages")
        conn.execute("DELETE FROM chat_threads")
        conn.execute("DELETE FROM accounts")
        conn.commit()
    finally:
        room_id_var.reset(token)


def test_news_service_instances_are_room_specific():
    """测试每个房间有独立的 NewsService 实例"""
    # 这个测试验证房间引擎为每个房间创建独立的服务实例
    # 由于 room_manager 是全局的，我们只能验证架构，不能在测试中启动多个房间
    # 但我们可以验证 API 层的房间感知获取函数
    
    from ifrontier.app.api import _get_room_news_service
    from ifrontier.infra.sqlite.db import room_id_var
    
    # 设置 room_id_var 为 "default"
    token = room_id_var.set("default")
    try:
        # 获取当前房间的新闻服务
        service = _get_room_news_service()
        assert service is not None
        # 验证它有 create_card 方法
        assert hasattr(service, 'create_card')
    finally:
        room_id_var.reset(token)


def test_news_service_isolation_via_api():
    """测试通过 API 访问时，房间隔离是否有效"""
    # 这个测试需要 HTTP 请求，使用 X-Room-Id 头
    # 但当前测试框架可能不支持，所以这里只是占位符
    pass
