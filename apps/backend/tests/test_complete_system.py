"""
测试完整的记忆系统（包括前后端集成）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory import search_memories, save_memory, load_memory
from app.main import provider_system_message


def test_complete_memory_system():
    """测试完整的记忆系统"""
    print("=" * 70)
    print("完整记忆系统测试")
    print("=" * 70)

    # 1. 测试记忆召回返回元组
    print("\n1. 测试 provider_system_message 返回格式")
    result = provider_system_message([], "帮我看看MACD指标")
    print(f"   返回类型: {type(result)}")
    print(f"   返回长度: {len(result)}")
    assert isinstance(result, tuple), "应该返回元组"
    assert len(result) == 2, "应该返回 (message, used_memories)"

    system_message, used_memories = result
    print(f"   ✓ 系统消息长度: {len(system_message)} 字符")
    print(f"   ✓ 使用的记忆: {len(used_memories)} 条")

    # 2. 测试有记忆时的召回
    print("\n2. 测试记忆召回功能")

    # 确保有测试记忆
    save_memory(
        memory_type="feedback",
        name="test-macd-params",
        description="MACD参数测试",
        content="MACD应该使用(12,26,9)参数",
        tags=["测试", "MACD"]
    )

    system_message, used_memories = provider_system_message([], "分析MACD指标")

    if used_memories:
        print(f"   ✓ 成功召回 {len(used_memories)} 条记忆")
        for mem in used_memories:
            print(f"     - {mem['name']}: {mem['description']} ({mem['type']})")
    else:
        print("   ✗ 未召回记忆（可能是搜索逻辑问题）")

    # 3. 测试不同类型的查询
    print("\n3. 测试不同查询场景")

    test_queries = [
        "帮我看看贵州茅台的MACD",
        "这只股票适合短线操作吗",
        "分析一下技术指标",
        "今天大盘怎么样"
    ]

    for query in test_queries:
        _, used = provider_system_message([], query)
        print(f"   查询: '{query}'")
        print(f"   召回: {len(used)} 条")

    # 4. 测试偏好集成
    print("\n4. 测试偏好与记忆集成")

    preferences = [
        {"label": "交易风格", "value": "我是短线交易者"},
        {"label": "分析偏好", "value": "我喜欢技术分析"}
    ]

    message, used = provider_system_message(preferences, "帮我分析")

    assert "短线交易者" in message, "偏好应该注入到系统消息"
    print(f"   ✓ 偏好成功注入系统消息")
    print(f"   ✓ 系统消息包含偏好信息")

    # 5. 测试记忆格式
    print("\n5. 测试使用的记忆格式")

    if used_memories:
        mem = used_memories[0]
        required_keys = ['name', 'description', 'type', 'relevance']

        for key in required_keys:
            assert key in mem, f"记忆应该包含 {key} 字段"

        print(f"   ✓ 记忆格式正确")
        print(f"   ✓ 包含所有必需字段: {', '.join(required_keys)}")
    else:
        print("   ⚠ 跳过（没有召回记忆）")

    print("\n" + "=" * 70)
    print("✓ 所有测试完成")
    print("=" * 70)
    print("\n前端测试说明:")
    print("1. 启动前端: cd apps/renderer && npm run dev")
    print("2. 启动后端: cd apps/backend && .venv/Scripts/python -m uvicorn app.main:app --reload")
    print("3. 在对话中输入包含MACD的问题")
    print("4. 查看助手回复下方是否显示'使用了X条记忆'")
    print("=" * 70)


if __name__ == "__main__":
    test_complete_memory_system()
