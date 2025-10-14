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
                import pypinyin
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
                
                # 检查是否为中文频道名称
                if re.search(r'[\u4e00-\u9fff]', name):
                    # 中文频道按拼音升序排列
                    pinyin_list = pypinyin.lazy_pinyin(name)
                    pinyin_str = ''.join(pinyin_list)
                    
                    # 处理中文名称中的数字（自然数排序）
                    def convert(text):
                        return int(text) if text.isdigit() else text.lower()
                    
                    # 将拼音和数字混合排序
                    return [convert(c) for c in re.split('([0-9]+)', pinyin_str)]
                else:
                    # 英文频道按字母升序，数字按自然数排序
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
            if self.use_vlc:
                # 使用VLC进行实际流媒体测试（添加超时控制）
                self.logger.info(f"正在使用VLC测试频道: {channel['name']}")
                try:
                    # 直接调用VLC测试，不使用线程池
                    vlc_result = self.vlc_tester.test_stream(channel['url'])
                    
                    # 正确处理VLC测试结果
                    if isinstance(vlc_result, str):
                        if vlc_result == 'success':
                            # VLC测试成功
                            valid_count += 1
                            score = 75  # 给VLC成功测试一个合理的评分
                            scores.append(score)
                            self.logger.debug(f"频道 {channel['name']} VLC测试成功: 评分={score:.2f}")
                        else:
                            # VLC测试失败
                            scores.append(0)
                            self.logger.debug(f"频道 {channel['name']} VLC测试失败: {vlc_result}")
                    elif isinstance(vlc_result, dict):
                        if vlc_result.get('available', False):
                            valid_count += 1
                            score = vlc_result.get('score', 0.7) * 100
                            scores.append(score)
                            self.logger.debug(f"频道 {channel['name']} 测试成功: 评分={score:.2f}")
                        else:
                            scores.append(0)
                            error_msg = vlc_result.get('error', '未知错误')
                            self.logger.debug(f"频道 {channel['name']} 测试失败: {error_msg}")
                    else:
                        scores.append(0)
                        self.logger.debug(f"频道 {channel['name']} 测试返回意外格式: {type(vlc_result)}")
                        
                except Exception as e:
                    # 特殊处理：VLC测试器有时会抛出包含'success'的异常
                    error_str = str(e)
                    if 'success' in error_str.lower():
                        # 这实际上是测试成功的情况
                        valid_count += 1
                        score = 75  # 给一个合理的评分
                        scores.append(score)
                        self.logger.debug(f"频道 {channel['name']} VLC测试成功（从异常中识别）: 评分={score:.2f}")
                    else:
                        scores.append(0)
                        self.logger.debug(f"频道 {channel['name']} 测试异常: {e}")
                                
            else:
                # HTTP测试模式增强版
                try:
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
                    else:
                        scores.append(0)
                except Exception as e:
                    self.logger.error(f"HTTP测试频道 {channel['name']} 时出错: {e}")
                    scores.append(0)
        
        # 计算最终结果 - 修复抽样测试逻辑
        total_channels = len(channels)
        tested_channels = len(test_channels)
        
        # 如果是抽样测试，需要根据抽样结果推断整体情况
        if tested_channels < total_channels:
            # 抽样测试的成功率
            sample_success_rate = valid_count / tested_channels if tested_channels > 0 else 0
            
            self.logger.info(f"抽样测试结果: {valid_count}/{tested_channels} 成功，成功率: {sample_success_rate:.2%}")
            
            # 如果抽样成功率太低，认为整个文件不可用
            if sample_success_rate < 0.1:  # 抽样成功率低于10%
                self.logger.warning(f"抽样测试成功率过低: {sample_success_rate:.2%}，判定文件不可用")
                availability_rate = sample_success_rate
                is_valid = False
                display_valid_count = int(total_channels * sample_success_rate)  # 直接按抽样结果计算
            else:
                # 根据抽样结果推断总体可用率（保守估计）
                estimated_valid_count = int(total_channels * sample_success_rate * 0.8)  # 打8折保守估计
                availability_rate = estimated_valid_count / total_channels
                is_valid = availability_rate >= 0.3
                display_valid_count = estimated_valid_count
                self.logger.info(f"基于抽样结果推断：总体可用率约为 {availability_rate:.2%}")
        else:
            # 全量测试
            availability_rate = valid_count / total_channels if total_channels > 0 else 0
            is_valid = availability_rate >= 0.3
            display_valid_count = valid_count
        
        # 计算平均评分
        avg_score = sum(scores)/len(scores) if scores else 0
        
        self.logger.info(
            f"文件 {os.path.basename(file_path)} 测试结果: "
            f"可用率={availability_rate:.2%}, "
            f"综合评分={avg_score:.2f}, "
            f"可用={is_valid}"
        )
        
        return is_valid, avg_score, display_valid_count, len(channels)
    
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
                import pypinyin
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
                
                # 检查是否为中文频道名称
                if re.search(r'[\u4e00-\u9fff]', name):
                    # 中文频道按拼音升序排列
                    pinyin_list = pypinyin.lazy_pinyin(name)
                    pinyin_str = ''.join(pinyin_list)
                    
                    # 处理中文名称中的数字（自然数排序）
                    def convert(text):
                        return int(text) if text.isdigit() else text.lower()
                    
                    # 将拼音和数字混合排序
                    return [convert(c) for c in re.split('([0-9]+)', pinyin_str)]
                else:
                    # 英文频道按字母升序，数字按自然数排序
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
        """完整的M3U文件优化流程
        
        1. 测试所有文件的可用性，删除不可用的文件
        2. 去重（基于源IP地址）
        3. 按质量排序（速度、可用率）
        4. 统一重命名为 [序号]IP_频道数ch.m3u 格式
        """
        self.logger.info(f"开始完整优化M3U文件，目录: {self.m3u_dir}")
        
        # 获取所有M3U文件（排除特殊文件）
        import glob
        all_files = glob.glob(os.path.join(self.m3u_dir, "*.m3u"))
        m3u_files = [f for f in all_files if not os.path.basename(f).startswith('all_channels_') 
                     and not os.path.basename(f).endswith('.json')]
        
        self.logger.info(f"找到 {len(m3u_files)} 个M3U文件，开始优化流程")
        
        if not m3u_files:
            self.logger.warning("未找到任何M3U文件")
            return
        
        # 第一步：测试所有文件的可用性
        self.logger.info("=" * 50)
        self.logger.info("第一步：测试文件可用性")
        self.logger.info("=" * 50)
        
        valid_files = []
        deleted_files = []
        
        for file_path in m3u_files:
            file_name = os.path.basename(file_path)
            try:
                self.logger.info(f"正在测试文件: {file_name}")
                is_valid, avg_speed, valid_count, total_count = self.test_m3u_file(file_path)
                
                if is_valid and valid_count > 0:
                    # 提取源IP地址
                    source_ip = self._extract_source_ip(file_path, file_name)
                    
                    valid_files.append({
                        'file_name': file_name,
                        'file_path': file_path,
                        'source_ip': source_ip,
                        'avg_speed': avg_speed,
                        'valid_count': valid_count,
                        'total_count': total_count,
                        'availability': valid_count / total_count if total_count > 0 else 0
                    })
                    self.logger.info(f"[OK] 文件 {file_name} 可用，保留 (可用率: {valid_count}/{total_count}, 速度: {avg_speed:.2f})")
                else:
                    # 删除不可用的文件
                    try:
                        os.remove(file_path)
                        deleted_files.append(file_name)
                        self.logger.warning(f"[DEL] 文件 {file_name} 不可用，已删除")
                    except Exception as delete_error:
                        self.logger.error(f"删除文件 {file_name} 失败: {delete_error}")
                        
            except Exception as e:
                self.logger.error(f"测试文件 {file_name} 时出错: {e}")
                # 测试出错的文件也删除
                try:
                    os.remove(file_path)
                    deleted_files.append(file_name)
                    self.logger.warning(f"[DEL] 文件 {file_name} 测试出错，已删除")
                except Exception as delete_error:
                    self.logger.error(f"删除出错文件 {file_name} 失败: {delete_error}")
        
        self.logger.info(f"可用性测试完成: 保留 {len(valid_files)} 个，删除 {len(deleted_files)} 个")
        
        if not valid_files:
            self.logger.warning("没有找到任何可用的M3U文件")
            return
        
        # 第二步：去重（基于源IP地址，保留质量最好的）
        self.logger.info("=" * 50)
        self.logger.info("第二步：去重处理")
        self.logger.info("=" * 50)
        
        # 按源IP分组
        ip_groups = {}
        for file_info in valid_files:
            ip = file_info['source_ip']
            if ip not in ip_groups:
                ip_groups[ip] = []
            ip_groups[ip].append(file_info)
        
        # 每个IP只保留质量最好的文件
        deduplicated_files = []
        duplicate_files = []
        
        for ip, files in ip_groups.items():
            if len(files) > 1:
                # 按综合质量排序：可用率 * 0.7 + 速度 * 0.3
                files.sort(key=lambda x: (x['availability'] * 0.7 + min(x['avg_speed']/10, 1) * 0.3), reverse=True)
                best_file = files[0]
                deduplicated_files.append(best_file)
                
                # 删除重复的文件
                for dup_file in files[1:]:
                    try:
                        os.remove(dup_file['file_path'])
                        duplicate_files.append(dup_file['file_name'])
                        self.logger.info(f"[DUP] 删除重复文件: {dup_file['file_name']} (保留更优质的 {best_file['file_name']})")
                    except Exception as e:
                        self.logger.error(f"删除重复文件 {dup_file['file_name']} 失败: {e}")
            else:
                deduplicated_files.append(files[0])
        
        self.logger.info(f"去重完成: 保留 {len(deduplicated_files)} 个，删除重复 {len(duplicate_files)} 个")
        
        # 第三步：按质量排序
        self.logger.info("=" * 50)
        self.logger.info("第三步：质量排序")
        self.logger.info("=" * 50)
        
        # 综合评分排序：可用率 * 0.6 + 速度 * 0.3 + 频道数量 * 0.1
        deduplicated_files.sort(key=lambda x: (
            x['availability'] * 0.6 + 
            min(x['avg_speed']/10, 1) * 0.3 + 
            min(x['total_count']/500, 1) * 0.1
        ), reverse=True)
        
        # 第四步：统一重命名
        self.logger.info("=" * 50)
        self.logger.info("第四步：统一重命名")
        self.logger.info("=" * 50)
        
        renamed_files = []
        for i, file_info in enumerate(deduplicated_files):
            rank = i + 1
            source_ip = file_info['source_ip']
            channel_count = file_info['total_count']
            
            # 统一命名格式：[序号]IP_频道数ch.m3u
            new_name = f"[{rank:02d}]{source_ip}_{channel_count}ch.m3u"
            new_path = os.path.join(self.m3u_dir, new_name)
            old_path = file_info['file_path']
            
            try:
                # 如果新旧路径不同，进行重命名
                if new_path != old_path:
                    # 如果目标文件已存在，先删除
                    if os.path.exists(new_path):
                        os.remove(new_path)
                    
                    # 重命名文件
                    os.rename(old_path, new_path)
                    
                renamed_files.append({
                    'rank': rank,
                    'old_name': file_info['file_name'],
                    'new_name': new_name,
                    'source_ip': source_ip,
                    'availability': file_info['availability'],
                    'avg_speed': file_info['avg_speed'],
                    'channel_count': channel_count
                })
                
                self.logger.info(f"[{rank:02d}] {file_info['file_name']} -> {new_name} (可用率: {file_info['availability']:.1%}, 速度: {file_info['avg_speed']:.2f})")
                
            except Exception as e:
                self.logger.error(f"重命名文件 {file_info['file_name']} 失败: {e}")
        
        # 保存优化结果
        result_summary = {
            'timestamp': datetime.now().isoformat(),
            'optimization_steps': {
                'total_files_found': len(m3u_files),
                'valid_files_after_testing': len(valid_files),
                'files_after_deduplication': len(deduplicated_files),
                'final_renamed_files': len(renamed_files)
            },
            'deleted_files': deleted_files,
            'duplicate_files': duplicate_files,
            'final_files': renamed_files
        }
        
        result_file = os.path.join(self.log_dir, f"optimization_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_summary, f, ensure_ascii=False, indent=2)
        
        self.logger.info("=" * 50)
        self.logger.info("优化完成总结:")
        self.logger.info(f"  - 原始文件: {len(m3u_files)} 个")
        self.logger.info(f"  - 删除不可用: {len(deleted_files)} 个")
        self.logger.info(f"  - 删除重复: {len(duplicate_files)} 个")
        self.logger.info(f"  - 最终保留: {len(renamed_files)} 个")
        self.logger.info(f"  - 结果保存到: {result_file}")
        self.logger.info("=" * 50)
    
    def _extract_source_ip(self, file_path: str, file_name: str) -> str:
        """从文件中提取源IP地址"""
        import re
        
        # 1. 首先尝试从文件内容中提取
        try:
            channels = self.parse_m3u_file(file_path)
            if channels and len(channels) > 0:
                url = channels[0]['url']
                # 提取IP地址或域名
                url_match = re.search(r'https?://([^:/]+)', url)
                if url_match:
                    host = url_match.group(1)
                    # 如果是IP地址，直接返回
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', host):
                        return host
                    # 如果是域名，也返回
                    return host
        except:
            pass
        
        # 2. 从文件名中提取IP地址
        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', file_name)
        if ip_match:
            return ip_match.group(1)
        
        # 3. 从文件名中提取域名
        domain_match = re.search(r'([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9][-a-zA-Z0-9]*)', file_name)
        if domain_match:
            return domain_match.group(1)
        
        # 4. 提取文件名中的第一个有意义部分
        parts = file_name.replace('[', '').replace(']', '').split('_')
        for part in parts:
            if part and not part.isdigit() and 'ch' not in part and '.m3u' not in part:
                return part
        
        return "unknown"
        

if __name__ == "__main__":
    # 示例用法
    optimizer = M3UOptimizer("output/m3u", use_vlc=True)
    optimizer.optimize_m3u_files()

if __name__ == "__main__":
    # 示例用法
    optimizer = M3UOptimizer("output/m3u")
    optimizer.optimize_m3u_files()