"""使用Selenium处理动态加载的频道爬虫模块"""
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from urllib.parse import urljoin
from typing import List, Dict
from models.channel import Channel
from config.logger import setup_logger
from config.constants import BASE_URL
import re

class SeleniumChannelCrawler:
    """使用Selenium的频道爬虫类"""
    
    def __init__(self, headless=True):
        self.base_url = BASE_URL
        self.logger = setup_logger("SeleniumChannelCrawler", level="INFO")
        self.headless = headless
        self.driver = None
        self._init_driver()
    
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
        
        # 禁用SSL错误和网络错误输出
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_argument('--disable-component-extensions-with-background-pages')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
        chrome_options.add_argument('--disable-gpu')
        
        # 禁用GCM和推送服务
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.notifications": 2,
            "gcm.enabled": False
        })
        
        # 禁用SSL错误和网络错误输出
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_argument('--disable-component-extensions-with-background-pages')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
        chrome_options.add_argument('--disable-gpu')
        
        # 禁用GCM和推送服务
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.notifications": 2,
            "gcm.enabled": False
        })
        
        # 禁用SSL错误和网络错误输出
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_argument('--disable-component-extensions-with-background-pages')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
        chrome_options.add_argument('--disable-gpu')
        
        # 禁用GCM和推送服务
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.notifications": 2,
            "gcm.enabled": False
        })
        
        # 禁用SSL错误和网络错误输出
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_argument('--disable-component-extensions-with-background-pages')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
        chrome_options.add_argument('--disable-gpu')
        
        # 禁用GCM和推送服务
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.notifications": 2,
            "gcm.enabled": False
        })
        
        # 禁用图片加载以提高速度
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')
        chrome_options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            # 隐藏自动化特征
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.logger.info("WebDriver初始化成功")
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
    
    def _wait_for_element(self, by, value, timeout=30):
        """等待元素出现"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            self.logger.warning(f"等待元素超时: {value}")
            return None
    
    def smart_request(self, url, max_wait=60):
        """智能请求页面"""
        self.logger.info(f"访问页面: {url}")
        
        try:
            self.driver.get(url)
            
            # 等待页面加载
            self._wait_for_page_load()
            
            # 等待更长时间让JavaScript动态内容加载
            time.sleep(8)  # 增加等待时间
            
            # 检查是否有隐藏的频道数据
            hidden_result = self._wait_for_element(By.ID, 'hiddenresult', 15)
            
            if hidden_result:
                # 等待result divs加载
                time.sleep(3)
                result_divs = hidden_result.find_elements(By.CLASS_NAME, 'result')
                self.logger.info(f"找到 {len(result_divs)} 个result divs")
            
            # 等待分页组件加载
            self._wait_for_element(By.CLASS_NAME, 'pagination', 10)
            
            # 随机延迟，模拟人类行为
            time.sleep(random.uniform(2, 4))
            
            return self.driver.page_source
            
        except Exception as e:
            self.logger.error(f"访问页面失败: {e}")
            return None
    
    def parse_channel_list_page(self, channel_info: Dict) -> List[Channel]:
        """解析频道列表页，获取具体的频道链接
        
        Args:
            channel_info: 频道列表信息字典
            
        Returns:
            频道对象列表
        """
        self.logger.info(f"解析频道列表: {channel_info['channel_url']}")
        
        page_source = self.smart_request(channel_info['channel_url'])
        if not page_source:
            return []
        
        channels = []
        
        try:
            # 等待频道数据加载完成
            time.sleep(3)
            
            # 查找隐藏的频道数据
            hidden_result = self.driver.find_element(By.ID, 'hiddenresult')
            if hidden_result:
                # 从hiddenresult中查找频道结果
                result_divs = hidden_result.find_elements(By.CLASS_NAME, 'result')
                self.logger.info(f"隐藏数据中找到 {len(result_divs)} 个频道结果")
            else:
                # 如果没有hiddenresult，尝试直接查找result divs
                result_divs = self.driver.find_elements(By.CLASS_NAME, 'result')
                self.logger.info(f"直接找到 {len(result_divs)} 个频道结果")
            
            # 分析页面结构
            self.logger.info(f"开始分析 {len(result_divs)} 个result divs")
            
            # 跳过第一个div（通常是IP信息摘要）
            for i, div in enumerate(result_divs):
                # 第一个div通常是IP信息摘要，跳过
                if i == 0:
                    self.logger.info("跳过第一个div（IP信息摘要）")
                    continue
                    
                try:
                    # 获取整个div的HTML内容以便调试
                    div_html = div.get_attribute('innerHTML')
                    self.logger.info(f"=== 分析第{i}个div ===")
                    self.logger.info(f"div文本内容: '{div.text[:200]}...'")
                    
                    # 获取频道名称
                    channel_name = ""
                    
                    # 尝试从tip类的div中获取频道名称
                    try:
                        tip_divs = div.find_elements(By.CLASS_NAME, 'tip')
                        self.logger.info(f"找到 {len(tip_divs)} 个tip divs")
                        for tip_div in tip_divs:
                            tip_text = tip_div.text.strip()
                            if tip_text:
                                self.logger.info(f"tip文本: '{tip_text}'")
                            if tip_text and len(tip_text) > 2:  # 有效的频道名称
                                channel_name = re.sub(r'\s+', ' ', tip_text.strip())
                                self.logger.info(f"使用tip作为频道名称: {channel_name}")
                                break
                    except NoSuchElementException:
                        self.logger.info("没有找到tip divs")
                    
                    # 如果tip中没有找到，尝试从其他元素获取
                    if not channel_name:
                        try:
                            # 查找包含频道名称的文本元素
                            all_text = div.text.strip()
                            if all_text:
                                self.logger.info(f"div完整文本: '{all_text}'")
                            
                            # 如果div文本为空，尝试从HTML中查找频道名称
                            if not all_text:
                                # 查找channel类的div
                                channel_divs = div.find_elements(By.CLASS_NAME, 'channel')
                                self.logger.info(f"找到 {len(channel_divs)} 个channel divs")
                                
                                for channel_div in channel_divs:
                                    channel_text = channel_div.text.strip()
                                    if channel_text:
                                        self.logger.info(f"channel div文本: '{channel_text}'")
                                    if channel_text:
                                        channel_name = re.sub(r'\s+', ' ', channel_text.strip())
                                        self.logger.info(f"使用channel div作为频道名称: {channel_name}")
                                        break
                                
                                # 如果channel div也没有文本，尝试从title属性或其他属性获取
                                if not channel_name:
                                    # 查找所有可能的文本元素
                                    all_elements = div.find_elements(By.XPATH, ".//*")
                                    for element in all_elements:
                                        element_text = element.text.strip()
                                        if element_text and len(element_text) > 2 and len(element_text) < 100:
                                            # 检查是否是有效的频道名称（不包含URL等）
                                            if not element_text.startswith(('http://', 'https://', 'm3u8', 'ts')):
                                                channel_name = re.sub(r'\s+', ' ', element_text.strip())
                                                self.logger.info(f"使用元素文本作为频道名称: {channel_name}")
                                                break
                                    
                                    # 如果还是没有找到，尝试使用JavaScript获取隐藏的文本
                                    if not channel_name:
                                        try:
                                            # 使用JavaScript获取元素的innerText（包括隐藏的文本）
                                            js_script = """
                                            var element = arguments[0];
                                            return element.innerText || element.textContent || '';
                                            """
                                            hidden_text = self.driver.execute_script(js_script, div)
                                            if hidden_text and len(hidden_text.strip()) > 2:
                                                channel_name = hidden_text.strip()
                                                # 清理频道名称中的多余空格
                                                channel_name = re.sub(r'\s+', ' ', channel_name)
                                                self.logger.info(f"使用JavaScript获取频道名称: {channel_name}")
                                        except Exception as js_e:
                                            self.logger.error(f"JavaScript获取文本失败: {js_e}")
                                    
                                    # 如果还是没有找到，尝试从HTML属性中获取
                                    if not channel_name:
                                        try:
                                            # 查找包含频道名称的title属性或其他属性
                                            for element in all_elements:
                                                title = element.get_attribute('title')
                                                if title and len(title.strip()) > 2:
                                                    channel_name = re.sub(r'\s+', ' ', title.strip())
                                                    self.logger.info(f"使用title属性作为频道名称: {channel_name}")
                                                    break
                                        except Exception as attr_e:
                                            self.logger.error(f"获取属性失败: {attr_e}")
                            else:
                                # 提取第一个非空行作为频道名称
                                lines = [line.strip() for line in all_text.split('\
') if line.strip()]
                                if lines:
                                    # 跳过第一行（通常是IP信息），取第二行作为频道名称
                                    if len(lines) > 1:
                                        channel_name = re.sub(r'\s+', ' ', lines[1].strip())
                                        self.logger.info(f"使用第二行作为频道名称: {channel_name}")
                                    else:
                                        channel_name = re.sub(r'\s+', ' ', lines[0].strip())
                                        self.logger.info(f"使用第一行作为频道名称: {channel_name}")
                        except Exception as e:
                            self.logger.error(f"从div文本提取频道名称失败: {e}")
                    
                    # 如果没找到，尝试从其他元素获取
                    if not channel_name:
                        try:
                            # 查找包含频道名称的文本
                            all_text = div.text.strip()
                            if all_text:
                                # 提取第一个非空行作为频道名称
                                lines = [line.strip() for line in all_text.split('\
') if line.strip()]
                                if lines:
                                    channel_name = lines[0]
                        except:
                            pass
                    
                    # 获取频道链接
                    stream_url = ""
                    try:
                        m3u8_div = div.find_element(By.CLASS_NAME, 'm3u8')
                        
                        # 查找包含复制功能的图片
                        img_elements = m3u8_div.find_elements(By.TAG_NAME, 'img')
                        for img in img_elements:
                            onclick = img.get_attribute('onclick')
                            if onclick and 'copyto(' in onclick:
                                match = re.search(r"copyto\('([^']+)'\)", onclick)
                                if match:
                                    stream_url = match.group(1)
                                    self.logger.debug(f"从onclick找到链接: {stream_url}")
                                    break
                        
                        # 如果没找到，尝试查找文本链接
                        if not stream_url:
                            td_elements = m3u8_div.find_elements(By.TAG_NAME, 'td')
                            for td in td_elements:
                                text = td.text.strip()
                                if text.startswith(('http://', 'https://')):
                                    stream_url = text
                                    self.logger.debug(f"从td文本找到链接: {stream_url}")
                                    break
                        
                        # 如果还没找到，查找整个div的文本
                        if not stream_url:
                            m3u8_text = m3u8_div.text
                            url_match = re.search(r'(https?://[^\s]+)', m3u8_text)
                            if url_match:
                                stream_url = url_match.group(1)
                                self.logger.debug(f"从div文本找到链接: {stream_url}")
                                
                    except NoSuchElementException:
                        # 如果没有m3u8 div，尝试其他方式
                        try:
                            # 查找页面中所有可能的链接
                            links = div.find_elements(By.TAG_NAME, 'a')
                            for link in links:
                                href = link.get_attribute('href')
                                if href and ('m3u8' in href or 'ts' in href or 'flv' in href):
                                    stream_url = href
                                    self.logger.debug(f"从a标签找到链接: {stream_url}")
                                    break
                        except:
                            pass
                    
                    # 如果还没找到链接，尝试从div的HTML中提取
                    if not stream_url and div_html:
                        url_match = re.search(r'(https?://[^\s"\']+m3u8[^\s"\']*)', div_html)
                        if url_match:
                            stream_url = url_match.group(1)
                            self.logger.debug(f"从HTML找到链接: {stream_url}")
                    
                    # 清理频道名称
                    if channel_name:
                        # 移除多余的空白字符和特殊空白字符
                        channel_name = re.sub(r'\s+', ' ', channel_name.strip())
                        
                        # 清理频道名称中的URL和其他不需要的内容
                        # 移除包含http://或https://的部分
                        if 'http://' in channel_name or 'https://' in channel_name:
                            # 找到第一个URL出现的位置
                            http_pos = channel_name.find('http://')
                            https_pos = channel_name.find('https://')
                            
                            # 取最小的有效位置
                            url_pos = -1
                            if http_pos != -1 and https_pos != -1:
                                url_pos = min(http_pos, https_pos)
                            elif http_pos != -1:
                                url_pos = http_pos
                            elif https_pos != -1:
                                url_pos = https_pos
                            
                            # 如果找到URL位置，截取URL之前的部分
                            if url_pos != -1:
                                channel_name = channel_name[:url_pos].strip()
                        
                        # 移除常见的文件扩展名
                        for ext in ['.m3u8', '.ts', '.flv', '.mp4']:
                            if ext in channel_name:
                                channel_name = channel_name.replace(ext, '')
                        
                        # 移除IP地址模式
                        # 移除IP地址（如192.168.1.1）
                        channel_name = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '', channel_name)
                        # 移除端口号（如:8080）
                        channel_name = re.sub(r':\d+', '', channel_name)
                        
                        # 再次清理空白字符
                        channel_name = re.sub(r'\s+', ' ', channel_name.strip())
                        
                        # 移除开头和结尾的特殊字符
                        channel_name = re.sub(r'^[\s\W]+|[\s\W]+$', '', channel_name)
                        
                        # 如果名称太长，截断
                        if len(channel_name) > 100:
                            channel_name = channel_name[:100] + "..."
                        
                        # 如果清理后名称为空，使用默认名称
                        if not channel_name.strip():
                            channel_name = f"频道_{i}"
                    
                    if channel_name and stream_url:
                        channel_data = Channel(
                            name=channel_name,
                            url=stream_url,
                            source_ip=channel_info['ip'],
                            category=channel_info['category'],
                            channel_count=channel_info['channel_count'],
                            location=channel_info.get('location', '')  # 添加完整的位置信息
                        )
                        channels.append(channel_data)
                        self.logger.info(f"找到频道: {channel_name}")
                        
                except Exception as e:
                    self.logger.error(f"解析频道时出错: {e}")
                    # 记录div内容以便调试
                    try:
                        div_text = div.text[:200] if div.text else "空内容"
                        self.logger.debug(f"问题div内容: {div_text}")
                    except:
                        pass
                    continue
                    
        except Exception as e:
            self.logger.error(f"解析频道列表页时出错: {e}")
        
        self.logger.info(f"从 {channel_info['ip']} 获取到 {len(channels)} 个频道")
        return channels
    
    def cleanup(self):
        """清理资源"""
        if self.driver:
            self.driver.quit()
            self.logger.info("WebDriver已关闭")

if __name__ == "__main__":
    # 测试代码
    crawler = SeleniumChannelCrawler(headless=False)  # 设置为False以便观察浏览器行为
    
    try:
        # 测试频道列表页
        test_info = {
            'ip': '121.19.134.137',
            'category': '酒店源',
            'channel_url': 'https://tonkiang.us/channellist.html?ip=121.19.134.137&tk=34bc615c&p=1',
            'channel_count': 65
        }
        
        channels = crawler.parse_channel_list_page(test_info)
        print(f"获取到 {len(channels)} 个频道")
        
        if channels:
            for i, channel in enumerate(channels[:5]):  # 显示前5个
                print(f"{i+1}. {channel.name}")
                print(f"   链接: {channel.url}")
        
    except Exception as e:
        print(f"测试出错: {e}")
    finally:
        crawler.cleanup()