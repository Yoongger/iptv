"""简化版反爬虫爬虫模块 - 专门针对tonkiang.us"""
import time
import random
import json
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from config.logger import setup_logger
from config.constants import BASE_URL

class SimpleAntiCrawler:
    """简化版反爬虫爬虫类"""
    
    def __init__(self, use_proxy=False, proxy_file="proxies.json"):
        self.session = requests.Session()
        self.base_url = BASE_URL
        self.logger = setup_logger("SimpleAntiCrawler")
        self.use_proxy = use_proxy
        self.proxy_file = proxy_file
        self.proxies = self._load_proxies() if use_proxy else []
        self.current_proxy_index = 0
        self.last_request_time = 0
        
        # 真实User-Agent列表
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
        ]
        
        # 设置基础请求头
        self._init_headers()
    
    def _load_proxies(self):
        """加载代理配置"""
        try:
            with open(self.proxy_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                proxies = data.get('proxies', [])
                return [p for p in proxies if 'ip' in p and 'port' in p]
        except Exception as e:
            self.logger.warning(f"加载代理失败: {e}")
            return []
    
    def _init_headers(self):
        """初始化请求头"""
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Sec-GPC': '1'
        }
        self.session.headers.update(headers)
    
    def _get_delay(self):
        """获取随机延迟"""
        return random.uniform(2.0, 6.0)
    
    def _rotate_proxy(self):
        """轮换代理"""
        if not self.proxies:
            return None
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return self.proxies[self.current_proxy_index]
    
    def smart_request(self, url, max_retries=3):
        """智能请求"""
        for attempt in range(max_retries):
            try:
                # 控制请求频率
                current_time = time.time()
                if self.last_request_time > 0:
                    delay = self._get_delay()
                    elapsed = current_time - self.last_request_time
                    if elapsed < delay:
                        time.sleep(delay - elapsed)
                
                # 设置随机User-Agent
                headers = self.session.headers.copy()
                headers['User-Agent'] = random.choice(self.user_agents)
                
                # 设置代理
                proxies = None
                if self.use_proxy and self.proxies:
                    proxy = self.proxies[self.current_proxy_index]
                    proxy_url = f"http://{proxy['ip']}:{proxy['port']}"
                    if proxy.get('username') and proxy.get('password'):
                        proxy_url = f"http://{proxy['username']}:{proxy['password']}@{proxy['ip']}:{proxy['port']}"
                    proxies = {'http': proxy_url, 'https': proxy_url}
                
                # 发送请求
                response = self.session.get(
                    url,
                    headers=headers,
                    proxies=proxies,
                    timeout=30,
                    verify=False,
                    allow_redirects=True
                )
                
                self.last_request_time = time.time()
                
                # 检查响应
                if response.status_code == 200:
                    # 检查是否被重定向或检测到爬虫
                    if self._is_blocked(response):
                        self.logger.warning(f"检测到反爬虫措施 (尝试 {attempt + 1}/{max_retries})")
                        if self.use_proxy:
                            self._rotate_proxy()
                        time.sleep(10)
                        continue
                    
                    # 确保正确编码
                    if response.encoding is None or response.encoding.lower() == 'iso-8859-1':
                        response.encoding = 'utf-8'
                    
                    return response
                
                elif response.status_code in [403, 429, 503]:
                    self.logger.warning(f"服务器拒绝访问: {response.status_code}")
                    if self.use_proxy:
                        self._rotate_proxy()
                    time.sleep(10)
                
                else:
                    self.logger.error(f"请求失败: {response.status_code}")
                    if attempt == max_retries - 1:
                        return None
                    time.sleep(5)
                    
            except Exception as e:
                self.logger.error(f"请求异常: {e}")
                if attempt == max_retries - 1:
                    return None
                if self.use_proxy:
                    self._rotate_proxy()
                time.sleep(5)
        
        return None
    
    def _is_blocked(self, response):
        """检查是否被反爬虫阻止"""
        text = response.text.lower()
        blocked_indicators = [
            '验证码', 'captcha', 'robot', 'bot', 'blocked', 'access denied',
            'security check', 'human verification'
        ]
        return any(indicator in text for indicator in blocked_indicators)
    
    def parse_main_page(self):
        """解析主页面获取IP列表"""
        url = f"{self.base_url}/hoteliptv2025.php"
        self.logger.info(f"解析主页面: {url}")
        
        response = self.smart_request(url)
        if not response:
            self.logger.error("无法获取主页面")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        ip_list = []
        
        # 方法1: 查找sh类的span标签
        sh_spans = soup.find_all('span', class_='sh')
        self.logger.info(f"找到 {len(sh_spans)} 个sh类的span标签")
        
        for span in sh_spans:
            try:
                a_tag = span.find('a')
                if a_tag:
                    ip_text = a_tag.get_text(strip=True)
                    href = a_tag.get('href', '')
                    
                    # 验证IP格式
                    import re
                    if re.match(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', ip_text):
                        # 获取分类
                        category = "未知分类"
                        parent_box = span.find_parent('div', class_='box')
                        if parent_box:
                            box_text = parent_box.get_text()
                            if '酒店' in box_text:
                                category = "酒店"
                            elif '组播' in box_text:
                                category = "组播"
                        
                        # 构建完整URL
                        if not href.startswith('http'):
                            href = urljoin(self.base_url, href)
                        
                        ip_info = {
                            'ip': ip_text,
                            'url': href,
                            'category': category
                        }
                        ip_list.append(ip_info)
                        self.logger.info(f"找到IP: {ip_text}, 分类: {category}")
                        
            except Exception as e:
                self.logger.error(f"解析span出错: {e}")
                continue
        
        # 方法2: 如果方法1失败，使用正则表达式
        if not ip_list:
            self.logger.info("使用方法2: 正则表达式提取")
            import re
            ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
            ips = set(re.findall(ip_pattern, response.text))
            
            for ip in ips:
                try:
                    parts = ip.split('.')
                    if len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts):
                        href = f"{self.base_url}/hoteliptv2025.php?s={ip}"
                        ip_info = {
                            'ip': ip,
                            'url': href,
                            'category': "正则提取"
                        }
                        ip_list.append(ip_info)
                except:
                    continue
        
        self.logger.info(f"共找到 {len(ip_list)} 个IP地址")
        return ip_list
    
    def parse_ip_channels(self, ip_info):
        """解析IP详情页获取频道列表"""
        self.logger.info(f"解析IP详情页: {ip_info['ip']}")
        
        response = self.smart_request(ip_info['url'])
        if not response:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        channels = []
        
        # 查找频道链接
        all_links = soup.find_all('a', href=True)
        for link in all_links:
            href = link.get('href', '')
            if ('hotellist.html' in href or 'hoteliptv2025.php' in href) and ip_info['ip'] in href:
                link_text = link.get_text(strip=True)
                
                # 提取频道数量
                import re
                count_match = re.search(r'(\d+)\s*频道', link_text)
                channel_count = int(count_match.group(1)) if count_match else 0
                
                # 构建完整URL
                if not href.startswith('http'):
                    href = urljoin(self.base_url, href)
                
                channel_info = {
                    'ip': ip_info['ip'],
                    'category': ip_info['category'],
                    'channel_url': href,
                    'channel_count': channel_count,
                    'title': link_text
                }
                channels.append(channel_info)
                self.logger.info(f"找到频道: {link_text}, 数量: {channel_count}")
        
        return channels
    
    def cleanup(self):
        """清理资源"""
        self.session.close()