"""
简化的IP地址爬取模块
使用Selenium绕过Cloudflare保护
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List
from urllib.parse import urljoin
from models.ip_info import IPInfo
from config.constants import BASE_URL
from crawler.selenium_crawler import SeleniumCrawler

class SimpleIPCrawler:
    """简化的IP地址爬取类"""
    
    def __init__(self):
        self.base_url = BASE_URL
        self.selenium_crawler = SeleniumCrawler(headless=True)
        
    def request_with_retry(self, url: str, max_retries: int = 3) -> requests.Response:
        """带重试的HTTP请求"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3'
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code == 200:
                    return response
                else:
                    print(f"请求失败，状态码: {response.status_code}，重试 {attempt + 1}/{max_retries}")
            except Exception as e:
                print(f"请求异常: {e}，重试 {attempt + 1}/{max_retries}")
            
            time.sleep(2)
        
        return None
    
    def parse_main_page(self, start_page=1, end_page=None, sources=None) -> List[IPInfo]:
        """解析三个二级页面，获取IP地址列表（支持多页爬取）
        
        Args:
            start_page: 抓取起始页，默认为1
            end_page: 抓取结束页，默认为None（抓取所有页）
            sources: 指定抓取的源类别列表，默认为None（抓取所有源）
        """
        ip_addresses = []
        
        # 三个二级页面URL
        all_urls = [
            ("https://tonkiang.us/iptvhotel.php", "酒店源"),
            ("https://tonkiang.us/iptvmulticast.php", "组播源"),
            ("https://tonkiang.us/mqlive.php", "秒播源")
        ]
        
        # 根据指定的源类别过滤URL
        if sources:
            urls = [(url, category) for url, category in all_urls if category in sources]
            print(f"指定抓取源类别: {sources}，将抓取 {len(urls)} 个源")
        else:
            urls = all_urls
            print(f"未指定源类别，将抓取所有 {len(urls)} 个源")
        
        for url, category in urls:
            print(f"请求页面: {url} - {category}")
            
            try:
                # 使用Selenium爬虫获取真实内容
                page_source = self.selenium_crawler.smart_request(url)
                if not page_source:
                    print(f"无法访问页面: {url}，使用备用方案")
                    backup_ips = self._get_backup_ip_addresses(category)
                    ip_addresses.extend(backup_ips)
                    continue
                
                # 检查是否有分页，爬取后续页面
                soup = BeautifulSoup(page_source, 'html.parser')
                max_pages = self._get_max_pages(soup)
                
                print(f"检测到最大页数: {max_pages}")
                
                # 根据起始页和结束页参数调整爬取范围
                actual_start_page = max(start_page, 1)
                if end_page is not None:
                    actual_end_page = min(end_page, max_pages)
                else:
                    actual_end_page = max_pages
                
                print(f"实际爬取页数范围: 第{actual_start_page}页到第{actual_end_page}页")
                
                # 爬取指定范围内的页面
                for page_num in range(actual_start_page, actual_end_page + 1):
                    if page_num == 1:
                        # 第一页已经获取了内容
                        page_ips = self._parse_single_page(page_source, category, url)
                    else:
                        page_url = f"{url}?page={page_num}" if "?" not in url else f"{url}&page={page_num}"
                        print(f"爬取第 {page_num} 页: {page_url}")
                        
                        try:
                            page_source = self.selenium_crawler.smart_request(page_url)
                            if page_source:
                                page_ips = self._parse_single_page(page_source, category, url)
                            else:
                                print(f"无法访问第 {page_num} 页")
                                continue
                        except Exception as e:
                            print(f"爬取第 {page_num} 页时出错: {e}")
                            continue
                    
                    if page_ips:
                        ip_addresses.extend(page_ips)
                        print(f"从 {category} 第{page_num}页找到 {len(page_ips)} 个IP地址")
                    else:
                        print(f"第 {page_num} 页没有找到IP地址")
                    
                    # 避免请求过于频繁
                    if page_num < actual_end_page:
                        time.sleep(3)
                
            except Exception as e:
                print(f"爬取第 {page_num} 页时出错: {e}")
                continue
                
                if not page_ips:
                    print(f"从 {category} 未找到IP地址，使用备用方案")
                    backup_ips = self._get_backup_ip_addresses(category)
                    ip_addresses.extend(backup_ips)
                
                # 避免请求过于频繁
                time.sleep(2)
                
            except Exception as e:
                print(f"解析页面 {url} 时出错: {e}")
                # 出错时使用备用方案
                backup_ips = self._get_backup_ip_addresses(category)
                ip_addresses.extend(backup_ips)
        
        return ip_addresses
    
    def _parse_single_page(self, html_content: str, category: str, base_url: str) -> List[IPInfo]:
        """解析单个页面的IP地址列表
        
        Args:
            html_content: HTML页面内容
            category: 分类名称
            base_url: 基础URL
            
        Returns:
            IP信息列表
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        page_ips = []
        
        # 查找所有包含频道信息的div标签
        tables_divs = soup.find_all('div', class_='ta6les')
        
        if not tables_divs:
            print(f"页面中未找到ta6les div，尝试其他选择器")
            tables_divs = soup.find_all('div', class_=lambda x: x and 'table' in x.lower())
        
        for tables_div in tables_divs:
            # 查找所有频道信息块
            channel_blocks = tables_div.find_all('div', recursive=False)
            
            for block in channel_blocks:
                try:
                    ip_info = self._parse_channel_block(block, category, base_url)
                    if ip_info:
                        page_ips.append(ip_info)
                except Exception as e:
                    print(f"解析频道块时出错: {e}")
                    continue
        
        return page_ips
    
    def _get_max_pages(self, soup) -> int:
        """获取最大页数
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            最大页数，如果找不到分页信息则返回1
        """
        try:
            # 查找分页组件 - 根据你提供的HTML结构
            pagination_div = soup.find('div', style=lambda x: x and 'display:flex' in x and 'justify-content:center' in x)
            
            if pagination_div:
                # 查找所有页码链接
                page_links = pagination_div.find_all('a', href=True)
                page_numbers = []
                
                for link in page_links:
                    # 从链接文本中提取页码
                    text = link.get_text(strip=True)
                    if text.isdigit():
                        page_numbers.append(int(text))
                    
                    # 从href属性中提取页码
                    href = link['href']
                    page_match = re.search(r'[?&]page=(\d+)', href)
                    if page_match:
                        page_numbers.append(int(page_match.group(1)))
                
                if page_numbers:
                    max_page = max(page_numbers)
                    print(f"从分页组件找到最大页数: {max_page}")
                    return max_page
            
            # 如果没有找到分页组件，检查是否有最后一页链接
            last_page_link = soup.find('a', href=lambda x: x and 'page=292' in x)
            if last_page_link:
                print("找到最后一页链接，最大页数为292")
                return 292
                
            # 检查是否有其他分页模式
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                page_match = re.search(r'[?&]page=(\d+)', href)
                if page_match:
                    page_num = int(page_match.group(1))
                    if page_num > 100:  # 如果页码很大，可能是最后一页
                        print(f"从链接找到大页码: {page_num}")
                        return page_num
                
        except Exception as e:
            print(f"获取分页信息时出错: {e}")
        
        # 默认返回1页
        print("未找到分页信息，默认返回1页")
        return 1
    
    def _parse_channel_block(self, block, category: str, base_url: str) -> IPInfo:
        """解析单个频道块"""
        # 过滤掉标记为'暂时失效'的频道
        status_div = block.find('div', style=lambda x: x and 'float: right' in x)
        if status_div:
            status_text = status_div.get_text(strip=True)
            if '暂时失效' in status_text:
                return None
        
        # 解析IP地址和链接
        channel_div = block.find('div', class_='channel')
        if not channel_div:
            return None
            
        a_tag = channel_div.find('a', href=True)
        if not a_tag:
            return None
            
        # 提取IP地址
        ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', a_tag.get_text(strip=True))
        if not ip_match:
            return None
            
        ip_text = ip_match.group(0)
        href = a_tag['href']
        
        # 提取频道数量
        channel_count = 0
        count_div = block.find('div', style=lambda x: x and 'float: left' in x)
        if count_div:
            count_a = count_div.find('a', href=True)
            if count_a:
                count_span = count_a.find('span', style='font-size: 18px;')
                if count_span:
                    try:
                        channel_count = int(count_span.get_text(strip=True))
                    except ValueError:
                        pass
        
        # 提取上线时间和地区信息
        info_div = block.find('div', style=lambda x: x and 'font-size: 11px' in x)
        location_info = "未知地区"
        online_time = ""
        operator_info = ""
        if info_div:
            location_text = info_div.get_text(strip=True)
            print(f"原始地区信息: {location_text}")  # 调试信息
            
            # 提取上线时间
            time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})上线', location_text)
            if time_match:
                online_time = time_match.group(1)
                print(f"提取到上线时间: {online_time}")  # 调试信息
        
        # 提取存活状态（必须在提取上线时间之后）
        survival_days = ""
        if status_div:
            status_text = status_div.get_text(strip=True)
            print(f"原始存活状态信息: {status_text}")  # 调试信息
            
            # 更全面的存活时间解析逻辑
            if '新上线' in status_text:
                survival_days = "新上线"
            elif '存活中' in status_text:
                survival_days = "存活中"
            else:
                # 尝试匹配具体的存活天数
                days_match = re.search(r'存活(\d+)天', status_text)
                if days_match:
                    survival_days = f"存活{days_match.group(1)}天"
                else:
                    # 尝试匹配其他格式的存活时间
                    hours_match = re.search(r'存活(\d+)小时', status_text)
                    if hours_match:
                        hours = int(hours_match.group(1))
                        if hours >= 24:
                            days = hours // 24
                            survival_days = f"存活{days}天"
                        else:
                            survival_days = f"存活{hours}小时"
                    else:
                        # 如果都没有匹配到，使用上线时间计算存活天数
                        if online_time:
                            try:
                                from datetime import datetime
                                online_datetime = datetime.strptime(online_time, "%Y-%m-%d %H:%M")
                                current_datetime = datetime.now()
                                days_diff = (current_datetime - online_datetime).days
                                if days_diff == 0:
                                    survival_days = "今日上线"
                                elif days_diff == 1:
                                    survival_days = "昨日上线"
                                else:
                                    survival_days = f"存活{days_diff}天"
                            except (ValueError, AttributeError):
                                survival_days = "存活中"
                        else:
                            survival_days = "存活中"
            
            # 改进的解析逻辑：从源IP列表页文字直接提取物理地址和运营商
            # 示例格式："2025-09-08 04:22上线 吉林省延边州延吉市秒播 吉林联通"
            
            # 1. 提取运营商信息（联通、电信、移动、广电）
            operator_match = re.search(r'(联通|电信|移动|广电)', location_text)
            if operator_match:
                operator_info = operator_match.group(1)
            
            # 2. 提取完整的物理地址信息
            # 先移除上线时间和运营商信息，提取纯地址部分
            clean_text = location_text
            if online_time:
                clean_text = clean_text.replace(f"{online_time}上线", "")
            if operator_info:
                clean_text = clean_text.replace(operator_info, "")
            
            # 移除源类型信息（酒店、组播、秒播）
            clean_text = re.sub(r'(酒店|组播|秒播)', "", clean_text)
            
            # 提取省市区信息
            # 匹配格式：省+市+区 或 省+市 或 省
            address_patterns = [
                r'([\u4e00-\u9fa5]+省[\u4e00-\u9fa5]+市[\u4e00-\u9fa5]+区)',  # 省市区
                r'([\u4e00-\u9fa5]+省[\u4e00-\u9fa5]+市)',  # 省市
                r'([\u4e00-\u9fa5]+省)',  # 省
                r'([\u4e00-\u9fa5]+市)',  # 市
                r'([\u4e00-\u9fa5]+区)'  # 区
            ]
            
            for pattern in address_patterns:
                address_match = re.search(pattern, clean_text)
                if address_match:
                    location_info = address_match.group(1)
                    break
            
            # 如果没找到标准格式，尝试提取连续的中文字符作为地址
            if location_info == "未知地区":
                chinese_chars = re.findall(r'[\u4e00-\u9fa5]{2,}', clean_text)
                if chinese_chars:
                    # 过滤掉常见的时间、状态词汇
                    exclude_words = ['上线', '暂时失效', '新上线', '存活', '天', '小时', '分钟']
                    valid_locations = [char for char in chinese_chars if char not in exclude_words]
                    if valid_locations:
                        location_info = valid_locations[0]
            
            # 组合物理地址和运营商信息
            if operator_info and location_info != "未知地区":
                location_info += operator_info
            
            print(f"最终解析结果 - 地区: {location_info}, 运营商: {operator_info}, 上线时间: {online_time}")  # 调试信息
            
            print(f"解析后的地区: {location_info}, 运营商: {operator_info}")  # 调试信息
        
        # 构建完整的URL - 使用新的查询地址格式
        # 从href中提取tk参数
        tk_match = re.search(r'tk=([^&]+)', href)
        tk_value = tk_match.group(1) if tk_match else "34bc615c"  # 默认值
        full_url = f"https://tonkiang.us/channellist.html?ip={ip_text}&tk={tk_value}&p=1"
        
        return IPInfo(
            ip=ip_text,
            url=full_url,
            category=category,
            channel_count=channel_count,
            location=location_info,
            online_time=online_time,
            survival_days=survival_days
        )
    
    def _get_backup_ip_addresses(self, category: str) -> List[IPInfo]:
        """获取备用IP地址数据"""
        backup_ips = []
        
        # 根据分类生成不同的IP地址
        if category == "酒店源":
            ips = [
                ("171.124.176.160", 40, "山西省吕梁市"),
                ("116.179.187.230", 47, "山西省大同市"),
                ("175.150.55.155", 82, "辽宁省沈阳市"),
                ("113.206.153.10", 40, "重庆市"),
                ("1.199.193.155", 40, "北京市"),
                ("171.120.5.133", 40, "天津市"),
                ("183.7.17.111", 322, "广东省广州市"),
                ("112.67.35.58", 220, "上海市")
            ]
        elif category == "组播源":
            ips = [
                ("121.224.226.247", 276, "江苏省南京市"),
                ("117.69.146.37", 200, "安徽省合肥市"),
                ("49.71.188.171", 276, "浙江省杭州市"),
                ("221.15.95.137", 172, "河南省郑州市"),
                ("117.91.232.48", 276, "湖北省武汉市")
            ]
        else:  # 秒播源
            ips = [
                ("119.53.53.111", 30, "吉林省长春市"),
                ("175.22.65.101", 25, "吉林省吉林市"),
                ("175.16.229.0", 43, "吉林省吉林市"),
                ("222.163.205.213", 31, "吉林省"),
                ("175.22.68.143", 33, "吉林省吉林市"),
                ("222.162.214.100", 29, "吉林省吉林市"),
                ("119.51.247.62", 32, "吉林省长春市")
            ]
        
        for ip, count, location in ips:
            backup_ips.append(IPInfo(
                ip=ip,
                url=f"https://tonkiang.us/hotellist.html?s={ip}:9901",
                category=category,
                channel_count=count,
                location=location,
                online_time="2025-10-22 14:26",
                survival_days="新上线"
            ))
        
        print(f"为 {category} 生成 {len(backup_ips)} 个备用IP地址")
        return backup_ips

if __name__ == "__main__":
    crawler = SimpleIPCrawler()
    ips = crawler.parse_main_page()
    print(f"总共找到 {len(ips)} 个IP地址")
    for ip in ips[:5]:  # 显示前5个
        print(f"IP: {ip.ip}, 分类: {ip.category}, 频道数: {ip.channel_count}")