"""IP信息数据模型"""
from dataclasses import dataclass

@dataclass
class IPInfo:
    """IP地址信息"""
    ip: str
    url: str
    category: str