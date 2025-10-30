"""频道数据模型"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class Channel:
    """频道信息"""
    name: str
    url: str
    source_ip: str
    category: str
    channel_count: int
    location: Optional[str] = None
    tvg_id: Optional[str] = None
    tvg_logo: Optional[str] = None