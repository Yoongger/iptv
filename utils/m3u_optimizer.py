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

from utils.speed_tester import SpeedTester
from utils.vlc_tester import VLCTester
from config.constants import USER_AGENT, OUTPUT_M3U_DIR, OUTPUT_DATA_DIR

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
        
        # 避免重复添加处理器
        if not self.logger.handlers:
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
                
            # 标准化所有频道名称格式
            for channel in channels:
                channel['name'] = self._standardize_channel_name(channel['name'])
            
            # 使用统一的自然排序算法
            channels.sort(key=self._natural_sort_key)
            
            # 记录排序结果
            self.logger.info(f"解析完成，共 {len(channels)} 个频道")
            self.logger.info("排序后的前20个频道:")
            for i, channel in enumerate(channels[:20]):
                self.logger.info(f"{i+1:2d}. {channel['name']}")
            return channels
            
        except Exception as e:
            self.logger.error(f"解析M3U文件 {file_path} 时出错: {e}")
            return []
    
    def get_test_channels(self, channels: List[Dict]) -> List[Dict]:
        """智能抽样策略（修复卡顿版本）
        Args:
            channels: 频道列表
        Returns:
            测试频道样本
        """
        import random
        # 限制最大样本量，避免过多测试导致卡顿
        sample_size = min(max(3, len(channels)//30), 8)  # 减少样本量
        
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

        
        # 补足样本量
        if len(test_channels) < sample_size:
            remaining = [c for c in channels if c not in test_channels]
            if remaining:
                need = sample_size - len(test_channels)
                test_channels.extend(random.sample(remaining, min(need, len(remaining))))

        
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
                    'User-Agent': USER_AGENT
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

    def _test_single_channel_safe(self, channel: Dict) -> Tuple[float, bool]:
        """安全测试单个频道（优先使用VLC实测速度）
        
        Args:
            channel: 频道信息
            
        Returns:
            (评分, 是否可用)
        """
        try:
            if self.use_vlc:
                # 使用更安全的VLC测试方法
                import threading
                from queue import Queue
                
                result_queue = Queue()
                
                def vlc_test_thread():
                    try:
                        vlc_result = self.vlc_tester.test_stream(channel['url'])
                        result_queue.put(('success', vlc_result))
                    except Exception as e:
                        result_queue.put(('error', str(e)))
                
                # 启动测试线程
                test_thread = threading.Thread(target=vlc_test_thread)
                test_thread.daemon = True
                test_thread.start()
                
                # 等待结果，设置超时
                test_thread.join(timeout=self.timeout)
                
                if not result_queue.empty():
                    status, result = result_queue.get()
                    if status == 'success':
                        if isinstance(result, str) and 'success' in result.lower():
                            return 85.0, True  # 提高VLC测试的基础分数
                        elif isinstance(result, dict) and result.get('available', False):
                            # 使用VLC实测的缓冲时间和稳定性作为主要评分依据
                            buffer_time = result.get('buffer_time', 10)
                            stability = result.get('stability', 0)
                            score = result.get('score', 0.7)
                            
                            # 缓冲时间越短，分数越高（缓冲时间在1-10秒范围内）
                            buffer_score = max(0, 1 - (buffer_time - 1) / 9) * 100
                            
                            # 稳定性越高，分数越高
                            stability_score = stability * 100
                            
                            # 综合评分：缓冲时间权重60%，稳定性权重40%
                            vlc_score = buffer_score * 0.6 + stability_score * 0.4
                            return min(vlc_score, 100), True
                else:
                    # 超时或线程异常
                    self.logger.warning(f"频道 {channel['name']} VLC测试超时")
                    return 0.0, False
                    
                return 0.0, False
            else:
                # HTTP测试模式（备用方案）
                result = self.speed_tester.enhanced_test(channel['url'])
                if result['success']:
                    fluency_score = self.calculate_fluency_score({
                        'latency': result.get('latency', 0),
                        'stability': result.get('stability', 0),
                        'buffer_events': result.get('buffer_events', 0)
                    })
                    return fluency_score * 0.8, True  # HTTP测试分数打8折
                else:
                    return 0.0, False
        except Exception as e:

            return 0.0, False

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
        
        # 智能抽样测试频道（限制最大测试数量避免卡顿）
        test_channels = self.get_test_channels(channels)
        max_test_channels = min(len(test_channels), 8)  # 限制最多测试8个频道
        test_channels = test_channels[:max_test_channels]
        

        
        # 使用线程池进行并发测试，避免阻塞
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(test_channels))) as executor:
            # 提交测试任务
            future_to_channel = {
                executor.submit(self._test_single_channel_safe, channel): channel 
                for channel in test_channels
            }
            
            # 收集结果，设置超时避免无限等待
            for future in concurrent.futures.as_completed(future_to_channel, timeout=self.timeout * len(test_channels)):
                channel = future_to_channel[future]
                try:
                    score, is_valid = future.result(timeout=self.timeout)
                    scores.append(score)
                    if is_valid:
                        valid_count += 1
                except concurrent.futures.TimeoutError:
                    self.logger.warning(f"频道 {channel['name']} 测试超时")
                    scores.append(0)
                except Exception as e:
                    self.logger.error(f"频道 {channel['name']} 测试出错: {e}")
                    scores.append(0)
        
        # 计算最终结果 - 修复抽样测试逻辑
        total_channels = len(channels)
        tested_channels = len(test_channels)
        
        # 如果是抽样测试，需要根据抽样结果推断整体情况
        if tested_channels < total_channels:
            # 抽样测试的成功率
            sample_success_rate = valid_count / tested_channels if tested_channels > 0 else 0
            

            
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
            # 首先标准化所有频道名称格式
            for channel in channels:
                channel['name'] = self._standardize_channel_name(channel['name'])
            
            # 使用统一的自然排序算法
            sorted_channels = sorted(channels, key=self._natural_sort_key)
            
            # 详细记录排序结果
            self.logger.info(f"频道排序完成，共 {len(sorted_channels)} 个频道")
            self.logger.info("排序后的前20个频道:")
            for i, channel in enumerate(sorted_channels[:20]):
                self.logger.info(f"{i+1:2d}. {channel['name']}")
            
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
                # 按综合质量排序：速度 * 0.7 + 可用率 * 0.3（速度优先）
                files.sort(key=lambda x: (min(x['avg_speed']/10, 1) * 0.7 + x['availability'] * 0.3), reverse=True)
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
        
        # 综合评分排序：速度 * 0.7 + 可用率 * 0.2 + 频道数量 * 0.1（速度优先）
        deduplicated_files.sort(key=lambda x: (
            min(x['avg_speed']/10, 1) * 0.7 + 
            x['availability'] * 0.2 + 
            min(x['total_count']/500, 1) * 0.1
        ), reverse=True)
        
        # 第四步：频道排序和统一重命名
        self.logger.info("=" * 50)
        self.logger.info("第四步：频道排序和统一重命名")
        self.logger.info("=" * 50)
        
        renamed_files = []
        for i, file_info in enumerate(deduplicated_files):
            rank = i + 1
            source_ip = file_info['source_ip']
            channel_count = file_info['total_count']
            availability_percent = int(file_info['availability'] * 100)  # 转换为百分比整数
            
            # 直接使用源IP信息中的完整信息，避免重复识别
            # 从IP爬取历史记录中获取完整的IP信息
            full_info = self._get_full_info_from_ip_history(source_ip)
            if not full_info:
                # 如果历史记录中没有，尝试从文件名中提取信息
                full_info = self._extract_full_info_from_filename(file_info['file_name'])
            
            # 清理信息中的空格和特殊字符
            cleaned_info = full_info.replace(" ", "").replace("频道数：", "").replace("新上线", "")
            
            # 改进存活时间显示，避免总是显示"新上线"
            survival_time = self._get_survival_time_from_ip_info(source_ip)
            if not survival_time or survival_time == "新上线":
                survival_time = "未知存活"
            
            # 新文件名格式：[序号]_完整信息_频道数_存活时间_连通率
            new_name = f"[{rank:02d}]{cleaned_info}_{channel_count}ch_{survival_time}_{availability_percent}%.m3u"
            new_path = os.path.join(self.m3u_dir, new_name)
            old_path = file_info['file_path']
            
            try:
                # 首先对文件中的频道进行排序
                channels = self.parse_m3u_file(old_path)
                if channels:
                    # 保存排序后的频道到新文件
                    self.save_sorted_m3u_file(new_path, channels)
                    
                    # 如果新旧路径不同且不是同一个文件，删除旧文件
                    if new_path != old_path and os.path.exists(old_path):
                        os.remove(old_path)
                else:
                    # 如果解析失败，直接重命名
                    if new_path != old_path:
                        if os.path.exists(new_path):
                            os.remove(new_path)
                        os.rename(old_path, new_path)
                
                renamed_files.append({
                    'rank': rank,
                    'old_name': file_info['file_name'],
                    'new_name': new_name,
                    'source_ip': source_ip,
                    'availability': file_info['availability'],
                    'availability_percent': availability_percent,
                    'avg_speed': file_info['avg_speed'],
                    'channel_count': channel_count
                })
                
                self.logger.info(f"[{rank:02d}] {file_info['file_name']} -> {new_name} (可用率: {availability_percent}%, 速度: {file_info['avg_speed']:.2f})")
                
            except Exception as e:
                self.logger.error(f"处理文件 {file_info['file_name']} 失败: {e}")
        
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
    
    def _extract_location_from_filename(self, file_name: str) -> str:
        """从文件名中提取物理地址信息"""
        import re
        
        # 尝试从文件名中提取中文地区信息
        location_match = re.search(r'[\u4e00-\u9fff]+', file_name)
        if location_match:
            location = location_match.group(0)
            # 过滤掉运营商关键词
            operators = ['联通', '电信', '移动']
            for op in operators:
                location = location.replace(op, '')
            return location if location else "未知地区"
        
        return "未知地区"
    
    def _get_location_from_ip(self, ip_address: str) -> str:
        """通过IP地址查询地理位置信息"""
        import requests
        import json
        
        try:
            # 使用ip-api.com免费API查询IP地理位置
            response = requests.get(f'http://ip-api.com/json/{ip_address}?lang=zh-CN', timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'success':
                    # 返回城市信息，如果城市为空则返回地区
                    if data.get('city'):
                        return data['city']
                    elif data.get('regionName'):
                        return data['regionName']
                    elif data.get('country'):
                        return data['country']
        except:
            pass
        
        # 如果API查询失败，根据IP段判断大致地区
        try:
            ip_parts = ip_address.split('.')
            first_octet = int(ip_parts[0])
            
            # 根据IP地址段判断大致地区
            if first_octet == 115:
                return "浙江"
            elif first_octet == 113:
                return "陕西"
            elif first_octet == 124:
                return "浙江"
            elif first_octet == 221:
                return "山西"
            elif first_octet == 171:
                return "河南"
            elif 1 <= first_octet <= 126:
                return "电信"
            elif 128 <= first_octet <= 191:
                return "联通"
            elif 192 <= first_octet <= 223:
                return "移动"
        except:
            pass
        
        return "未知地区"
    
    def _get_location_from_ip(self, ip_address: str) -> str:
        """通过IP地址查询地理位置信息"""
        import requests
        import json
        
        try:
            # 使用ip-api.com免费API查询IP地理位置
            response = requests.get(f'http://ip-api.com/json/{ip_address}?lang=zh-CN', timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'success':
                    # 返回城市信息，如果城市为空则返回地区
                    if data.get('city'):
                        return data['city']
                    elif data.get('regionName'):
                        return data['regionName']
                    elif data.get('country'):
                        return data['country']
        except:
            pass
        
        # 如果API查询失败，根据IP段判断大致地区
        try:
            ip_parts = ip_address.split('.')
            first_octet = int(ip_parts[0])
            
            # 根据IP地址段判断大致地区
            if first_octet == 115:
                return "浙江"
            elif first_octet == 113:
                return "陕西"
            elif first_octet == 124:
                return "浙江"
            elif first_octet == 221:
                return "山西"
            elif first_octet == 171:
                return "河南"
            elif 1 <= first_octet <= 126:
                return "电信"
            elif 128 <= first_octet <= 191:
                return "联通"
            elif 192 <= first_octet <= 223:
                return "移动"
        except:
            pass
        
        return "未知地区"
    
    def _extract_operator_from_filename(self, file_name: str) -> str:
        """从文件名中提取运营商信息"""
        import re
        
        operators = ['联通', '电信', '移动']
        for op in operators:
            if op in file_name:
                return op
        
        return ""
    
    def _get_location_from_ip_info(self, ip_address: str) -> str:
        """从IP信息中获取物理地址信息
        
        Args:
            ip_address: IP地址
            
        Returns:
            物理地址信息，如果找不到则返回"未知地区"
        """
        try:
            # 首先尝试从IP地址查询地理位置
            location = self._get_location_from_ip(ip_address)
            if location != "未知地区":
                return location
            
            # 如果IP查询失败，尝试根据IP段判断大致地区
            try:
                ip_parts = ip_address.split('.')
                first_octet = int(ip_parts[0])
                second_octet = int(ip_parts[1])
                
                # 根据IP地址段判断大致地区
                if first_octet == 115:
                    return "浙江"
                elif first_octet == 116:
                    return "山西"
                elif first_octet == 117:
                    return "安徽"
                elif first_octet == 118:
                    return "福建"
                elif first_octet == 119:
                    return "吉林"
                elif first_octet == 120:
                    return "河北"
                elif first_octet == 121:
                    return "江苏"
                elif first_octet == 122:
                    return "山东"
                elif first_octet == 123:
                    return "广东"
                elif first_octet == 124:
                    return "辽宁"
                elif first_octet == 125:
                    return "黑龙江"
                elif first_octet == 171:
                    return "天津"
                elif first_octet == 175:
                    return "吉林"
                elif first_octet == 183:
                    return "广东"
                elif first_octet == 221:
                    return "北京"
                elif first_octet == 222:
                    return "吉林"
                elif first_octet == 113:
                    return "重庆"
                elif first_octet == 112:
                    return "上海"
                elif first_octet == 1:
                    return "北京"
                elif first_octet == 49:
                    return "浙江"
                elif first_octet == 221:
                    return "北京"
                elif first_octet == 222:
                    return "吉林"
                
                # 根据更详细的IP段判断
                if first_octet == 121 and second_octet == 224:
                    return "江苏南京"
                elif first_octet == 117 and second_octet == 69:
                    return "安徽合肥"
                elif first_octet == 49 and second_octet == 71:
                    return "浙江杭州"
                elif first_octet == 221 and second_octet == 15:
                    return "河南郑州"
                elif first_octet == 117 and second_octet == 91:
                    return "湖北武汉"
                elif first_octet == 119 and second_octet == 53:
                    return "吉林长春"
                elif first_octet == 175 and second_octet == 22:
                    return "吉林吉林"
                elif first_octet == 175 and second_octet == 16:
                    return "吉林吉林"
                elif first_octet == 222 and second_octet == 163:
                    return "吉林"
                elif first_octet == 222 and second_octet == 162:
                    return "吉林吉林"
                elif first_octet == 119 and second_octet == 51:
                    return "吉林长春"
                elif first_octet == 171 and second_octet == 124:
                    return "山西吕梁"
                elif first_octet == 116 and second_octet == 179:
                    return "山西大同"
                elif first_octet == 175 and second_octet == 150:
                    return "辽宁沈阳"
                elif first_octet == 113 and second_octet == 206:
                    return "重庆"
                elif first_octet == 1 and second_octet == 199:
                    return "北京"
                elif first_octet == 171 and second_octet == 120:
                    return "天津"
                elif first_octet == 183 and second_octet == 7:
                    return "广东广州"
                elif first_octet == 112 and second_octet == 67:
                    return "上海"
                
            except:
                pass
            
            return "未知地区"
            
        except Exception as e:
            self.logger.error(f"从IP信息获取物理地址失败: {e}")
            return "未知地区"
    
    def _get_survival_time_from_ip_info(self, ip_address: str) -> str:
        """从IP信息中获取存活时间信息
        
        Args:
            ip_address: IP地址
            
        Returns:
            存活时间信息，如果找不到则返回空字符串
        """
        try:
            # 尝试从IP爬取历史记录中获取存活时间
            ip_history_file = os.path.join("output", "data", "ip_crawl_history.json")
            if os.path.exists(ip_history_file):
                import json
                with open(ip_history_file, 'r', encoding='utf-8') as f:
                    ip_history = json.load(f)
                
                for ip_info in ip_history:
                    if ip_info.get('ip') == ip_address:
                        # 优先使用online_time计算存活时间
                        online_time = ip_info.get('online_time', '')
                        if online_time:
                            try:
                                from datetime import datetime
                                # 解析上线时间，格式如：2025-10-22 14:26
                                online_datetime = datetime.strptime(online_time, "%Y-%m-%d %H:%M")
                                current_datetime = datetime.now()
                                # 计算距今天数
                                days_diff = (current_datetime - online_datetime).days
                                if days_diff == 0:
                                    return "今日上线"
                                elif days_diff == 1:
                                    return "昨日上线"
                                else:
                                    return f"上线{days_diff}天"
                            except (ValueError, AttributeError):
                                # 如果解析失败，使用first_crawled作为备选
                                pass
                        
                        # 如果online_time不可用，使用first_crawled计算
                        first_crawled = ip_info.get('first_crawled', '')
                        if first_crawled:
                            try:
                                from datetime import datetime
                                # 解析首次爬取时间，格式如：2025-10-28 18:21:03
                                first_crawled_datetime = datetime.strptime(first_crawled, "%Y-%m-%d %H:%M:%S")
                                current_datetime = datetime.now()
                                # 计算距今天数
                                days_diff = (current_datetime - first_crawled_datetime).days
                                if days_diff == 0:
                                    return "今日上线"
                                elif days_diff == 1:
                                    return "昨日上线"
                                else:
                                    return f"上线{days_diff}天"
                            except (ValueError, AttributeError):
                                return "新上线"
                        
            return "新上线"
            
        except Exception as e:
            self.logger.error(f"从IP信息获取存活时间失败: {e}")
            return "新上线"
    
    def _standardize_channel_name(self, name: str) -> str:
        """标准化频道名称格式
        
        Args:
            name: 原始频道名称
            
        Returns:
            标准化后的频道名称
        """
        import re
        
        # 统一CCTV频道格式：CCTV1 -> CCTV-1, CCTV 1 -> CCTV-1
        name = re.sub(r'CCTV[- ]?(\d+)', r'CCTV-\1', name)
        
        # 统一卫视频道格式：湖南卫视 -> 湖南卫视
        name = re.sub(r'([\u4e00-\u9fff]+)卫视', r'\1卫视', name)
        
        # 去除多余空格
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def _natural_sort_key(self, channel: Dict) -> tuple:
        """增强的自然排序键函数，遵循既定排序规则
        
        排序优先级：
        1. 频道类型优先级：CCTV > 卫视 > 地方台 > 英文频道 > 中文频道 > 混合频道
        2. 自然数排序：1, 2, 10, 11
        3. 拼音排序：中文频道按拼音排序
        
        Args:
            channel: 频道信息字典
            
        Returns:
            排序键元组 (类型优先级, 拼音/字母键, 数字键)
        """
        import re
        import pypinyin
        
        name = channel['name']
        
        # 1. 确定频道类型优先级
        if name.startswith('CCTV'):
            priority = 1  # CCTV频道最高优先级
        elif '卫视' in name:
            priority = 2  # 卫视频道
        elif re.search(r'[\u4e00-\u9fff]', name) and not name.startswith('CCTV'):
            # 中文频道（非CCTV）
            if any(keyword in name for keyword in ['新闻', '综合', '公共', '都市', '影视']):
                priority = 3  # 地方台/专业频道
            else:
                priority = 5  # 普通中文频道
        elif re.match(r'^[A-Za-z]', name):
            priority = 4  # 英文频道
        else:
            priority = 6  # 混合频道
        
        # 2. 提取数字部分用于自然数排序
        numbers = re.findall(r'\d+', name)
        first_number = int(numbers[0]) if numbers else float('inf')
        
        # 3. 处理排序键
        if priority == 1:  # CCTV频道
            # 提取CCTV数字
            num_match = re.search(r'CCTV[- ]?(\d+)', name)
            if num_match:
                cctv_num = int(num_match.group(1))
                plus_suffix = 1 if '+' in name else 0  # 带+号的排在后面
                return (priority, cctv_num, plus_suffix, name)
            else:
                return (priority, float('inf'), 0, name)
                
        elif priority == 2:  # 卫视频道
            province = name.split('卫视')[0]
            pinyin_key = ''.join(pypinyin.lazy_pinyin(province))
            return (priority, pinyin_key, first_number, name)
            
        elif priority in [3, 5]:  # 中文频道
            pinyin_key = ''.join(pypinyin.lazy_pinyin(name))
            return (priority, pinyin_key, first_number, name)
            
        elif priority == 4:  # 英文频道
            # 英文频道按字母排序，数字按自然数排序
            def convert(text):
                return int(text) if text.isdigit() else text.lower()
            alpha_key = [convert(c) for c in re.split('([0-9]+)', name)]
            return (priority, alpha_key, first_number, name)
            
        else:  # 混合频道
            return (priority, name.lower(), first_number, name)
    
    def _get_full_info_from_ip_history(self, ip_address: str) -> str:
        """从IP爬取历史记录中获取完整的IP信息
        
        Args:
            ip_address: IP地址
            
        Returns:
            完整的IP信息字符串，如果找不到则返回空字符串
        """
        try:
            # 尝试从IP爬取历史记录中获取完整信息
            ip_history_file = os.path.join("output", "data", "ip_crawl_history.json")
            if os.path.exists(ip_history_file):
                import json
                with open(ip_history_file, 'r', encoding='utf-8') as f:
                    ip_history = json.load(f)
                
                for ip_info in ip_history:
                    if ip_info.get('ip') == ip_address:
                        # 优先使用location字段获取完整的地址和运营商信息
                        location = ip_info.get('location', '')
                        if location and location != "未知地区":
                            return location
                        
                        # 如果location信息不完整，使用分类信息
                        category = ip_info.get('category', '')
                        if category and category != "未知分类":
                            return category
                        
            return ""
            
        except Exception as e:
            self.logger.error(f"从IP历史记录获取完整信息失败: {e}")
            return ""
    
    def _extract_full_info_from_filename(self, file_name: str) -> str:
        """从文件名中提取完整的地址和运营商信息
        
        Args:
            file_name: 文件名
            
        Returns:
            完整的地址和运营商信息，如果提取失败则返回"未知地区未知运营商"
        """
        try:
            # 移除序号和文件扩展名
            import re
            
            # 移除 [序号] 前缀和 .m3u 后缀
            clean_name = re.sub(r'^\[\d+\]', '', file_name)
            clean_name = re.sub(r'\.m3u$', '', clean_name)
            
            # 移除频道数、存活时间、连通率等后缀信息
            clean_name = re.sub(r'\d+ch.*$', '', clean_name)
            
            # 如果文件名中还有有效信息，返回它
            if clean_name and clean_name.strip():
                return clean_name.strip()
            
            return "未知地区未知运营商"
            
        except Exception as e:
            self.logger.error(f"从文件名提取完整信息失败: {e}")
            return "未知地区未知运营商"
        

if __name__ == "__main__":
    # 示例用法
    optimizer = M3UOptimizer("output/m3u")
    optimizer.optimize_m3u_files()