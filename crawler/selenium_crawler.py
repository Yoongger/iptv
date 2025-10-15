"""使用Selenium绕过Cloudflare反爬虫的爬虫模块"""
import time
import random
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from urllib.parse import urljoin
from config.logger import setup_logger
from config.constants import BASE_URL
import re

class SeleniumCrawler:
    """使用Selenium的爬虫类"""
    
    def __init__(self, use_proxy=False, proxy_file="proxies.json", headless=True):
        self.base_url = BASE_URL
        self.logger = setup_logger("SeleniumCrawler")
        self.use_proxy = use_proxy
        self.proxy_file = proxy_file
        self.proxies = self._load_proxies() if use_proxy else []
        self.headless = headless
        self.driver = None
        self._init_driver()
    
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
    
    def _init_driver(self):
        """初始化WebDriver"""
        chrome_options = Options()
        
        # 设置User-Agent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')
        
        # 无头模式
        if self.headless:
            chrome_options.add_argument('--headless')
        
        # 其他配置
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # 设置代理
        if self.use_proxy and self.proxies:
            proxy = random.choice(self.proxies)
            proxy_url = f"{proxy['ip']}:{proxy['port']}"
            if proxy.get('username') and proxy.get('password'):
                proxy_url = f"{proxy['username']}:{proxy['password']}@{proxy_url}"
            chrome_options.add_argument(f'--proxy-server=http://{proxy_url}')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            # 隐藏自动化特征
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception as e:
            self.logger.error(f"初始化WebDriver失败: {e}")
            raise
    
    def _wait_for_page_load(self, timeout=30):
        """等待页面加载完成"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script('return document.readyState') == 'complete'
            )
        except TimeoutException:
            self.logger.warning("页面加载超时")
    
    def _handle_cloudflare(self, timeout=60):
        """处理Cloudflare挑战"""
        try:
            # 等待可能的Cloudflare挑战
            WebDriverWait(self.driver, timeout).until(
                lambda driver: 'cf-browser-verification' not in driver.page_source.lower()
            )
            self.logger.info("Cloudflare挑战处理完成")
            return True
        except TimeoutException:
            self.logger.warning("Cloudflare挑战处理超时")
            return False
    
    def smart_request(self, url, max_wait=60):
        """智能请求页面"""
        self.logger.info(f"访问页面: {url}")
        
        try:
            self.driver.get(url)
            
            # 等待页面加载
            self._wait_for_page_load()
            
            # 处理Cloudflare挑战
            if not self._handle_cloudflare(max_wait):
                return None
            
            # 随机延迟，模拟人类行为
            time.sleep(random.uniform(2, 5))
            
            return self.driver.page_source
            
        except Exception as e:
            self.logger.error(f"访问页面失败: {e}")
            return None
    
    def parse_main_page(self):
        """解析主页面获取IP列表"""
        url = f"{self.base_url}/hoteliptv2025.php"
        
        page_source = self.smart_request(url)
        if not page_source:
            self.logger.error("无法获取主页面")
            return []
        
        ip_list = []
        
        # 使用Selenium查找元素
        try:
            # 查找sh类的span标签
            sh_spans = self.driver.find_elements(By.CSS_SELECTOR, 'span.sh')
            self.logger.info(f"找到 {len(sh_spans)} 个sh类的span标签")
            
            for span in sh_spans:
                try:
                    # 查找span内的链接
                    a_tag = span.find_element(By.TAG_NAME, 'a')
                    ip_text = a_tag.text.strip()
                    href = a_tag.get_attribute('href')
                    
                    # 验证IP格式
                    if re.match(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', ip_text):
                        # 获取分类
                        category = "未知分类"
                        try:
                            parent_box = span.find_element(By.XPATH, './ancestor::div[contains(@class, "box")]')
                            box_text = parent_box.text
                            if '酒店' in box_text:
                                category = "酒店"
                            elif '组播' in box_text:
                                category = "组播"
                        except NoSuchElementException:
                            pass
                        
                        ip_info = {
                            'ip': ip_text,
                            'url': href if href else f"{self.base_url}/hoteliptv2025.php?s={ip_text}",
                            'category': category
                        }
                        ip_list.append(ip_info)
                        self.logger.info(f"找到IP: {ip_text}, 分类: {category}")
                        
                except Exception as e:
                    self.logger.error(f"解析span元素出错: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"查找元素出错: {e}")
        
        # 如果Selenium方法失败，使用正则表达式
        if not ip_list:
            self.logger.info("使用正则表达式提取IP")
            ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
            ips = set(re.findall(ip_pattern, page_source))
            
            for ip in ips:
                try:
                    parts = ip.split('.')
                    if len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts):
                        ip_info = {
                            'ip': ip,
                            'url': f"{self.base_url}/hoteliptv2025.php?s={ip}",
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
        
        page_source = self.smart_request(ip_info['url'])
        if not page_source:
            return []
        
        channels = []
        
        try:
            # 查找频道链接
            all_links = self.driver.find_elements(By.TAG_NAME, 'a')
            
            for link in all_links:
                try:
                    href = link.get_attribute('href')
                    if href and ('hotellist.html' in href or 'hoteliptv2025.php' in href) and ip_info['ip'] in href:
                        link_text = link.text.strip()
                        
                        # 提取频道数量
                        count_match = re.search(r'(\d+)\s*频道', link_text)
                        channel_count = int(count_match.group(1)) if count_match else 0
                        
                        channel_info = {
                            'ip': ip_info['ip'],
                            'category': ip_info['category'],
                            'channel_url': href,
                            'channel_count': channel_count,
                            'title': link_text
                        }
                        channels.append(channel_info)
                        self.logger.info(f"找到频道: {link_text}, 数量: {channel_count}")
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            self.logger.error(f"查找频道链接出错: {e}")
        
        return channels
    
    def cleanup(self):
        """清理资源"""
        if self.driver:
            self.driver.quit()