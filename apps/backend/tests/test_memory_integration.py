"""
记忆系统集成测试脚本
"""

import sys
from pathlib import Path

# 添加 app 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory import (
    ensure_memory_dir,
    load_memory,
    search_memories,
    get_all_memories
)

def test_memory_integration():
    """测试记忆系统集成"""
    print("=" * 60)
    print("记忆系统集成测试")
    print("=" * 60)

    # 1. 测试目录初始化
    print("\n1. 测试目录初始化...")
    ensure_memory_dir()
    print("✓ 目录初始化成功")

    # 2. 测试加载已有记忆
    print("\n2. 测试加载已有记忆...")
    memory = load_memory("trading-style")
    if memory:
        print(f"✓ 成功加载记忆: {memory['name']}")
        print(f"  描述: {memory['description']}")
        print(f"  类型: {memory['type']}")
    else:
        print("✗ 加载记忆失败")

    # 3. 测试搜索功能
    print("\n3. 测试搜索功能...")

    print("\n   测试 3.1: 搜索 'MACD'")
    results = search_memories("MACD")
    print(f"   找到 {len(results)} 条记忆:")
    for r in results:
        print(f"   - {r['name']}: {r['description']}")

    print("\n   测试 3.2: 搜索 '短线'")
    results = search_memories("短线")
    print(f"   找到 {len(results)} 条记忆:")
    for r in results:
        print(f"   - {r['name']}: {r['description']}")

    print("\n   测试 3.3: 搜索 'K线图'")
    results = search_memories("K线图")
    print(f"   找到 {len(results)} 条记忆:")
    for r in results:
        print(f"   - {r['name']}: {r['description']}")

    # 4. 测试获取所有记忆
    print("\n4. 测试获取所有记忆...")
    all_memories = get_all_memories()
    print(f"   User 记忆: {len(all_memories['user'])} 条")
    print(f"   Feedback 记忆: {len(all_memories['feedback'])} 条")
    print(f"   Project 记忆: {len(all_memories['project'])} 条")
    print(f"   Reference 记忆: {len(all_memories['reference'])} 条")

    # 5. 测试记忆召回（模拟对话场景）
    print("\n5. 测试记忆召回场景...")

    scenarios = [
        "帮我看看贵州茅台的 MACD 指标",
        "分析一下平安银行的技术面",
        "这只股票适合短线操作吗"
    ]

    for scenario in scenarios:
        print(f"\n   场景: '{scenario}'")
        results = search_memories(scenario)
        if results:
            print(f"   召回 {len(results)} 条相关记忆:")
            for r in results[:3]:  # 只显示前3条
                print(f"   - [{r['relevance']}] {r['name']}")
        else:
            print("   未找到相关记忆")

    print("\n" + "=" * 60)
    print("✓ 所有测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_memory_integration()
