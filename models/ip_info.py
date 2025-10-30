"""IP信息数据模型"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class IPInfo:
    """IP地址信息"""
    ip: str
    url: str
    category: str
    channel_count: Optional[int] = 0
    location: Optional[str] = ""
    online_time: Optional[str] = ""
    survival_days: Optional[str] = ""