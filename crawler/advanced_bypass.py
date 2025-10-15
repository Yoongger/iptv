"""高级Cloudflare绕过爬虫 - 使用代理IP池和高级反检测技术"""
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
from typing import List, Dict, Optional, Tuple
import hashlib
import base64

class AdvancedBypassCrawler:
    """高级Cloudflare绕过爬虫"""
    
    def __init__(self, base_url: str = "https://tonkiang.us"):
        self.base_url = base_url
        self.session = requests.Session()
        self.proxies = self._load_proxies()
        self.request_count = 0
        self._init_session()
        
    def _load_proxies(self) -> List[Dict]:
        """加载代理IP列表"""
        try:
            with open('proxies.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('proxies', [])
        except:
            return []
            
    def _init_session(self):
        """初始化会话设置"""
        # 清除默认头信息
        self.session.headers.clear()
        
        # 设置更真实的浏览器头信息
        self._rotate_user_agent()
        
    def _rotate_user_agent(self):
        """轮换User-Agent"""
        user_agents = [
            # Chrome Windows
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            # Firefox Windows
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
            # Chrome Mac
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # Safari Mac
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        ]
        
        self.session.headers.update({
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        })
        
    def _get_random_proxy(self) -> Optional[Dict]:
        """获取随机代理"""
        if not self.proxies:
            return None
        return random.choice(self.proxies)
        
    def _human_like_delay(self):
        """模拟人类操作延迟"""
        # 根据请求次数调整延迟时间
        base_delay = random.uniform(3.0, 8.0)
        additional_delay = min(self.request_count * 0.5, 10.0)  # 最多额外延迟10秒
        total_delay = base_delay + additional_delay
        time.sleep(total_delay)
        
    def _generate_fingerprint(self) -> Dict:
        """生成浏览器指纹信息"""
        return {
            'screen_resolution': '1920x1080',
            'timezone': 'Asia/Shanghai',
            'language': 'zh-CN',
            'platform': 'Win32',
            'hardware_concurrency': '8',
            'device_memory': '8',
        }
        
    def _check_blocked(self, response: requests.Response) -> bool:
        """检查是否被阻止"""
        if response.status_code in [403, 429, 503]:
            return True
            
        content_lower = response.text.lower()
        blocked_indicators = [
            'cloudflare', 'access denied', 'blocked', 'bot', 'captcha',
            'challenge', 'security check', 'ddos protection'
        ]
        
        for indicator in blocked_indicators:
            if indicator in content_lower:
                return True
                
        return False
        
    def _extract_redirect_url(self, response: requests.Response) -> Optional[str]:
        """提取重定向URL"""
        if response.history:
            return response.url
            
        # 检查meta refresh重定向
        soup = BeautifulSoup(response.text, 'html.parser')
        meta_refresh = soup.find('meta', attrs={'http-equiv': re.compile('refresh', re.I)})
        if meta_refresh and 'content' in meta_refresh.attrs:
            content = meta_refresh['content']
            url_match = re.search(r'url=(.+)', content, re.I)
            if url_match:
                return url_match.group(1)
                
        return None
        
    def _make_request(self, url: str, use_proxy: bool = True) -> Optional[requests.Response]:
        """发送请求"""
        self.request_count += 1
        
        # 准备请求参数
        kwargs = {
            'timeout': 30,
            'allow_redirects': True,
        }
        
        # 使用代理
        if use_proxy and self.proxies:
            proxy = self._get_random_proxy()
            if proxy:
                kwargs['proxies'] = {
                    'http': f"http://{proxy['ip']}:{proxy['port']}",
                    'https': f"http://{proxy['ip']}:{proxy['port']}",
                }
                
        try:
            # 人类化延迟
            self._human_like_delay()
            
            # 发送请求
            response = self.session.get(url, **kwargs)
            
            # 检查是否被阻止
            if self._check_blocked(response):
                print(f"请求被阻止，状态码: {response.status_code}")
                return None
                
            return response
            
        except requests.RequestException as e:
            print(f"请求异常: {e}")
            return None
            
    def bypass_cloudflare(self, url: str) -> Optional[str]:
        """绕过Cloudflare防护"""
        max_attempts = 5
        
        for attempt in range(max_attempts):
            print(f"尝试绕过Cloudflare (第{attempt + 1}次)...")
            
            # 轮换User-Agent
            self._rotate_user_agent()
            
            # 发送请求
            response = self._make_request(url, use_proxy=(attempt > 0))
            
            if response and response.status_code == 200:
                # 检查是否成功绕过
                if not self._check_blocked(response):
                    print("成功绕过Cloudflare防护")
                    return response.text
                else:
                    print("仍然被阻止，尝试其他方法...")
                    
            # 增加延迟
            time.sleep(random.uniform(5.0, 15.0))
            
        print("无法绕过Cloudflare防护")
        return None
        
    def parse_ip_addresses(self, html_content: str) -> List[str]:
        """解析IP地址"""
        ip_addresses = []
        
        if not html_content:
            return ip_addresses
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 方法1: 查找包含IP的链接
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            # 查找hoteliptv链接中的IP
            if 'hoteliptv' in href:
                ip_match = re.search(r'[?&]s=(\d+\.\d+\.\d+\.\d+)', href)
                if ip_match:
                    ip = ip_match.group(1)
                    if ip not in ip_addresses:
                        ip_addresses.append(ip)
                        
        # 方法2: 查找文本中的IP地址
        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::\d+)?\b'
        text_ips = re.findall(ip_pattern, html_content)
        for ip in text_ips:
            # 过滤掉本地IP和无效IP
            if (ip not in ip_addresses and 
                not ip.startswith('0.') and 
                not ip.startswith('127.') and
                not ip.startswith('192.168.') and
                not ip.startswith('10.') and
                not ip.startswith('172.')):
                ip_addresses.append(ip.split(':')[0])  # 去掉端口号
                
        return list(set(ip_addresses))[:50]  # 去重并限制数量
        
    def crawl(self) -> Dict:
        """执行爬取操作"""
        result = {
            'success': False,
            'ip_addresses': [],
            'content_length': 0,
            'attempts': self.request_count,
            'error': None
        }
        
        try:
            print("开始爬取tonkiang.us...")
            
            # 绕过Cloudflare获取内容
            html_content = self.bypass_cloudflare(self.base_url)
            
            if html_content:
                result['content_length'] = len(html_content)
                
                # 解析IP地址
                ip_addresses = self.parse_ip_addresses(html_content)
                
                result['success'] = True
                result['ip_addresses'] = ip_addresses
                result['attempts'] = self.request_count
                
                print(f"爬取成功! 找到 {len(ip_addresses)} 个IP地址")
            else:
                result['error'] = '无法获取页面内容'
                print("爬取失败: 无法获取页面内容")
                
        except Exception as e:
            result['error'] = str(e)
            print(f"爬取异常: {e}")
            
        return result

def main():
    """主函数"""
    print("=== 高级Cloudflare绕过爬虫 ===")
    
    crawler = AdvancedBypassCrawler()
    result = crawler.crawl()
    
    if result['success']:
        print(f"\n爬取统计:")
        print(f"- 请求次数: {result['attempts']}")
        print(f"- 内容长度: {result['content_length']} 字符")
        print(f"- 找到IP地址: {len(result['ip_addresses'])} 个")
        print(f"\nIP地址列表:")
        for i, ip in enumerate(result['ip_addresses'], 1):
            print(f"  {i:2d}. {ip}")
    else:
        print(f"\n爬取失败: {result['error']}")

if __name__ == "__main__":
    main()