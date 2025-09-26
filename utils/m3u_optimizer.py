"""M3U文件优化模块

该模块用于优化现有的M3U文件，包括：
1. 检测文件可用性，删除失效的源文件
2. 对文件中的频道进行测速排序
3. 根据测速结果重命名文件
4. 记录处理日志
"""
import os
import re
import time
import json
import logging
import requests
import concurrent.futures
from typing import List, Dict, Tuple
from datetime import datetime
from pathlib import Path
from models.channel import Channel

class M3UOptimizer:
    """M3U文件优化类"""
    
    def __init__(self, m3u_dir: str, log_dir: str = None, max_workers: int = 10, timeout: int = 5):
        """初始化M3U优化器
        
        Args:
            m3u_dir: M3U文件目录
            log_dir: 日志目录，默认为m3u_dir
            max_workers: 并发测速的最大线程数
            timeout: 测速超时时间（秒）
        """
        self.m3u_dir = m3u_dir
        self.log_dir = log_dir if log_dir else m3u_dir
        self.max_workers = max_workers
        self.timeout = timeout
        
        # 创建日志目录
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 配置日志
        self.logger = logging.getLogger("M3UOptimizer")
        self.logger.setLevel(logging.INFO)
        
        # 创建日志文件处理器
        log_file = os.path.join(self.log_dir, f"m3u_optimizer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        
        # 设置日志格式
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # 添加处理器到日志记录器
        self.logger.addHandler(file_handler)
        
        # 同时输出到控制台
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        self.logger.info(f"M3U优化器初始化完成，目标目录: {m3u_dir}")
    
    def parse_m3u_file(self, file_path: str) -> List[Dict]:
        """解析M3U文件，提取频道信息
        
        Args:
            file_path: M3U文件路径
            
        Returns:
            频道信息列表
        """
        channels = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.startswith('#EXTINF:'):
                    # 提取频道名称
                    name_match = re.search(r'#EXTINF:-1,(.*)', line)
                    if name_match and i + 1 < len(lines):
                        channel_name = name_match.group(1).strip()
                        channel_url = lines[i + 1].strip()
                        
                        if channel_url.startswith(('http://', 'https://')):
                            channels.append({
                                'name': channel_name,
                                'url': channel_url
                            })
                        i += 2
                        continue
                i += 1
                
            self.logger.info(f"从 {file_path} 解析到 {len(channels)} 个频道")
            return channels
            
        except Exception as e:
            self.logger.error(f"解析M3U文件 {file_path} 时出错: {e}")
            return []
    
    def test_channel_speed(self, channel: Dict) -> float:
        """测试频道连接速度
        
        Args:
            channel: 频道信息字典
            
        Returns:
            连接速度（毫秒），如果连接失败则返回无穷大
        """
        try:
            start_time = time.time()
            response = requests.get(
                channel['url'], 
                timeout=self.timeout, 
                stream=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
                }
            )
            if response.status_code == 200:
                # 只读取少量数据以验证流是否有效
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        break
                return (time.time() - start_time) * 1000
        except:
            pass
        return float('inf')
    
    def test_m3u_file(self, file_path: str) -> Tuple[bool, float, int, int]:
        """测试M3U文件的可用性和平均速度
        
        Args:
            file_path: M3U文件路径
            
        Returns:
            (是否可用, 平均速度, 可用频道数, 总频道数)
        """
        channels = self.parse_m3u_file(file_path)
        if not channels:
            return False, float('inf'), 0, 0
        
        # 随机选择最多10个频道进行测试
        import random
        test_channels = random.sample(channels, min(10, len(channels)))
        
        valid_count = 0
        total_speed = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            speeds = list(executor.map(self.test_channel_speed, test_channels))
            
        for speed in speeds:
            if speed < float('inf'):
                valid_count += 1
                total_speed += speed
        
        # 计算可用率和平均速度
        availability = valid_count / len(test_channels) if test_channels else 0
        avg_speed = total_speed / valid_count if valid_count > 0 else float('inf')
        
        is_valid = availability >= 0.3  # 至少30%的频道可用才认为文件有效
        
        self.logger.info(f"文件 {os.path.basename(file_path)} 测试结果: 可用率={availability:.2%}, 平均速度={avg_speed:.2f}ms, 可用={is_valid}")
        
        return is_valid, avg_speed, valid_count, len(test_channels)
    
    def optimize_m3u_files(self) -> None:
        """优化M3U文件
        
        1. 检测文件可用性，删除失效的源文件
        2. 对有效文件进行测速排序
        3. 根据测速结果重命名文件
        """
        self.logger.info(f"开始优化M3U文件，目录: {self.m3u_dir}")
        
        # 获取所有M3U文件
        m3u_files = [f for f in os.listdir(self.m3u_dir) if f.endswith('.m3u')]
        self.logger.info(f"找到 {len(m3u_files)} 个M3U文件")
        
        if not m3u_files:
            self.logger.warning("未找到任何M3U文件")
            return
        
        # 测试文件可用性和速度
        file_results = []
        deleted_files = []
        
        for file_name in m3u_files:
            file_path = os.path.join(self.m3u_dir, file_name)
            is_valid, avg_speed, valid_count, total_count = self.test_m3u_file(file_path)
            
            if is_valid:
                # 提取IP地址
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', file_name)
                ip = ip_match.group(1) if ip_match else "unknown"
                
                file_results.append({
                    'file_name': file_name,
                    'file_path': file_path,
                    'avg_speed': avg_speed,
                    'valid_count': valid_count,
                    'total_count': total_count,
                    'availability': valid_count / total_count if total_count > 0 else 0,
                    'ip': ip
                })
            else:
                # 删除无效文件
                try:
                    os.remove(file_path)
                    deleted_files.append(file_name)
                    self.logger.info(f"已删除无效文件: {file_name}")
                except Exception as e:
                    self.logger.error(f"删除文件 {file_name} 时出错: {e}")
        
        # 按平均速度排序
        file_results.sort(key=lambda x: x['avg_speed'])
        
        # 重命名文件
        renamed_files = []
        for i, result in enumerate(file_results):
            rank = i + 1
            new_name = f"[{rank:02d}]{result['ip']}.m3u"
            new_path = os.path.join(self.m3u_dir, new_name)
            
            try:
                os.rename(result['file_path'], new_path)
                renamed_files.append({
                    'old_name': result['file_name'],
                    'new_name': new_name,
                    'rank': rank,
                    'avg_speed': result['avg_speed'],
                    'availability': result['availability']
                })
                self.logger.info(f"已重命名文件: {result['file_name']} -> {new_name}")
            except Exception as e:
                self.logger.error(f"重命名文件 {result['file_name']} 时出错: {e}")
        
        # 保存处理结果
        result_summary = {
            'timestamp': datetime.now().isoformat(),
            'total_files': len(m3u_files),
            'valid_files': len(file_results),
            'deleted_files': deleted_files,
            'renamed_files': renamed_files
        }
        
        result_file = os.path.join(self.log_dir, f"optimization_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_summary, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"M3U文件优化完成，共处理 {len(m3u_files)} 个文件，删除 {len(deleted_files)} 个无效文件，重命名 {len(renamed_files)} 个文件")
        self.logger.info(f"处理结果已保存到: {result_file}")

if __name__ == "__main__":
    # 示例用法
    optimizer = M3UOptimizer("output/m3u")
    optimizer.optimize_m3u_files()