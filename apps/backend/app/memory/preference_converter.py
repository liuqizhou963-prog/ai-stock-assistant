"""
偏好到记忆的智能转换模块
"""

from typing import Dict, Any, Optional
import re


def analyze_preference_type(label: str, value: str) -> Dict[str, Any]:
    """
    分析偏好内容，判断应该创建什么类型的记忆

    Returns:
        {
            "memory_type": "user/feedback/project/reference",
            "name": "kebab-case-name",
            "description": "简短描述",
            "content": "记忆内容",
            "tags": ["标签1", "标签2"]
        }
    """
    label_lower = label.lower()
    value_lower = value.lower()

    # 1. 识别用户画像类型（User Memory）
    user_keywords = [
        "交易风格", "风险偏好", "投资风格", "持仓周期", "交易周期",
        "我是", "我喜欢", "我偏好", "我习惯", "我倾向",
        "分析方法", "图表偏好", "指标偏好", "技术分析", "基本面分析"
    ]

    if any(kw in label or kw in value for kw in user_keywords):
        return {
            "memory_type": "user",
            "name": _generate_name("user", label),
            "description": f"用户偏好：{label}",
            "content": _format_user_memory(label, value),
            "tags": _extract_tags(label, value, ["用户画像", "偏好设置"])
        }

    # 2. 识别反馈/纠正类型（Feedback Memory）
    feedback_keywords = [
        "参数", "应该", "不对", "错误", "正确", "纠正", "修改",
        "要用", "不要用", "改成", "调整为"
    ]

    if any(kw in label or kw in value for kw in feedback_keywords):
        return {
            "memory_type": "feedback",
            "name": _generate_name("feedback", label),
            "description": f"用户反馈：{label}",
            "content": _format_feedback_memory(label, value),
            "tags": _extract_tags(label, value, ["用户反馈", "参数设置"])
        }

    # 3. 识别项目/研究类型（Project Memory）
    project_keywords = [
        "自选股", "关注", "研究", "策略", "计划", "目标",
        "正在", "准备", "打算", "想要"
    ]

    if any(kw in label or kw in value for kw in project_keywords):
        return {
            "memory_type": "project",
            "name": _generate_name("project", label),
            "description": f"项目记忆：{label}",
            "content": _format_project_memory(label, value),
            "tags": _extract_tags(label, value, ["项目记忆", "研究计划"])
        }

    # 4. 默认为用户画像
    return {
        "memory_type": "user",
        "name": _generate_name("user", label),
        "description": f"用户设置：{label}",
        "content": _format_default_memory(label, value),
        "tags": _extract_tags(label, value, ["用户设置"])
    }


def _generate_name(memory_type: str, label: str) -> str:
    """生成 kebab-case 记忆名称"""
    # 移除特殊字符，转换为拼音或英文
    name = label.lower()

    # 简单的中文关键词映射
    mappings = {
        "交易风格": "trading-style",
        "风险偏好": "risk-profile",
        "分析偏好": "analysis-preference",
        "图表偏好": "chart-preference",
        "指标偏好": "indicator-preference",
        "持仓周期": "holding-period",
        "自选股": "watchlist",
        "策略": "strategy",
        "参数": "params",
        "macd": "macd",
        "kdj": "kdj",
        "均线": "ma",
        "成交量": "volume",
    }

    for cn, en in mappings.items():
        if cn in name:
            name = name.replace(cn, en)

    # 移除非字母数字字符，用连字符替代
    name = re.sub(r'[^a-z0-9]+', '-', name)
    name = name.strip('-')

    # 如果转换后为空，使用时间戳
    if not name or len(name) < 3:
        import time
        name = f"{memory_type}-{int(time.time())}"

    return name


def _format_user_memory(label: str, value: str) -> str:
    """格式化用户画像记忆"""
    return f"""# {label}

{value}

**类型**: 用户画像
**来源**: 用户在偏好设置中手动添加
"""


def _format_feedback_memory(label: str, value: str) -> str:
    """格式化反馈记忆"""
    return f"""# {label}

{value}

**Why:** 用户明确要求的设置或纠正

**How to apply:**
- 在相关功能中应用此设置
- 优先级高于默认配置
"""


def _format_project_memory(label: str, value: str) -> str:
    """格式化项目记忆"""
    return f"""# {label}

{value}

**状态**: 进行中
**来源**: 用户偏好设置
"""


def _format_default_memory(label: str, value: str) -> str:
    """默认格式化"""
    return f"""# {label}

{value}
"""


def _extract_tags(label: str, value: str, default_tags: list) -> list:
    """从内容中提取标签"""
    tags = list(default_tags)

    # 技术分析相关
    tech_keywords = ["MACD", "KDJ", "RSI", "均线", "K线", "技术", "指标"]
    if any(kw in label or kw in value for kw in tech_keywords):
        tags.append("技术分析")

    # 基本面分析相关
    fundamental_keywords = ["基本面", "财报", "估值", "PE", "PB", "ROE", "利润"]
    if any(kw in label or kw in value for kw in fundamental_keywords):
        tags.append("基本面分析")

    # 短线交易
    if any(kw in label or kw in value for kw in ["短线", "日内", "波段"]):
        tags.append("短线交易")

    # 长线投资
    if any(kw in label or kw in value for kw in ["长线", "价值投资", "长期"]):
        tags.append("长线投资")

    return list(set(tags))  # 去重
