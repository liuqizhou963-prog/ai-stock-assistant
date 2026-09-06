"""
记忆层单元测试
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from datetime import datetime

# 测试前需要设置环境变量指向临时目录
import os
import sys

# 添加 app 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory import (
    ensure_memory_dir,
    load_memory,
    search_memories,
    save_memory,
    delete_memory,
    update_memory_index,
    get_all_memories,
    MEMORY_DIR
)


@pytest.fixture
def temp_memory_dir(monkeypatch):
    """创建临时记忆目录用于测试"""
    temp_dir = tempfile.mkdtemp()
    temp_state = Path(temp_dir) / "state"
    temp_state.mkdir()

    # 修改模块中的 MEMORY_DIR
    monkeypatch.setattr('app.memory.STATE_DIR', temp_state)
    monkeypatch.setattr('app.memory.MEMORY_DIR', temp_state / "memory")

    yield temp_state / "memory"

    # 清理
    shutil.rmtree(temp_dir)


class TestMemoryBasics:
    """基础功能测试"""

    def test_ensure_memory_dir(self, temp_memory_dir, monkeypatch):
        """测试目录创建"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        assert (temp_memory_dir / "user").exists()
        assert (temp_memory_dir / "feedback").exists()
        assert (temp_memory_dir / "project").exists()
        assert (temp_memory_dir / "reference").exists()
        assert (temp_memory_dir / "MEMORY.md").exists()

    def test_save_and_load_memory(self, temp_memory_dir, monkeypatch):
        """测试保存和加载记忆"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        # 保存记忆
        save_memory(
            memory_type="user",
            name="test-trading-style",
            description="用户是短线交易者",
            content="用户主要进行短线交易，持仓周期 3-7 天",
            tags=["交易风格", "短线"]
        )

        # 加载记忆
        memory = load_memory("test-trading-style")

        assert memory is not None
        assert memory["name"] == "test-trading-style"
        assert memory["description"] == "用户是短线交易者"
        assert "短线交易" in memory["content"]
        assert memory["type"] == "user"

    def test_search_memories(self, temp_memory_dir, monkeypatch):
        """测试记忆搜索"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        # 创建多个记忆
        save_memory("user", "trading-style", "短线交易者", "用户是短线交易者，关注技术分析", ["短线"])
        save_memory("feedback", "macd-params", "MACD参数纠正", "用户要求使用 MACD(12,26,9)", ["MACD"])
        save_memory("project", "watchlist", "科技股自选", "关注 AI 和半导体", ["科技"])

        # 搜索
        results = search_memories("MACD")
        assert len(results) == 1
        assert results[0]["name"] == "macd-params"

        results = search_memories("短线")
        assert len(results) == 1
        assert results[0]["type"] == "user"

        results = search_memories("科技")
        assert len(results) == 1

    def test_delete_memory(self, temp_memory_dir, monkeypatch):
        """测试删除记忆"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        # 创建记忆
        save_memory("user", "test-memory", "测试记忆", "这是测试内容")

        # 验证存在
        assert load_memory("test-memory") is not None

        # 删除
        result = delete_memory("test-memory")
        assert result is True

        # 验证已删除
        assert load_memory("test-memory") is None

    def test_update_memory(self, temp_memory_dir, monkeypatch):
        """测试更新记忆"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        # 创建记忆
        save_memory("user", "test-update", "原始描述", "原始内容")
        original = load_memory("test-update")
        created_date = original["metadata"]["metadata"]["created"]

        # 更新记忆
        save_memory("user", "test-update", "更新描述", "更新内容", ["新标签"])
        updated = load_memory("test-update")

        assert updated["description"] == "更新描述"
        assert updated["content"] == "更新内容"
        assert updated["metadata"]["metadata"]["created"] == created_date
        assert "新标签" in updated["metadata"]["metadata"]["tags"]

    def test_get_all_memories(self, temp_memory_dir, monkeypatch):
        """测试获取所有记忆"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        # 创建不同类型的记忆
        save_memory("user", "user1", "用户记忆1", "内容1")
        save_memory("user", "user2", "用户记忆2", "内容2")
        save_memory("feedback", "feedback1", "反馈记忆1", "内容3")
        save_memory("project", "project1", "项目记忆1", "内容4")

        all_memories = get_all_memories()

        assert len(all_memories["user"]) == 2
        assert len(all_memories["feedback"]) == 1
        assert len(all_memories["project"]) == 1
        assert len(all_memories["reference"]) == 0

    def test_memory_index_update(self, temp_memory_dir, monkeypatch):
        """测试索引文件更新"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        # 创建记忆
        save_memory("user", "test-index", "测试索引", "测试内容")

        # 读取索引文件
        index_file = temp_memory_dir / "MEMORY.md"
        content = index_file.read_text(encoding="utf-8")

        assert "test-index" in content
        assert "测试索引" in content
        assert "用户画像 (User)" in content


class TestMemoryTypes:
    """不同记忆类型的测试"""

    def test_user_memory(self, temp_memory_dir, monkeypatch):
        """测试用户画像记忆"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        save_memory(
            "user",
            "trading-style",
            "用户是短线交易者，偏好技术分析",
            """用户主要进行短线交易，持仓周期 3-7 天。

- 交易周期：短线为主（3-7天）
- 分析方法：技术分析 70% + 基本面筛选 30%
- 关注指标：MACD、KDJ、成交量""",
            ["交易风格", "短线", "技术分析"]
        )

        memory = load_memory("trading-style")
        assert memory["type"] == "user"
        assert "MACD" in memory["content"]

    def test_feedback_memory(self, temp_memory_dir, monkeypatch):
        """测试反馈记忆"""
        monkeypatch.setattr('app.memory.MEMORY_DIR', temp_memory_dir)
        ensure_memory_dir()

        save_memory(
            "feedback",
            "macd-params",
            "MACD参数纠正为(12,26,9)",
            """用户指出 MACD 参数应为 (12,26,9)。

**Why:** 这是市场标准参数

**How to apply:** 所有 MACD 计算必须使用此参数""",
            ["MACD", "参数纠正"]
        )

        memory = load_memory("macd-params")
        assert memory["type"] == "feedback"
        assert "Why:" in memory["content"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
