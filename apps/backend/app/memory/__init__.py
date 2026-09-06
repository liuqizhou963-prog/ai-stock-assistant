# apps/backend/app/memory/__init__.py

from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import frontmatter  # 需要安装: pip install python-frontmatter
import os

STATE_DIR = Path(os.getenv("DESKTOP_AGENT_STATE_DIR", Path(__file__).resolve().parents[4] / "state"))
MEMORY_DIR = STATE_DIR / "memory"

def ensure_memory_dir():
    """确保记忆目录存在"""
    for subdir in ["user", "feedback", "project", "reference"]:
        (MEMORY_DIR / subdir).mkdir(parents=True, exist_ok=True)

    index_file = MEMORY_DIR / "MEMORY.md"
    if not index_file.exists():
        index_file.write_text(
            f"# 股票助手记忆索引\n\n最后更新：{datetime.now().strftime('%Y-%m-%d')}\n\n"
            "## 用户画像 (User)\n\n暂无记忆\n\n"
            "## 用户反馈 (Feedback)\n\n暂无记忆\n\n"
            "## 项目记忆 (Project)\n\n暂无记忆\n\n"
            "## 外部资源 (Reference)\n\n暂无记忆\n",
            encoding="utf-8"
        )

def load_memory(name: str) -> Optional[Dict[str, Any]]:
    """
    加载指定记忆

    Args:
        name: 记忆文件的 name 字段（不含路径和扩展名）

    Returns:
        记忆内容字典，包含 metadata 和 content；如果不存在返回 None
    """
    # 在所有子目录中搜索
    for subdir in ["user", "feedback", "project", "reference"]:
        file_path = MEMORY_DIR / subdir / f"{name}.md"
        if file_path.exists():
            post = frontmatter.load(file_path)
            return {
                "name": post.metadata.get("name"),
                "description": post.metadata.get("description"),
                "type": post.metadata.get("metadata", {}).get("type"),
                "content": post.content,
                "metadata": post.metadata
            }
    return None

def search_memories(query: str, memory_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    搜索相关记忆

    Args:
        query: 搜索关键词
        memory_type: 记忆类型过滤 (user/feedback/project/reference)

    Returns:
        相关记忆列表，按相关性排序
    """
    results = []
    search_dirs = [memory_type] if memory_type else ["user", "feedback", "project", "reference"]

    for subdir in search_dirs:
        dir_path = MEMORY_DIR / subdir
        if not dir_path.exists():
            continue

        for file_path in dir_path.glob("*.md"):
            if file_path.name == "MEMORY.md":
                continue

            try:
                post = frontmatter.load(file_path)
                description = post.metadata.get("description", "")
                content = post.content

                # 简单的关键词匹配（可以改进为向量检索）
                if query.lower() in description.lower() or query.lower() in content.lower():
                    results.append({
                        "name": post.metadata.get("name"),
                        "description": description,
                        "type": post.metadata.get("metadata", {}).get("type"),
                        "relevance": "high" if query.lower() in description.lower() else "medium",
                        "file_path": str(file_path)
                    })
            except Exception as e:
                print(f"Error loading memory {file_path}: {e}")
                continue

    return sorted(results, key=lambda x: 0 if x["relevance"] == "high" else 1)

def save_memory(
    memory_type: str,
    name: str,
    description: str,
    content: str,
    tags: Optional[List[str]] = None
):
    """
    保存或更新记忆

    Args:
        memory_type: user/feedback/project/reference
        name: kebab-case 标识符
        description: 一句话描述
        content: 记忆主体内容
        tags: 标签列表
    """
    if memory_type not in ["user", "feedback", "project", "reference"]:
        raise ValueError(f"Invalid memory_type: {memory_type}")

    file_path = MEMORY_DIR / memory_type / f"{name}.md"

    now = datetime.now().strftime("%Y-%m-%d")
    is_new = not file_path.exists()

    # 如果是更新，保留原有的 created 时间
    created_date = now
    if not is_new:
        try:
            old_post = frontmatter.load(file_path)
            created_date = old_post.metadata.get("metadata", {}).get("created", now)
        except:
            pass

    post = frontmatter.Post(content)
    post.metadata = {
        "name": name,
        "description": description,
        "metadata": {
            "type": memory_type,
            "created": created_date,
            "updated": now,
            "tags": tags or []
        }
    }

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    # 更新索引
    update_memory_index()

def delete_memory(name: str) -> bool:
    """
    删除指定记忆

    Args:
        name: 记忆名称

    Returns:
        是否成功删除
    """
    for subdir in ["user", "feedback", "project", "reference"]:
        file_path = MEMORY_DIR / subdir / f"{name}.md"
        if file_path.exists():
            file_path.unlink()
            update_memory_index()
            return True
    return False

def update_memory_index():
    """更新 MEMORY.md 索引文件"""
    index_path = MEMORY_DIR / "MEMORY.md"

    sections = {
        "user": {"header": "## 用户画像 (User)\n\n", "items": []},
        "feedback": {"header": "## 用户反馈 (Feedback)\n\n", "items": []},
        "project": {"header": "## 项目记忆 (Project)\n\n", "items": []},
        "reference": {"header": "## 外部资源 (Reference)\n\n", "items": []}
    }

    for mem_type in sections.keys():
        dir_path = MEMORY_DIR / mem_type
        if not dir_path.exists():
            continue

        for file_path in sorted(dir_path.glob("*.md")):
            try:
                post = frontmatter.load(file_path)
                name = post.metadata.get("name", file_path.stem)
                desc = post.metadata.get("description", "")
                sections[mem_type]["items"].append(
                    f"- [{name}]({mem_type}/{file_path.name}) — {desc}\n"
                )
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                continue

    content = f"# 股票助手记忆索引\n\n最后更新：{datetime.now().strftime('%Y-%m-%d')}\n\n"

    for mem_type in ["user", "feedback", "project", "reference"]:
        content += sections[mem_type]["header"]
        if sections[mem_type]["items"]:
            content += "".join(sections[mem_type]["items"])
        else:
            content += "暂无记忆\n"
        content += "\n"

    index_path.write_text(content, encoding="utf-8")

def get_all_memories() -> Dict[str, List[Dict[str, Any]]]:
    """
    获取所有记忆，按类型分组

    Returns:
        按类型分组的记忆字典
    """
    all_memories = {
        "user": [],
        "feedback": [],
        "project": [],
        "reference": []
    }

    for mem_type in all_memories.keys():
        dir_path = MEMORY_DIR / mem_type
        if not dir_path.exists():
            continue

        for file_path in sorted(dir_path.glob("*.md")):
            try:
                post = frontmatter.load(file_path)
                all_memories[mem_type].append({
                    "name": post.metadata.get("name"),
                    "description": post.metadata.get("description"),
                    "content": post.content,
                    "metadata": post.metadata,
                    "file_path": str(file_path)
                })
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                continue

    return all_memories
