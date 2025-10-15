"""绕过Cloudflare防护的爬虫模块"""
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
from typing import List, Dict, Optional

class CloudflareBypassCrawler:
    """绕过Cloudflare防护的爬虫类"""
    
    def __init__(self, base_url: str = "https://tonkiang.us"):
        self.base_url = base_url
        self.session = requests.Session()
        self._init_session_headers()
        
    def _init_session_headers(self):
        """初始化会话头信息"""
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
        })
        
    def _get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        ]
        return random.choice(user_agents)
    
    def _random_delay(self, min_delay: float = 2.0, max_delay: float = 5.0):
        """随机延迟"""
        time.sleep(random.uniform(min_delay, max_delay))
        
    def _check_cloudflare_challenge(self, response: requests.Response) -> bool:
        """检查是否遇到Cloudflare挑战"""
        if response.status_code == 403:
            return True
        if 'cloudflare' in response.headers.get('server', '').lower():
            return True
        if 'cf-ray' in response.headers:
            return True
        if 'challenge' in response.text.lower():
            return True
        return False
        
    def _extract_cloudflare_info(self, response: requests.Response) -> Dict:
        """提取Cloudflare挑战信息"""
        soup = BeautifulSoup(response.text, 'html.parser')
        info = {}
        
        # 查找可能的挑战表单
        challenge_form = soup.find('form', {'id': 'challenge-form'})
        if challenge_form:
            info['challenge_form'] = True
            
        # 查找JavaScript挑战
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.get_text()
            if 'cf.chl' in script_text or 'jschl' in script_text:
                info['javascript_challenge'] = True
                break
                
        return info
        
    def _solve_simple_challenge(self, response: requests.Response) -> Optional[requests.Response]:
        """尝试解决简单的Cloudflare挑战"""
        try:
            # 更新User-Agent
            self.session.headers['User-Agent'] = self._get_random_user_agent()
            
            # 添加Referer头
            self.session.headers['Referer'] = self.base_url
            
            # 等待一段时间后重试
            self._random_delay(3.0, 8.0)
            
            # 重新发送请求
            response = self.session.get(self.base_url)
            
            if not self._check_cloudflare_challenge(response):
                return response
                
        except Exception as e:
            print(f"解决挑战时出错: {e}")
            
        return None
        
    def get_page_content(self, url: str = None) -> Optional[str]:
        """获取页面内容，处理Cloudflare挑战"""
        if url is None:
            url = self.base_url
            
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 设置随机User-Agent
                self.session.headers['User-Agent'] = self._get_random_user_agent()
                
                # 发送请求
                response = self.session.get(url, timeout=30)
                
                # 检查是否遇到Cloudflare挑战
                if self._check_cloudflare_challenge(response):
                    print(f"第{attempt + 1}次尝试遇到Cloudflare挑战")
                    
                    # 尝试解决挑战
                    solved_response = self._solve_simple_challenge(response)
                    if solved_response:
                        return solved_response.text
                    else:
                        # 增加延迟后重试
                        self._random_delay(5.0, 10.0)
                        continue
                        
                # 检查响应状态
                if response.status_code == 200:
                    return response.text
                else:
                    print(f"请求失败，状态码: {response.status_code}")
                    
            except requests.RequestException as e:
                print(f"请求异常: {e}")
                
            # 重试前延迟
            if attempt < max_retries - 1:
                self._random_delay(3.0, 7.0)
                
        return None
        
    def parse_ip_addresses(self, html_content: str) -> List[str]:
        """解析IP地址列表"""
        ip_addresses = []
        
        if not html_content:
            return ip_addresses
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 方法1: 查找包含IP地址的链接
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            # 查找包含IP地址的链接
            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', href)
            if ip_match:
                ip = ip_match.group(1)
                if ip not in ip_addresses:
                    ip_addresses.append(ip)
                    
        # 方法2: 查找文本中的IP地址
        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
        text_ips = re.findall(ip_pattern, html_content)
        for ip in text_ips:
            if ip not in ip_addresses and not ip.startswith('0.'):
                ip_addresses.append(ip)
                
        return ip_addresses[:20]  # 限制返回数量
        
    def crawl(self) -> Dict:
        """执行爬取操作"""
        result = {
            'success': False,
            'ip_addresses': [],
            'error': None
        }
        
        try:
            # 获取主页内容
            html_content = self.get_page_content()
            
            if html_content:
                # 解析IP地址
                ip_addresses = self.parse_ip_addresses(html_content)
                
                result['success'] = True
                result['ip_addresses'] = ip_addresses
                result['content_length'] = len(html_content)
            else:
                result['error'] = '无法获取页面内容'
                
        except Exception as e:
            result['error'] = str(e)
            
        return result

def main():
    """主函数"""
    print("=== Cloudflare绕过爬虫测试 ===")
    
    crawler = CloudflareBypassCrawler()
    result = crawler.crawl()
    
    if result['success']:
        print(f"爬取成功! 找到 {len(result['ip_addresses'])} 个IP地址")
        print("IP地址列表:")
        for ip in result['ip_addresses']:
            print(f"  - {ip}")
    else:
        print(f"爬取失败: {result['error']}")

if __name__ == "__main__":
    main()