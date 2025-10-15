"""增强版反爬虫爬虫模块"""
import time
import random
import json
import requests
from typing import Optional, Dict, List, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from config.logger import setup_logger
from config.constants import BASE_URL

class AntiAntiCrawler:
    """增强版反爬虫爬虫类"""
    
    def __init__(self, use_proxy: bool = False, proxy_file: str = "proxies.json"):
        """初始化爬虫
        
        Args:
            use_proxy: 是否使用代理
            proxy_file: 代理配置文件路径
        """
        self.session = requests.Session()
        self.base_url = BASE_URL
        self.logger = setup_logger("AntiAntiCrawler")
        self.use_proxy = use_proxy
        self.proxy_file = proxy_file
        self.proxies = self._load_proxies() if use_proxy else []
        self.current_proxy_index = 0
        self.last_request_time = 0
        self.request_count = 0
        
        # 更真实的User-Agent列表
        self.user_agents = [
            # Chrome Windows
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
            
            # Firefox Windows
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            
            # Edge Windows
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            
            # Chrome Mac
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            
            # Safari Mac
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            
            # Chrome Linux
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        # 初始化会话头
        self._init_session_headers()
    
    def _load_proxies(self) -> List[Dict[str, str]]:
        """加载代理配置
        
        Returns:
            代理列表
        """
        try:
            with open(self.proxy_file, 'r', encoding='utf-8') as f:
                proxies_data = json.load(f)
                proxies = proxies_data.get('proxies', [])
                # 确保代理格式正确
                valid_proxies = []
                for proxy in proxies:
                    if 'ip' in proxy and 'port' in proxy:
                        valid_proxies.append(proxy)
                return valid_proxies
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self.logger.warning(f"代理配置文件 {self.proxy_file} 不存在或格式错误")
            return []
    
    def _init_session_headers(self):
        """初始化会话头"""
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Sec-GPC': '1'
        })
        
        # 移除可能引起问题的头
        if 'Accept-Encoding' in self.session.headers:
            # 让requests自动处理编码
            del self.session.headers['Accept-Encoding']
    
    def _get_random_delay(self) -> float:
        """获取随机延迟时间
        
        Returns:
            延迟秒数
        """
        # 基础延迟 + 随机延迟
        base_delay = 2.0  # 基础延迟2秒
        random_delay = random.uniform(1.0, 5.0)  # 随机延迟1-5秒
        
        # 根据请求频率调整延迟
        if self.request_count > 10:
            base_delay += 1.0
        if self.request_count > 20:
            base_delay += 2.0
            
        return base_delay + random_delay
    
    def _rotate_proxy(self) -> Optional[Dict[str, str]]:
        """轮换代理
        
        Returns:
            代理配置或None
        """
        if not self.proxies:
            return None
            
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return self.proxies[self.current_proxy_index]
    
    def _detect_captcha(self, response: requests.Response) -> bool:
        """检测验证码
        
        Args:
            response: 响应对象
            
        Returns:
            是否检测到验证码
        """
        if response.status_code == 403:
            return True
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 检测常见的验证码关键词
        captcha_indicators = [
            'captcha', '验证码', 'verification', 'robot check',
            'human verification', 'security check'
        ]
        
        page_text = response.text.lower()
        for indicator in captcha_indicators:
            if indicator in page_text:
                return True
                
        # 检测验证码图片
        captcha_images = soup.find_all('img', src=lambda x: x and any(
            keyword in x.lower() for keyword in ['captcha', 'verify', 'security']
        ))
        if captcha_images:
            return True
            
        return False
    
    def _handle_captcha_challenge(self, response: requests.Response) -> bool:
        """处理验证码挑战
        
        Args:
            response: 响应对象
            
        Returns:
            是否成功处理
        """
        self.logger.warning("检测到验证码挑战，尝试绕过...")
        
        # 策略1: 更换User-Agent
        self.session.headers['User-Agent'] = random.choice(self.user_agents)
        
        # 策略2: 如果使用代理，更换代理
        if self.use_proxy and self.proxies:
            self._rotate_proxy()
            
        # 策略3: 增加延迟
        time.sleep(10)
        
        # 策略4: 添加更多请求头
        self.session.headers.update({
            'DNT': '1',
            'Sec-GPC': '1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        })
        
        return True
    
    def smart_request(self, url: str, method: str = 'GET', 
                     data: Optional[Dict] = None, max_retries: int = 5) -> Optional[requests.Response]:
        """智能请求方法
        
        Args:
            url: 请求URL
            method: 请求方法
            data: POST数据
            max_retries: 最大重试次数
            
        Returns:
            响应对象或None
        """
        for attempt in range(max_retries):
            try:
                # 控制请求频率
                current_time = time.time()
                if self.last_request_time > 0:
                    delay = self._get_random_delay()
                    time_since_last = current_time - self.last_request_time
                    if time_since_last < delay:
                        time.sleep(delay - time_since_last)
                
                # 准备请求参数
                headers = self.session.headers.copy()
                headers['User-Agent'] = random.choice(self.user_agents)
                
                # 设置代理
                proxies = None
                if self.use_proxy and self.proxies:
                    if self.current_proxy_index < len(self.proxies):
                        proxy_config = self.proxies[self.current_proxy_index]
                        proxy_url = f"http://{proxy_config['ip']}:{proxy_config['port']}"
                        
                        # 如果有认证信息
                        if proxy_config.get('username') and proxy_config.get('password'):
                            proxy_url = f"http://{proxy_config['username']}:{proxy_config['password']}@{proxy_config['ip']}:{proxy_config['port']}"
                        
                        proxies = {
                            'http': proxy_url,
                            'https': proxy_url
                        }
                        self.logger.info(f"使用代理: {proxy_config['ip']}:{proxy_config['port']}")
                    else:
                        self.logger.warning("代理索引超出范围，不使用代理")
                
                # 发送请求
                request_kwargs = {
                    'headers': headers,
                    'timeout': 30,
                    'proxies': proxies,
                    'verify': False,  # 忽略SSL证书验证
                    'allow_redirects': True  # 允许重定向
                }
                
                # 处理响应编码
                response = self.session.request(method, url, **request_kwargs)
                
                # 确保响应文本正确解码
                if response.encoding is None or response.encoding.lower() == 'iso-8859-1':
                    response.encoding = 'utf-8'
                
                if method.upper() == 'POST' and data:
                    request_kwargs['data'] = data
                
                response = self.session.request(method, url, **request_kwargs)
                
                # 更新请求统计
                self.last_request_time = time.time()
                self.request_count += 1
                
                # 检查响应状态
                if response.status_code == 200:
                    # 检查是否被重定向到验证码页面
                    if self._detect_captcha(response):
                        self.logger.warning(f"检测到验证码 (尝试 {attempt + 1}/{max_retries})")
                        if not self._handle_captcha_challenge(response):
                            continue
                        # 重试当前请求
                        continue
                    
                    return response
                    
                elif response.status_code == 429:  # 请求过于频繁
                    retry_delay = min(60, 10 * (2 ** attempt))  # 指数退避，最大60秒
                    self.logger.warning(f"请求过于频繁，等待 {retry_delay}秒后重试")
                    time.sleep(retry_delay)
                    
                elif response.status_code in [403, 503]:  # 禁止访问或服务不可用
                    self.logger.warning(f"服务器拒绝访问 ({response.status_code})")
                    if self.use_proxy and self.proxies:
                        self._rotate_proxy()
                        self.logger.info("已更换代理IP")
                    time.sleep(10)
                    
                else:
                    self.logger.error(f"请求失败: {response.status_code}")
                    if attempt == max_retries - 1:
                        return None
                    time.sleep(5)
                    
            except requests.exceptions.RequestException as e:
                self.logger.error(f"请求异常: {e}")
                if attempt == max_retries - 1:
                    return None
                
                # 如果使用代理，更换代理
                if self.use_proxy and self.proxies:
                    self._rotate_proxy()
                    self.logger.info("因网络错误更换代理IP")
                    
                time.sleep(5 * (attempt + 1))
        
        return None
    
    def parse_main_page(self) -> List[Dict[str, Any]]:
        """解析主页面获取IP列表
        
        Returns:
            IP信息列表
        """
        url = f"{self.base_url}/hoteliptv2025.php"
        self.logger.info(f"开始解析主页面: {url}")
        
        response = self.smart_request(url)
        if not response:
            self.logger.error("无法获取主页面")
            return []
        
        # 检查是否被重定向到验证码页面
        if '验证码' in response.text or 'captcha' in response.text.lower():
            self.logger.warning("检测到验证码页面，尝试绕过...")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        ip_list = []
        
        # 方法1: 查找class为'sh'的span标签（根据调试结果）
        ip_spans = soup.find_all('span', class_='sh')
        self.logger.info(f"找到 {len(ip_spans)} 个sh类的span标签")
        
        for span in ip_spans:
            try:
                # 查找span内的链接
                a_tag = span.find('a')
                if a_tag:
                    ip_text = a_tag.get_text(strip=True)
                    href = a_tag.get('href', '')
                    
                    # 验证IP格式
                    import re
                    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
                    if re.match(ip_pattern, ip_text):
                        # 获取分类信息 - 查找父级box div
                        parent_box = span.find_parent('div', class_='box')
                        category = "未知分类"
                        
                        if parent_box:
                            # 查找分类信息（可能在box内的其他元素中）
                            # 根据调试，分类信息可能在文本中
                            box_text = parent_box.get_text()
                            if '酒店' in box_text:
                                category = "酒店"
                            elif '组播' in box_text:
                                category = "组播"
                            elif '代理' in box_text:
                                category = "代理"
                        
                        # 确保链接格式正确
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
                self.logger.error(f"解析span元素时出错: {e}")
                continue
        
        # 方法2: 如果方法1没有找到，使用正则表达式从文本中提取
        if not ip_list:
            self.logger.info("方法1未找到IP，使用方法2: 正则表达式提取")
            import re
            ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
            all_ip_matches = re.findall(ip_pattern, response.text)
            
            # 过滤有效的IP地址
            valid_ips = set()
            for ip in all_ip_matches:
                try:
                    parts = ip.split('.')
                    if len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts):
                        valid_ips.add(ip)
                except ValueError:
                    continue
            
            for ip in valid_ips:
                # 创建默认链接
                href = f"/hotellist.html?s={ip}"
                category = "正则提取"
                
                ip_info = {
                    'ip': ip,
                    'url': urljoin(self.base_url, href),
                    'category': category
                }
                ip_list.append(ip_info)
                self.logger.info(f"正则提取IP: {ip}")
        
        self.logger.info(f"共找到 {len(ip_list)} 个IP地址")
        return ip_list
    
    def parse_ip_channels(self, ip_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析IP详情页获取频道列表
        
        Args:
            ip_info: IP信息
            
        Returns:
            频道列表信息
        """
        self.logger.info(f"解析IP详情页: {ip_info['ip']}")
        
        response = self.smart_request(ip_info['url'])
        if not response:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        channel_links = []
        
        # 根据调试结果，网站结构可能已经变化
        # 尝试多种方式查找频道信息
        
        # 方式1: 查找包含频道信息的特定结构
        result_divs = soup.find_all('div', class_='result')
        self.logger.info(f"找到 {len(result_divs)} 个result div")
        
        if result_divs:
            # 使用原有的解析逻辑
            for div in result_divs:
                channel_div = div.find('div', class_='channel')
                if channel_div:
                    a_tag = channel_div.find('a', href=True)
                    # 更新链接匹配逻辑，支持hoteliptv2025.php和hotellist.html
                    if a_tag and ('hotellist.html' in a_tag['href'] or 'hoteliptv2025.php' in a_tag['href']):
                        # 提取频道数量
                        channel_count = 0
                        count_span = div.find('span', style='font-size: 18px;')
                        if count_span:
                            try:
                                channel_count = int(count_span.get_text(strip=True))
                            except ValueError:
                                pass
                        
                        channel_info = {
                            'ip': ip_info['ip'],
                            'category': ip_info['category'],
                            'channel_url': urljoin(self.base_url, a_tag['href']),
                            'channel_count': channel_count,
                            'title': a_tag.get_text(strip=True)
                        }
                        channel_links.append(channel_info)
                        self.logger.info(f"找到频道列表: {a_tag['href']}, 频道数: {channel_count}")
        else:
            # 方式2: 如果没有result div，尝试其他方式
            self.logger.info("未找到result div，尝试其他解析方式")
            
            # 查找所有包含IP的链接
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                # 更新链接匹配逻辑
                if ('hotellist.html' in href or 'hoteliptv2025.php' in href) and ip_info['ip'] in href:
                    # 从链接文本中提取信息
                    link_text = link.get_text(strip=True)
                    channel_count = 0
                    
                    # 尝试从文本中提取频道数量
                    import re
                    count_match = re.search(r'(\d+)\s*频道', link_text)
                    if count_match:
                        channel_count = int(count_match.group(1))
                    
                    channel_info = {
                        'ip': ip_info['ip'],
                        'category': ip_info['category'],
                        'channel_url': urljoin(self.base_url, href),
                        'channel_count': channel_count,
                        'title': link_text
                    }
                    channel_links.append(channel_info)
                    self.logger.info(f"从链接找到频道: {link_text}")
        
        return channel_links

    def cleanup(self):
        """清理资源"""
        self.session.close()