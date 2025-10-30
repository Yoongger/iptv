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
                
                # 从span的完整文本中提取位置信息
                # 格式如：113.227.102.202频道数：30 新上线 2025-10-27 14:35上线 辽宁省大连市酒店 联通ADSL
                full_text = span.get_text(strip=True)
                
                # 提取位置信息 - 从IP地址后面的文本中提取完整的位置描述
                location = ""
                if full_text and len(full_text) > len(ip_text):
                    # 获取IP地址后面的完整描述
                    description = full_text[len(ip_text):].strip()
                    
                    # 提取上线时间信息
                    online_time = ""
                    import re
                    time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})上线', description)
                    if time_match:
                        online_time = time_match.group(1)
                    
                    # 提取位置和运营商信息（上线时间后面的部分）
                    if time_match:
                        location_part = description[time_match.end():].strip()
                        if location_part:
                            location = location_part
                    else:
                        # 如果没有找到上线时间，尝试提取位置信息
                        # 移除频道数、新上线等信息
                        cleaned_desc = re.sub(r'频道数：\d+', '', description)
                        cleaned_desc = re.sub(r'新上线', '', cleaned_desc)
                        cleaned_desc = cleaned_desc.strip()
                        if cleaned_desc:
                            location = cleaned_desc
                
                ip_addresses.append(IPInfo(
                    ip=ip_text,
                    url=urljoin(self.base_url, href),
                    category=category,
                    location=location,
                    online_time=online_time
                ))
                self.logger.info(f"找到IP: {ip_text}, 分类: {category}, 位置: {location}, 上线时间: {online_time}")
        
        return ip_addresses