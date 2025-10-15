"""代理IP池管理器"""
import json
import time
import requests
import random
import threading
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from config.logger import setup_logger

class ProxyManager:
    """代理IP池管理器"""
    
    def __init__(self, config_file: str = "proxies.json"):
        """初始化代理管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.logger = setup_logger("ProxyManager")
        self.proxies = []
        self.valid_proxies = []
        self.last_update = 0
        self.update_interval = 3600  # 1小时更新一次
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.logger.warning("配置文件不存在或格式错误，使用默认配置")
            self.config = {
                "update_urls": [
                    "https://www.proxy-list.download/api/v1/get?type=http",
                    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http"
                ],
                "config": {
                    "max_proxies": 50,
                    "min_speed": 50,
                    "min_uptime": 80,
                    "test_url": "https://tonkiang.us",
                    "timeout": 10
                }
            }
    
    def fetch_proxies_from_source(self, url: str) -> List[str]:
        """从单个源获取代理列表
        
        Args:
            url: 代理源URL
            
        Returns:
            代理列表
        """
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                proxies = []
                for line in response.text.split('\n'):
                    line = line.strip()
                    if line and ':' in line and not line.startswith('#'):
                        proxies.append(line)
                return proxies
        except Exception as e:
            self.logger.error(f"从 {url} 获取代理失败: {e}")
        return []
    
    def fetch_proxies(self) -> List[str]:
        """从多个源获取代理列表
        
        Returns:
            代理列表
        """
        all_proxies = []
        update_urls = self.config.get("update_urls", [])
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {
                executor.submit(self.fetch_proxies_from_source, url): url 
                for url in update_urls
            }
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    proxies = future.result()
                    all_proxies.extend(proxies)
                    self.logger.info(f"从 {url} 获取到 {len(proxies)} 个代理")
                except Exception as e:
                    self.logger.error(f"处理 {url} 时出错: {e}")
        
        # 去重
        unique_proxies = list(set(all_proxies))
        self.logger.info(f"共获取到 {len(unique_proxies)} 个唯一代理")
        return unique_proxies
    
    def test_proxy(self, proxy: str) -> Optional[Dict[str, any]]:
        """测试单个代理
        
        Args:
            proxy: 代理地址
            
        Returns:
            代理信息或None
        """
        try:
            start_time = time.time()
            response = requests.get(
                self.config["config"]["test_url"],
                proxies={'http': f'http://{proxy}', 'https': f'http://{proxy}'},
                timeout=self.config["config"]["timeout"]
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                speed = int(1000 / response_time) if response_time > 0 else 1000
                return {
                    'ip': proxy.split(':')[0],
                    'port': proxy.split(':')[1],
                    'type': 'http',
                    'speed': speed,
                    'response_time': response_time,
                    'uptime': 100.0
                }
        except Exception:
            pass
        
        return None
    
    def validate_proxies(self, proxies: List[str]) -> List[Dict[str, any]]:
        """验证代理列表
        
        Args:
            proxies: 代理列表
            
        Returns:
            有效代理列表
        """
        valid_proxies = []
        max_proxies = self.config["config"]["max_proxies"]
        min_speed = self.config["config"]["min_speed"]
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_proxy = {
                executor.submit(self.test_proxy, proxy): proxy 
                for proxy in proxies[:100]  # 限制测试数量
            }
            
            for future in as_completed(future_to_proxy):
                proxy = future_to_proxy[future]
                try:
                    proxy_info = future.result()
                    if proxy_info and proxy_info['speed'] >= min_speed:
                        valid_proxies.append(proxy_info)
                        if len(valid_proxies) >= max_proxies:
                            break
                except Exception:
                    pass
        
        # 按速度排序
        valid_proxies.sort(key=lambda x: x['speed'], reverse=True)
        self.logger.info(f"验证通过 {len(valid_proxies)} 个代理")
        return valid_proxies
    
    def update_proxy_pool(self):
        """更新代理池"""
        if time.time() - self.last_update < self.update_interval:
            return
        
        self.logger.info("开始更新代理池...")
        
        # 获取新代理
        raw_proxies = self.fetch_proxies()
        if not raw_proxies:
            self.logger.warning("未能获取到新代理")
            return
        
        # 验证代理
        new_valid_proxies = self.validate_proxies(raw_proxies)
        
        if new_valid_proxies:
            self.valid_proxies = new_valid_proxies
            self.last_update = time.time()
            
            # 保存到配置文件
            self.save_proxies()
            self.logger.info(f"代理池更新完成，当前有效代理: {len(self.valid_proxies)}")
        else:
            self.logger.warning("没有找到有效的代理")
    
    def save_proxies(self):
        """保存代理到配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}
        
        config['proxies'] = self.valid_proxies
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def get_random_proxy(self) -> Optional[Dict[str, any]]:
        """获取随机代理
        
        Returns:
            代理信息或None
        """
        if not self.valid_proxies:
            self.update_proxy_pool()
        
        if self.valid_proxies:
            return random.choice(self.valid_proxies)
        return None
    
    def get_fastest_proxy(self) -> Optional[Dict[str, any]]:
        """获取最快的代理
        
        Returns:
            代理信息或None
        """
        if not self.valid_proxies:
            self.update_proxy_pool()
        
        if self.valid_proxies:
            return self.valid_proxies[0]
        return None
    
    def start_auto_update(self):
        """启动自动更新线程"""
        def update_worker():
            while True:
                self.update_proxy_pool()
                time.sleep(self.update_interval)
        
        thread = threading.Thread(target=update_worker, daemon=True)
        thread.start()
        self.logger.info("代理池自动更新已启动")