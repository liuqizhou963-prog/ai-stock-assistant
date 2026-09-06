"""
记忆管理 API 端点的 Pydantic 模型
"""

from pydantic import BaseModel
from typing import List, Optional


class MemoryCreate(BaseModel):
    memory_type: str  # user/feedback/project/reference
    name: str
    description: str
    content: str
    tags: List[str] = []


class MemoryUpdate(BaseModel):
    description: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None


class MemorySearch(BaseModel):
    query: str
    memory_type: Optional[str] = None
