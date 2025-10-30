"""频道爬取模块"""
import re
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urljoin
from models.channel import Channel
from models.ip_info import IPInfo
from crawler.base_crawler import BaseCrawler
from crawler.selenium_channel_crawler import SeleniumChannelCrawler
from config.constants import API_HEADERS

class ChannelCrawler(BaseCrawler):
    """频道爬取类"""
    
    def parse_ip_detail_page(self, ip_info: IPInfo) -> List[Dict]:
        """解析IP详情页，获取频道列表链接
        
        Args:
            ip_info: IP信息对象
            
        Returns:
            频道列表信息字典
        """
        self.logger.info(f"解析IP详情页: {ip_info.ip}")
        
        # 新的页面结构下，IP详情页URL本身就是频道列表页
        # 直接使用IP信息中的URL作为频道列表链接
        channel_links = []
        
        # 从URL中提取tk参数
        tk_match = re.search(r'tk=([^&]+)', ip_info.url)
        tk_value = tk_match.group(1) if tk_match else "34bc615c"
        
        # 构建频道列表URL
        channel_url = f"https://tonkiang.us/channellist.html?ip={ip_info.ip}&tk={tk_value}&p=1"
        
        channel_links.append({
            'ip': ip_info.ip,
            'category': ip_info.category,
            'channel_url': channel_url,
            'channel_count': ip_info.channel_count,
            'location': ip_info.location,  # 添加完整的位置信息
            'title': f"{ip_info.ip} - {ip_info.category}"
        })
        
        self.logger.info(f"找到频道列表: {channel_url}, 频道数: {ip_info.channel_count}")
        
        return channel_links

    def parse_channel_list_page(self, channel_info: Dict) -> List[Channel]:
        """解析频道列表页，获取具体的频道链接
        
        Args:
            channel_info: 频道列表信息字典
            
        Returns:
            频道对象列表
        """
        self.logger.info(f"解析频道列表: {channel_info['channel_url']}")
        
        # 使用Selenium处理动态加载的页面
        selenium_crawler = SeleniumChannelCrawler(headless=True)
        
        try:
            channels = selenium_crawler.parse_channel_list_page(channel_info)
            self.logger.info(f"从 {channel_info['ip']} 获取到 {len(channels)} 个频道")
            return channels
        except Exception as e:
            self.logger.error(f"解析频道列表页时出错: {e}")
            return []
        finally:
            selenium_crawler.cleanup()