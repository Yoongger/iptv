"""爬虫基类"""
import time
import random
from typing import Optional
import requests
from config.logger import setup_logger
from config.constants import BASE_URL, REQUEST_HEADERS, API_HEADERS

class BaseCrawler:
    """爬虫基类，提供通用功能"""
    
    def __init__(self):
        """初始化爬虫"""
        self.session = requests.Session()
        self.session.headers = REQUEST_HEADERS
        self.base_url = BASE_URL
        self.logger = setup_logger(self.__class__.__name__)
    
    def request_with_retry(self, url: str, max_retries: int = 3) -> Optional[requests.Response]:
        """带重试机制的请求(增强版)
        
        Args:
            url: 请求URL
            max_retries: 最大重试次数
            
        Returns:
            响应对象或None
        """
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Mozilla/5.0 (X11; Linux x86_64)'
        ]
        
        for attempt in range(max_retries):
            try:
                # 随机延迟1-3秒
                time.sleep(random.uniform(1, 3))
                
                # 更新请求头
                headers = {
                    **self.session.headers,
                    'User-Agent': random.choice(user_agents),
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://www.google.com/'
                }
                
                response = self.session.get(
                    url, 
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    return response
                elif response.status_code in [429, 503]:
                    retry_delay = min(30, 5 * (2 ** attempt))  # 指数退避，最大30秒
                    self.logger.warning(
                        f"服务器繁忙 ({response.status_code}), 尝试 {attempt + 1}/{max_retries}, "
                        f"等待 {retry_delay}秒后重试"
                    )
                    time.sleep(retry_delay)
                else:
                    self.logger.error(f"请求失败: {response.status_code}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"请求异常: {e}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(5 * (attempt + 1))
        
        return None