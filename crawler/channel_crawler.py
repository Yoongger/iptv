"""频道爬取模块"""
import re
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urljoin
from models.channel import Channel
from models.ip_info import IPInfo
from crawler.base_crawler import BaseCrawler
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
        
        response = self.request_with_retry(ip_info.url)
        if not response:
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        channel_links = []
        
        # 查找频道列表链接
        result_divs = soup.find_all('div', class_='result')
        
        for div in result_divs:
            channel_div = div.find('div', class_='channel')
            if channel_div:
                a_tag = channel_div.find('a', href=True)
                if a_tag and 'hotellist.html' in a_tag['href']:
                    # 提取频道数
                    channel_count = 0
                    count_span = div.find('span', style='font-size: 18px;')
                    if count_span:
                        try:
                            channel_count = int(count_span.get_text(strip=True))
                        except ValueError:
                            pass
                    
                    channel_links.append({
                        'ip': ip_info.ip,
                        'category': ip_info.category,
                        'channel_url': urljoin(self.base_url, a_tag['href']),
                        'channel_count': channel_count,
                        'title': a_tag.get_text(strip=True)
                    })
                    self.logger.info(f"找到频道列表: {a_tag['href']}, 频道数: {channel_count}")
        
        return channel_links

    def parse_channel_list_page(self, channel_info: Dict) -> List[Channel]:
        """解析频道列表页，通过API获取具体的频道链接
        
        Args:
            channel_info: 频道列表信息字典
            
        Returns:
            频道对象列表
        """
        self.logger.info(f"解析频道列表: {channel_info['channel_url']}")
        
        # 从URL中提取IP和端口
        ip_port_match = re.search(r's=([^&]+)', channel_info['channel_url'])
        if not ip_port_match:
            self.logger.error(f"无法从URL中提取IP和端口: {channel_info['channel_url']}")
            return []
            
        ip_port = ip_port_match.group(1)
        
        # 直接调用API获取频道数据
        api_url = f"{self.base_url}/listall.php?s={ip_port}"
        self.logger.info(f"调用API: {api_url}")
        
        # 保存原始headers
        original_headers = self.session.headers.copy()
        
        # 添加更多必要的请求头
        enhanced_headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': channel_info['channel_url'],
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            'Origin': self.base_url,
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        self.session.headers.update(enhanced_headers)
        
        # 尝试使用POST请求，有些API可能更改了请求方式
        try:
            response = self.session.post(api_url, timeout=30)
            if response.status_code != 200:
                # 如果POST失败，回退到GET请求
                response = self.request_with_retry(api_url)
        except:
            # 如果POST请求出错，使用带重试的GET请求
            response = self.request_with_retry(api_url)
        
        # 恢复原始headers
        self.session.headers = original_headers
        if not response:
            return []
            
        channels = []
        
        try:
            # 解析API响应
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找所有频道结果
            result_divs = soup.find_all('div', class_='result')
            self.logger.info(f"API返回 {len(result_divs)} 个频道结果")
            
            for div in result_divs:
                try:
                    # 获取频道名称
                    channel_name = ""
                    channel_div = div.find('div', class_='channel')
                    if channel_div:
                        name_div = channel_div.find('div', style=lambda x: x and 'float: left' in x)
                        if name_div:
                            channel_name = name_div.get_text(strip=True)
                    
                    # 获取频道链接
                    stream_url = ""
                    m3u8_div = div.find('div', class_='m3u8')
                    if m3u8_div:
                        # 从onclick属性中提取链接
                        img_tags = m3u8_div.find_all('img', onclick=True)
                        for img in img_tags:
                            onclick = img.get('onclick', '')
                            if 'copyto(' in onclick:
                                match = re.search(r"copyto\('([^']+)'\)", onclick)
                                if match:
                                    stream_url = match.group(1)
                                    break
                        
                        # 如果onclick中没有找到，尝试从td文本中获取
                        if not stream_url:
                            td_texts = m3u8_div.find_all('td', style=lambda x: x and 'padding-left: 6px' in x)
                            for td in td_texts:
                                text = td.get_text(strip=True)
                                if text.startswith(('http://', 'https://')):
                                    stream_url = text
                                    break
                    
                    if channel_name and stream_url:
                        channel_data = Channel(
                            name=channel_name,
                            url=stream_url,
                            source_ip=channel_info['ip'],
                            category=channel_info['category'],
                            channel_count=channel_info['channel_count']
                        )
                        channels.append(channel_data)
                        self.logger.info(f"找到频道: {channel_name}")
                        
                except Exception as e:
                    self.logger.error(f"解析频道时出错: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"解析API响应时出错: {e}")
        
        self.logger.info(f"从 {ip_port} 获取到 {len(channels)} 个频道")
        return channels