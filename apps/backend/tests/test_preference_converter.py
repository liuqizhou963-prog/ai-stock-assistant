"""
测试偏好到记忆的自动转换功能
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory.preference_converter import analyze_preference_type


def test_preference_conversion():
    """测试各种偏好的智能识别和转换"""
    print("=" * 60)
    print("偏好到记忆智能转换测试")
    print("=" * 60)

    test_cases = [
        # 用户画像类型
        {
            "label": "交易风格",
            "value": "我是短线交易者，喜欢做3-7天的波段",
            "expected_type": "user"
        },
        {
            "label": "分析偏好",
            "value": "我偏好技术分析，主要看MACD和KDJ指标",
            "expected_type": "user"
        },
        {
            "label": "图表偏好",
            "value": "我喜欢K线图，不喜欢折线图",
            "expected_type": "user"
        },

        # 反馈/纠正类型
        {
            "label": "MACD参数",
            "value": "MACD参数应该用(12,26,9)，不要用(12,26,10)",
            "expected_type": "feedback"
        },
        {
            "label": "均线设置",
            "value": "均线要调整为MA5、MA10、MA20",
            "expected_type": "feedback"
        },

        # 项目/研究类型
        {
            "label": "自选股",
            "value": "我正在关注科技板块，重点研究AI和半导体方向",
            "expected_type": "project"
        },
        {
            "label": "策略研究",
            "value": "我打算开发一个MACD动量突破策略",
            "expected_type": "project"
        },

        # 默认类型
        {
            "label": "其他设置",
            "value": "这是一个普通的设置",
            "expected_type": "user"
        }
    ]

    passed = 0
    failed = 0

    for i, case in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {case['label']}")
        print(f"  内容: {case['value']}")

        result = analyze_preference_type(case["label"], case["value"])

        print(f"  识别类型: {result['memory_type']}")
        print(f"  生成名称: {result['name']}")
        print(f"  描述: {result['description']}")
        print(f"  标签: {', '.join(result['tags'])}")

        if result['memory_type'] == case['expected_type']:
            print(f"  结果: ✓ 通过")
            passed += 1
        else:
            print(f"  结果: ✗ 失败 (期望: {case['expected_type']})")
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试完成: {passed} 通过, {failed} 失败")
    print("=" * 60)


if __name__ == "__main__":
    test_preference_conversion()
