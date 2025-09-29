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
import threading
from typing import List, Dict, Tuple
from datetime import datetime
from pathlib import Path
# from models.channel import Channel  # 移除未使用的导入
from utils.speed_tester import SpeedTester
from utils.vlc_tester import VLCTester

class M3UOptimizer:
    """M3U文件优化类"""
    
    # 频道质量标准
    MIN_ACCEPTABLE_SCORE = 85  # 最低可接受评分
    MAX_BUFFER_TIME = 2.0      # 最大缓冲时间(秒)
    
    def __init__(self, m3u_dir: str, log_dir: str = None, max_workers: int = 10, timeout: int = 5, use_vlc: bool = False):
        """初始化M3U优化器
        
        Args:
            m3u_dir: M3U文件目录
            log_dir: 日志目录，默认为m3u_dir
            max_workers: 并发测速的最大线程数
            timeout: 测速超时时间（秒）
            use_vlc: 是否使用VLC进行实际流媒体测试
        """
        self.m3u_dir = m3u_dir
        self.log_dir = log_dir if log_dir else m3u_dir
        self.max_workers = max_workers
        self.timeout = timeout
        self.test_interval = 6 * 3600  # 6小时
        self.running = False
        
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
        
        self.speed_tester = SpeedTester(max_workers=max_workers)
        self.use_vlc = use_vlc
        
        # 如果启用VLC测试，初始化VLC测试器
        if self.use_vlc:
            try:
                self.vlc_tester = VLCTester(timeout=timeout)
                self.logger.info("VLC测试器初始化成功")
            except Exception as e:
                self.logger.error(f"VLC测试器初始化失败: {e}")
                self.use_vlc = False
        
        # 日志已在前面初始化
        
        self.logger.info(f"M3U优化器初始化完成，目标目录: {m3u_dir}")
    
    def is_channel_acceptable(self, test_result):
        """检查频道是否达到质量标准"""
        return (test_result['score'] >= self.MIN_ACCEPTABLE_SCORE and 
                test_result['buffer_time'] <= self.MAX_BUFFER_TIME)
                
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
                
            # 改进的频道名称排序（统一返回列表类型）
            def natural_sort_key(s):
                import re
                name = s['name']
                
                # 标准化频道名称格式（统一为CCTV-数字格式）
                name = re.sub(r'CCTV[- ]?(\d+)', r'CCTV-\1', name)
                
                # 特殊处理CCTV频道
                if name.startswith('CCTV'):
                    # 处理带有"+"号的CCTV频道（如CCTV-5+）
                    plus_match = re.search(r'CCTV-(\d+)\+', name)
                    if plus_match:
                        # 带"+"号的频道排在对应数字频道之后
                        return ['CCTV', int(plus_match.group(1)), 1]
                    
                    # 提取数字部分
                    num_match = re.search(r'CCTV-(\d+)', name)
                    if num_match:
                        return ['CCTV', int(num_match.group(1)), 0]
                    
                    # 处理无数字的CCTV频道（如"CCTV综合"）
                    return ['CCTV', 0, name]
                
                # 处理其他常见电视台命名模式（如卫视频道）
                for prefix in ['北京', '东方', '湖南', '江苏', '浙江']:
                    if name.startswith(prefix):
                        return [prefix, name]
                
                # 处理卫视频道
                if '卫视' in name:
                    province = name.split('卫视')[0]
                    return [province, '卫视']
                
                # 普通频道名称的自然排序
                def convert(text):
                    return int(text) if text.isdigit() else text.lower()
                return [convert(c) for c in re.split('([0-9]+)', name)]
            
            # 先标准化频道名称格式
            for channel in channels:
                channel['name'] = re.sub(r'CCTV[- ]?(\d+)', r'CCTV-\1', channel['name'])
            
            # 排序并记录排序后的频道名称
            channels.sort(key=natural_sort_key)
            self.logger.debug("排序后的前10个频道:")
            for i, channel in enumerate(channels[:10]):
                self.logger.debug(f"{i+1}. {channel['name']}")
            return channels
            
        except Exception as e:
            self.logger.error(f"解析M3U文件 {file_path} 时出错: {e}")
            return []
    
    def get_test_channels(self, channels: List[Dict]) -> List[Dict]:
        """智能抽样策略
        Args:
            channels: 频道列表
        Returns:
            测试频道样本
        """
        import random
        # 动态样本量 (5-15个，大列表适当增加)
        sample_size = min(max(5, len(channels)//20), 15)
        
        # 按频道类型分组抽样
        groups = {
            '卫视': [c for c in channels if '卫视' in c['name']],
            '央视': [c for c in channels if 'CCTV' in c['name'] or '央视' in c['name']],
            '其他': [c for c in channels if all(kw not in c['name'] for kw in ['卫视','CCTV','央视'])]
        }
        
        # 每组至少抽1个，最多抽sample_size//3个
        test_channels = []
        for group_name, group_channels in groups.items():
            if group_channels:
                sample_num = min(max(1, sample_size//3), len(group_channels))
                test_channels.extend(random.sample(group_channels, sample_num))
                self.logger.debug(f"从[{group_name}]组抽样{sample_num}个频道")
        
        # 补足样本量
        if len(test_channels) < sample_size:
            remaining = [c for c in channels if c not in test_channels]
            if remaining:
                need = sample_size - len(test_channels)
                test_channels.extend(random.sample(remaining, min(need, len(remaining))))
                self.logger.debug(f"补充随机抽样{need}个频道")
        
        return test_channels

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
    
    def calculate_fluency_score(self, test_result: Dict) -> float:
        """多维度流畅度评分算法
        Args:
            test_result: 测试结果字典
        Returns:
            评分 (0-100)
        """
        # 基础分（0-100）
        base_score = 100 - min(test_result.get('latency',0)/10, 50)  # 延迟惩罚
        
        # 稳定性加成（0-30）
        stability_bonus = test_result.get('stability',0) * 30
        
        # 缓冲惩罚（0-20）
        buffer_penalty = min(test_result.get('buffer_events',0)*2, 20)
        
        return max(0, min(100, base_score + stability_bonus - buffer_penalty))

    def test_m3u_file(self, file_path: str) -> Tuple[bool, float, int, int]:
        """测试M3U文件的可用性和流畅度评分
        
        Args:
            file_path: M3U文件路径
            
        Returns:
            (是否可用, 流畅度评分[0-100], 可用频道数, 总频道数)
        """
        channels = self.parse_m3u_file(file_path)
        if not channels:
            return False, 0.0, 0, 0
        
        # 测试所有频道的动态指标
        self.speed_tester.batch_test([c['url'] for c in channels])
        
        # 计算综合流畅度评分
        scores = []
        valid_count = 0
        total_score = 0
        
        # 智能抽样测试频道
        test_channels = self.get_test_channels(channels)
        self.logger.info(f"将通过智能抽样测试 {len(test_channels)}/{len(channels)} 个频道")
        
        for channel in test_channels:
            try:
                if self.use_vlc:
                    # 使用VLC进行实际流媒体测试
                    self.logger.info(f"正在使用VLC测试频道: {channel['name']}")
                    result = self.vlc_tester.test_stream(channel['url'])
                    
                    if result['success'] and self.is_channel_acceptable(result):
                        # 使用多维度评分算法
                        fluency_score = self.calculate_fluency_score({
                            'latency': result.get('latency', 0),
                            'stability': result.get('stability', 0),
                            'buffer_events': result.get('buffer_events', 0)
                        })
                        
                        scores.append(fluency_score)
                        valid_count += 1
                        self.logger.info(
                            f"频道 {channel['name']} 流畅度评分: {fluency_score:.1f} "
                            f"(缓冲: {result['buffer_time']:.2f}s, "
                            f"缓冲事件: {result['buffer_events']}, "
                            f"丢帧: {result['frames_dropped']})"
                        )
                    else:
                        self.logger.warning(f"VLC测试失败: {result.get('error', '未知错误')}")
                else:
                    # HTTP测试模式增强版
                    result = self.speed_tester.enhanced_test(channel['url'])
                    
                    if result['success']:
                        # 使用多维度评分算法
                        fluency_score = self.calculate_fluency_score({
                            'latency': result.get('latency', 0),
                            'stability': result.get('stability', 0),
                            'buffer_events': result.get('buffer_events', 0)
                        })
                        
                        scores.append(fluency_score)
                        valid_count += 1
                        self.logger.info(
                            f"频道 {channel['name']} 预估流畅度: {fluency_score:.1f} "
                            f"(延迟: {result['latency']}ms, "
                            f"稳定性: {result['stability']:.2f})"
                        )
            except Exception as e:
                self.logger.error(f"测试频道 {channel['name']} 时出错: {e}")
        
        # 对于未测试的频道，使用HTTP请求测试
        if len(test_channels) < len(channels):
            for channel in channels[len(test_channels):]:
                score = self.speed_tester.calculate_score(channel['url'])
                if score > 0:
                    valid_count += 1
        
        avg_score = sum(scores)/len(scores) if scores else 0
        is_valid = valid_count / len(channels) >= 0.3  # 至少30%可用
        
        self.logger.info(
            f"文件 {os.path.basename(file_path)} 测试结果: "
            f"可用率={valid_count/len(channels):.2%}, "
            f"综合评分={avg_score:.2f}, "
            f"可用={is_valid}"
        )
        
        return is_valid, avg_score, valid_count, len(channels)
    
    def run_periodic_tests(self):
        """定时执行测速任务"""
        self.running = True
        while self.running:
            self.logger.info("开始定时测速检查...")
            try:
                m3u_files = [f for f in os.listdir(self.m3u_dir) if f.endswith('.m3u')]
                for file_name in m3u_files:
                    file_path = os.path.join(self.m3u_dir, file_name)
                    self.test_m3u_file(file_path)
            except Exception as e:
                self.logger.error(f"定时测速出错: {e}")
            
            time.sleep(self.test_interval)

    def start_background_tester(self):
        """启动后台测速线程"""
        tester = threading.Thread(target=self.run_periodic_tests)
        tester.daemon = True
        tester.start()
        self.logger.info("后台测速线程已启动")
        
    def save_sorted_m3u_file(self, file_path: str, channels: List[Dict]) -> bool:
        """将频道按名称排序后保存到M3U文件
        
        Args:
            file_path: M3U文件路径
            channels: 频道信息列表
            
        Returns:
            是否成功保存
        """
        try:
            # 使用自然排序算法对频道进行排序
            def natural_sort_key(s):
                import re
                name = s['name']
                
                # 特殊处理CCTV频道
                if name.startswith('CCTV'):
                    # 处理带有"+"号的CCTV频道（如CCTV-5+）
                    plus_match = re.search(r'CCTV[- ]?(\d+)\+', name)
                    if plus_match:
                        # 带"+"号的频道排在对应数字频道之后
                        return ['CCTV', int(plus_match.group(1)), 1]
                    
                    # 提取数字部分，支持多种格式：CCTV1, CCTV-1, CCTV 1
                    num_match = re.search(r'CCTV[- ]?(\d+)', name)
                    if num_match:
                        return ['CCTV', int(num_match.group(1)), 0]
                    
                    # 处理无数字的CCTV频道（如"CCTV综合"）
                    return ['CCTV', 0, name]
                
                # 处理其他常见电视台命名模式（如卫视频道）
                for prefix in ['北京', '东方', '湖南', '江苏', '浙江']:
                    if name.startswith(prefix):
                        return [prefix, name]
                
                # 处理卫视频道
                if '卫视' in name:
                    province = name.split('卫视')[0]
                    return [province, '卫视']
                
                # 普通频道名称的自然排序
                def convert(text):
                    return int(text) if text.isdigit() else text.lower()
                return [convert(c) for c in re.split('([0-9]+)', name)]
            
            # 使用自然排序算法排序
            sorted_channels = sorted(channels, key=natural_sort_key)
            
            # 调试日志：输出排序后的前10个频道
            self.logger.debug("排序后的前10个频道:")
            for i, channel in enumerate(sorted_channels[:10]):
                self.logger.debug(f"{i+1}. {channel['name']}")
            
            with open(file_path, 'w', encoding='utf-8') as f:
                # 写入M3U头部
                f.write("#EXTM3U\n")
                
                # 写入每个频道
                for channel in sorted_channels:
                    f.write(f"#EXTINF:-1,{channel['name']}\n")
                    f.write(f"{channel['url']}\n")
                
            self.logger.info(f"已将 {len(sorted_channels)} 个频道按名称排序并保存到 {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存排序后的M3U文件 {file_path} 时出错: {e}")
            return False

    def optimize_m3u_files(self) -> None:
        """优化M3U文件
        
        1. 检测文件可用性，删除失效的源文件
        2. 对有效文件进行测速排序
        3. 根据测速结果重命名文件
        """
        self.logger.info(f"开始优化M3U文件，目录: {self.m3u_dir}")
        # 启动后台测速
        self.start_background_tester()
        
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
                # 提取源地址（IP地址或域名）
                # 1. 首先尝试从文件内容中提取源地址
                channels = self.parse_m3u_file(file_path)
                channel_count = len(channels)  # 获取实际频道数量
                source_from_content = None
                if channels and len(channels) > 0:
                    # 从第一个频道URL中提取域名或IP
                    url = channels[0]['url']
                    url_match = re.search(r'https?://([^:/]+)', url)
                    if url_match:
                        source_from_content = url_match.group(1)
                
                # 2. 如果从内容中无法提取，则尝试从文件名中提取
                if source_from_content:
                    source = source_from_content
                else:
                    # 从文件名中提取IP地址
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', file_name)
                    if ip_match:
                        source = ip_match.group(1)
                    else:
                        # 从文件名中提取域名
                        domain_match = re.search(r'([a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)', file_name)
                        if domain_match:
                            source = domain_match.group(1)
                        else:
                            # 尝试从文件名中提取任何有意义的标识符
                            parts = file_name.split('_')
                            if len(parts) > 0 and not parts[0].startswith('['):
                                source = parts[0]
                            else:
                                source = "unknown"
                
                file_results.append({
                    'file_name': file_name,
                    'file_path': file_path,
                    'avg_speed': avg_speed,
                    'valid_count': valid_count,
                    'total_count': channel_count,  # 使用实际解析到的频道数量
                    'availability': valid_count / total_count if total_count > 0 else 0,
                    'ip': source,
                    'channel_count': channel_count  # 添加频道数量字段
                })
            else:
                # 删除无效文件
                try:
                    os.remove(file_path)
                    deleted_files.append(file_name)
                    self.logger.info(f"已删除无效文件: {file_name}")
                except Exception as e:
                    self.logger.error(f"删除文件 {file_name} 时出错: {e}")
        
        # 按综合质量排序（流畅度评分降序，缓冲时间升序）
        file_results.sort(key=lambda x: (
            -x['avg_speed'],  # 流畅度评分降序
            x.get('buffer_time', 0)  # 缓冲时间升序
        ))
        
        # 重命名文件
        renamed_files = []
        for i, result in enumerate(file_results):
            rank = i + 1
            # 确保文件扩展名只有一个.m3u
            source = result['ip']
            channel_count = result['channel_count']
            
            # 统一格式：所有文件名都包含频道数量
            new_name = f"[{rank:02d}]{source}_{channel_count}ch.m3u"
            new_path = os.path.join(self.m3u_dir, new_name)
            
            try:
                # 如果目标文件已存在，先删除它
                if os.path.exists(new_path) and new_path != result['file_path']:
                    os.remove(new_path)
                    self.logger.info(f"已删除已存在的文件: {new_name}")
                
                # 读取并排序频道信息
                channels = self.parse_m3u_file(result['file_path'])
                if channels:
                    # 调试日志：输出排序前的频道名称
                    self.logger.debug("排序前的频道名称示例:")
                    for i, channel in enumerate(channels[:10]):
                        self.logger.debug(f"{i+1}. {channel['name']}")
                    
                    # 保存排序后的频道
                    self.save_sorted_m3u_file(new_path, channels)
                    
                    # 验证保存后的文件
                    saved_channels = self.parse_m3u_file(new_path)
                    self.logger.debug("保存后的频道名称示例:")
                    for i, channel in enumerate(saved_channels[:10]):
                        self.logger.debug(f"{i+1}. {channel['name']}")
                    # 如果排序保存成功，删除原文件（如果新旧路径不同）
                    if new_path != result['file_path'] and os.path.exists(result['file_path']):
                        os.remove(result['file_path'])
                else:
                    # 如果无法解析频道，则直接重命名
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