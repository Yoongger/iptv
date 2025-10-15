"""终极Cloudflare绕过方案 - 处理加密内容和高级防护"""
import time
import random
import requests
from bs4 import BeautifulSoup
import re
import json
import zlib
import gzip
from io import BytesIO
from typing import List, Dict, Optional
import base64

class UltimateBypassCrawler:
    """终极Cloudflare绕过爬虫"""
    
    def __init__(self, base_url: str = "https://tonkiang.us"):
        self.base_url = base_url
        self.session = requests.Session()
        self._setup_session()
        
    def _setup_session(self):
        """设置会话参数"""
        # 清除默认头信息
        self.session.headers.clear()
        
        # 设置更真实的头信息
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        })
        
    def _decode_content(self, response: requests.Response) -> Optional[str]:
        """解码响应内容"""
        try:
            # 检查内容编码
            content_encoding = response.headers.get('content-encoding', '').lower()
            
            if content_encoding == 'gzip':
                return gzip.decompress(response.content).decode('utf-8', errors='ignore')
            elif content_encoding == 'deflate':
                return zlib.decompress(response.content).decode('utf-8', errors='ignore')
            elif content_encoding == 'br':
                # 需要brotli库，这里简单处理
                return response.content.decode('utf-8', errors='ignore')
            else:
                # 尝试自动检测编码
                return response.content.decode('utf-8', errors='ignore')
                
        except Exception as e:
            print(f"解码内容时出错: {e}")
            # 尝试其他编码
            try:
                return response.content.decode('latin-1', errors='ignore')
            except:
                return None
                
    def _is_encrypted_content(self, content: str) -> bool:
        """检查内容是否被加密"""
        if not content:
            return True
            
        # 检查是否是有效的HTML
        if '<html' in content.lower() or '<!doctype' in content.lower():
            return False
            
        # 检查是否包含大量非打印字符
        printable_ratio = sum(1 for c in content[:1000] if c.isprintable()) / min(1000, len(content))
        if printable_ratio < 0.7:
            return True
            
        return False
        
    def _try_different_encodings(self, content_bytes: bytes) -> Optional[str]:
        """尝试不同的编码方式"""
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'gbk', 'gb2312', 'big5']
        
        for encoding in encodings:
            try:
                decoded = content_bytes.decode(encoding, errors='ignore')
                if not self._is_encrypted_content(decoded):
                    return decoded
            except:
                continue
                
        return None
        
    def _make_smart_request(self, url: str) -> Optional[requests.Response]:
        """发送智能请求"""
        try:
            # 禁用自动重定向
            response = self.session.get(url, allow_redirects=False, timeout=30)
            
            # 检查重定向
            if response.status_code in [301, 302, 303, 307, 308]:
                redirect_url = response.headers.get('Location')
                if redirect_url:
                    if not redirect_url.startswith('http'):
                        redirect_url = requests.compat.urljoin(url, redirect_url)
                    print(f"重定向到: {redirect_url}")
                    return self.session.get(redirect_url, timeout=30)
                    
            return response
            
        except requests.RequestException as e:
            print(f"请求异常: {e}")
            return None
            
    def get_page_content(self) -> Optional[str]:
        """获取页面内容"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            print(f"尝试获取页面内容 (第{attempt + 1}次)...")
            
            try:
                # 发送请求
                response = self._make_smart_request(self.base_url)
                
                if response and response.status_code == 200:
                    # 解码内容
                    content = self._decode_content(response)
                    
                    if content and not self._is_encrypted_content(content):
                        print("成功获取有效内容")
                        return content
                    else:
                        print("内容可能被加密，尝试其他解码方式...")
                        # 尝试原始字节解码
                        if response.content:
                            alternative_content = self._try_different_encodings(response.content)
                            if alternative_content and not self._is_encrypted_content(alternative_content):
                                print("使用替代编码成功解码")
                                return alternative_content
                            
                # 等待后重试
                time.sleep(random.uniform(2.0, 5.0))
                
            except Exception as e:
                print(f"获取内容时出错: {e}")
                time.sleep(random.uniform(3.0, 6.0))
                
        print("无法获取有效内容")
        return None
        
    def parse_content(self, content: str) -> List[str]:
        """解析内容中的IP地址"""
        ip_addresses = []
        
        if not content:
            return ip_addresses
            
        # 方法1: 正则表达式匹配IP地址
        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::\d+)?\b'
        matches = re.findall(ip_pattern, content)
        
        for ip in matches:
            # 过滤无效IP
            if (not ip.startswith('0.') and 
                not ip.startswith('127.') and
                not ip.startswith('192.168.') and
                not ip.startswith('10.') and
                not ip.startswith('172.') and
                ip.count('.') == 3):
                clean_ip = ip.split(':')[0]  # 去掉端口号
                if clean_ip not in ip_addresses:
                    ip_addresses.append(clean_ip)
                    
        # 方法2: 查找特定格式的IP
        url_pattern = r'https?://([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})'
        url_matches = re.findall(url_pattern, content)
        ip_addresses.extend([ip for ip in url_matches if ip not in ip_addresses])
        
        return list(set(ip_addresses))[:100]  # 去重并限制数量
        
    def crawl(self) -> Dict:
        """执行爬取操作"""
        result = {
            'success': False,
            'ip_addresses': [],
            'content_info': {},
            'error': None
        }
        
        try:
            print("开始终极绕过爬取...")
            
            # 获取页面内容
            content = self.get_page_content()
            
            if content:
                result['content_info'] = {
                    'length': len(content),
                    'sample': content[:200] + '...' if len(content) > 200 else content
                }
                
                # 解析IP地址
                ip_addresses = self.parse_content(content)
                
                result['success'] = True
                result['ip_addresses'] = ip_addresses
                
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
    print("=== 终极Cloudflare绕过爬虫 ===")
    
    crawler = UltimateBypassCrawler()
    result = crawler.crawl()
    
    if result['success']:
        print(f"\n爬取统计:")
        print(f"- 内容长度: {result['content_info'].get('length', 0)} 字符")
        print(f"- 找到IP地址: {len(result['ip_addresses'])} 个")
        
        if result['ip_addresses']:
            print(f"\nIP地址列表:")
            for i, ip in enumerate(result['ip_addresses'][:20], 1):
                print(f"  {i:2d}. {ip}")
            if len(result['ip_addresses']) > 20:
                print(f"  ... 还有 {len(result['ip_addresses']) - 20} 个IP地址未显示")
        else:
            print("\n内容样本:")
            print(result['content_info'].get('sample', '无内容'))
    else:
        print(f"\n爬取失败: {result['error']}")

if __name__ == "__main__":
    main()