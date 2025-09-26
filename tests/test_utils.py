"""工具模块测试"""
import unittest
from ..utils.m3u_processor import M3UProcessor
from ..models.channel import Channel

class TestM3UProcessor(unittest.TestCase):
    """M3U处理器测试类"""
    
    def setUp(self):
        """测试初始化"""
        self.processor = M3UProcessor()
        self.test_channels = [
            Channel(name="CCTV1", url="http://example.com/cctv1", 
                   source_ip="192.168.1.1", category="组播", channel_count=100),
            Channel(name="CCTV2", url="http://example.com/cctv2", 
                   source_ip="192.168.1.1", category="组播", channel_count=100)
        ]
    
    def test_save_to_m3u(self):
        """测试保存为M3U文件"""
        # 测试将在实际环境中实现
        pass
        
    def test_extract_location(self):
        """测试提取地理信息"""
        self.assertEqual(self.processor._extract_location("Hotel IPTV"), "酒店")
        self.assertEqual(self.processor._extract_location("联通IPTV"), "联通")
        self.assertEqual(self.processor._extract_location("未知分类"), "未知地区")