"""IP地址爬取模块"""
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urljoin
from models.ip_info import IPInfo
from crawler.base_crawler import BaseCrawler

class IPCrawler(BaseCrawler):
    """IP地址爬取类"""
    
    def parse_main_page(self) -> List[IPInfo]:
        """解析主页面，获取IP地址列表
        
        Returns:
            IP信息列表
        """
        url = f"{self.base_url}/hoteliptv2025.php"
        self.logger.info(f"请求主页面: {url}")
        
        response = self.request_with_retry(url)
        if not response:
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        ip_addresses = []
        
        # 查找所有包含IP地址的span标签
        ip_spans = soup.find_all('span', class_='sh')
        
        for span in ip_spans:
            a_tag = span.find('a')
            if a_tag and a_tag.get('href'):
                ip_text = a_tag.get_text(strip=True)
                href = a_tag['href']
                
                # 确定分类
                parent_div = span.find_parent('div', class_='box')
                if parent_div:
                    category_div = parent_div.find('div', style=lambda x: x and 'margin-top: -30px' in x)
                    category = category_div.get_text(strip=True) if category_div else "未知分类"
                else:
                    category = "未知分类"
                
                ip_addresses.append(IPInfo(
                    ip=ip_text,
                    url=urljoin(self.base_url, href),
                    category=category
                ))
                self.logger.info(f"找到IP: {ip_text}, 分类: {category}")
        
        return ip_addresses