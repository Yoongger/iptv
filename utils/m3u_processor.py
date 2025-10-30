"""M3U文件处理模块"""
import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from typing import List
from models.channel import Channel
from config.constants import USER_AGENT, OUTPUT_M3U_DIR, OUTPUT_M3U_DIR as M3U_DIR

class M3UProcessor:
    """M3U文件处理类"""
    
    def __init__(self, logger=None, max_workers=5):
        """初始化M3U处理器
        
        Args:
            logger: 日志记录器
            max_workers: 最大并发测速线程数
        """
        self.logger = logger
        self.max_workers = max_workers
    
    def _test_channel_speed(self, channel: Channel) -> float:
        """测试单个频道连接速度和可用性
        
        Args:
            channel: 频道对象
            
        Returns:
            连接时间(毫秒)，失败返回无穷大
        """
        try:
            start_time = time.time()
            response = requests.get(
                channel.url,
                timeout=5,
                stream=True,
                headers={'User-Agent': USER_AGENT}
            )
            
            # 更严格的可用性检测
            if response.status_code == 200:
                # 检查响应头，确保是有效的流媒体
                content_type = response.headers.get('content-type', '').lower()
                is_stream = any(x in content_type for x in ['video', 'audio', 'application/x-mpegurl'])
                
                # 尝试读取少量数据验证流是否有效
                if is_stream:
                    # 对于流媒体，尝试读取前1KB数据
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:  # 成功读取到数据
                            return (time.time() - start_time) * 1000
                        break
                else:
                    # 对于非流媒体，直接返回成功
                    return (time.time() - start_time) * 1000
                    
        except Exception as e:
            pass
        
        return float('inf')

    def _sort_channels_by_speed(self, channels: List[Channel]) -> List[Channel]:
        """按连接速度排序频道
        
        Args:
            channels: 频道列表
            
        Returns:
            排序后的频道列表
        """
        
        # 使用线程池并发测速
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            speeds = list(executor.map(self._test_channel_speed, channels))
        
        # 按速度排序(从快到慢)
        sorted_channels = [ch for _, ch in sorted(zip(speeds, channels), key=lambda x: x[0])]
        return sorted_channels

    def save_to_m3u(self, channels: List[Channel], filename: str):
        """保存为M3U格式文件
        
        Args:
            channels: 频道列表
            filename: 输出文件名
        """
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for channel in channels:
                f.write(f'#EXTINF:-1,{channel.name}\n')
                f.write(f'{channel.url}\n')
        
        if self.logger:
            self.logger.info(f"M3U文件已保存: {filename}")

    def save_to_m3u_with_speed_test(self, channels: List[Channel], filename: str):
        """保存为M3U格式文件(带测速排序)
        
        Args:
            channels: 频道列表
            filename: 输出文件名
        """
        # 先测速排序
        sorted_channels = self._sort_channels_by_speed(channels)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for channel in sorted_channels:
                f.write(f'#EXTINF:-1,{channel.name}\n')
                f.write(f'{channel.url}\n')
        
        if self.logger:
            valid_count = sum(1 for c in sorted_channels if c.url)
            self.logger.info(f"已保存测速排序M3U文件: {filename} (有效频道: {valid_count}/{len(channels)})")

    def save_global_sorted_m3u(self, channels: List[Channel], filename: str = "output/m3u/all_channels_sorted.m3u"):
        """保存全局排序的M3U文件
        
        Args:
            channels: 所有频道列表
            filename: 输出文件名
        """
        if self.logger:
            self.logger.info(f"开始全局测速排序 {len(channels)} 个频道...")
            
        # 过滤有效频道
        valid_channels = [ch for ch in channels if ch.url]
        
        # 测速排序
        sorted_channels = self._sort_channels_by_speed(valid_channels)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # 保存排序后的文件
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for i, channel in enumerate(sorted_channels):
                # 添加速度排名到频道名称
                ranked_name = f"[{i+1}] {channel.name}"
                f.write(f'#EXTINF:-1,{ranked_name}\n')
                f.write(f'{channel.url}\n')
        
        if self.logger:
            self.logger.info(f"已保存全局排序M3U文件: {filename} (共 {len(sorted_channels)} 个频道)")
        
        return sorted_channels
    
    def save_individual_m3u_files(self, channels: List[Channel]):
        """为每个视频源IP创建单独的M3U文件(带测速排序)
        
        Args:
            channels: 频道列表
        """
        # 按源IP分组
        grouped_channels = {}
        for channel in channels:
            source_ip = channel.source_ip
            if source_ip not in grouped_channels:
                grouped_channels[source_ip] = []
            grouped_channels[source_ip].append(channel)
        
        # 为每个源创建M3U文件
        file_counter = 1
        for source_ip, source_channels in grouped_channels.items():
            # 获取源信息
            source_info = source_channels[0] if source_channels else None
            channel_count = len(source_channels)
            
            # 优先使用Channel对象中的完整位置信息
            if source_info and getattr(source_info, 'location', None):
                full_info = source_info.location
                online_time = getattr(source_info, 'online_time', '')
            else:
                # 如果Channel对象中没有位置信息，尝试从IP历史记录获取
                history_data = self._get_data_from_history(source_ip)
                if history_data and history_data.get('location'):
                    full_info = history_data.get('location')
                    online_time = history_data.get('online_time', '')
                else:
                    # 如果都没有位置信息，使用分类信息
                    category = getattr(source_info, 'category', '未知分类')
                    online_time = getattr(source_info, 'online_time', '')
                    full_info = category
            
            # 如果online_time为空，再次尝试从历史记录获取
            if not online_time:
                history_data = self._get_data_from_history(source_ip)
                if history_data and history_data.get('online_time'):
                    online_time = history_data.get('online_time')
            
            # 清理信息中的空格和特殊字符
            cleaned_info = full_info.replace(" ", "_").replace("频道数：", "").replace("新上线", "")
            
            # 格式化上线时间 - 计算距今天数
            formatted_survival = "新上线"  # 默认值
            if online_time:
                try:
                    from datetime import datetime
                    # 解析上线时间，格式如：2025-10-22 14:26
                    online_datetime = datetime.strptime(online_time, "%Y-%m-%d %H:%M")
                    current_datetime = datetime.now()
                    # 计算距今天数
                    days_diff = (current_datetime - online_datetime).days
                    if days_diff == 0:
                        formatted_survival = "今日上线"
                    elif days_diff == 1:
                        formatted_survival = "昨日上线"
                    else:
                        formatted_survival = f"上线{days_diff}天"
                except (ValueError, AttributeError):
                    # 如果解析失败，保持默认值
                    pass
            
            # 保存带测速排序的M3U文件
            sorted_channels = self._sort_channels_by_speed(source_channels)
            
            # 计算可用率（并发测速以提升速度）
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                test_results = list(executor.map(self._test_channel_speed, sorted_channels))
            valid_count = sum(1 for result in test_results if result < float('inf'))
            availability = valid_count / len(source_channels) if source_channels else 0
            availability_pct = int(availability * 100)
            
            # 创建文件名：完整信息_IP地址_频道数_上线时间/存活时间_连通率（不带序号）
            filename = f"{cleaned_info}_{source_ip}_{channel_count}ch_{formatted_survival}_{availability_pct}%.m3u"
            
            filepath = f"{M3U_DIR}/{filename}"
            
            # 确保目录存在
            os.makedirs(M3U_DIR, exist_ok=True)
            
            # 保存文件
            self.save_to_m3u(sorted_channels, filepath)
            
            file_counter += 1
            
        # 不再生成全局排序的文件，只保存单个视频源的M3U文件

    def _extract_location(self, category: str) -> str:
        """从分类中提取地理信息
        
        Args:
            category: 分类字符串
            
        Returns:
            地理信息
        """
        location_mapping = {
            'Hotel IPTV': '酒店',
            'Proxy IPTV': '代理',
            'Multicast IP': '组播',
            '联通': '联通',
            '电信': '电信',
            '移动': '移动'
        }
        
        for key, value in location_mapping.items():
            if key in category:
                return value
        return '未知地区'
    
    def _extract_operator(self, category: str) -> str:
        """从分类中提取运营商信息
        
        Args:
            category: 分类字符串
            
        Returns:
            运营商信息
        """
        operator_mapping = {
            '联通': '联通',
            '电信': '电信',
            '移动': '移动',
            'China Unicom': '联通',
            'China Telecom': '电信',
            'China Mobile': '移动'
        }
        
        for key, value in operator_mapping.items():
            if key in category:
                return value
        return '未知运营商'
    
    def _extract_operator_from_location(self, location: str) -> str:
        """从位置信息中提取运营商信息
        
        Args:
            location: 位置字符串
            
        Returns:
            运营商信息
        """
        operator_mapping = {
            '联通': '联通',
            '电信': '电信',
            '移动': '移动',
            '广电': '广电'
        }
        
        if location:
            for key, value in operator_mapping.items():
                if key in location:
                    return value
        return '未知运营商'
    
    def _get_data_from_history(self, ip_address: str) -> dict:
        """从ip_crawl_history.json文件中获取IP相关信息
        
        Args:
            ip_address: IP地址
            
        Returns:
            包含location、online_time等信息的字典，如果找不到则返回空字典
        """
        try:
            import json
            import os
            
            # 使用绝对路径确保能找到文件
            ip_history_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "data", "ip_crawl_history.json")
            
            if os.path.exists(ip_history_file):
                with open(ip_history_file, 'r', encoding='utf-8') as f:
                    ip_history = json.load(f)
                
                # 查找匹配的IP记录
                for ip_info in ip_history:
                    if ip_info.get('ip') == ip_address:
                        # 返回所有相关数据
                        return {
                            'location': ip_info.get('location', ''),
                            'online_time': ip_info.get('online_time', ''),
                            'category': ip_info.get('category', ''),
                            'channel_count': ip_info.get('channel_count', 0)
                        }
                
            return {}
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"从历史记录获取数据失败: {e}")
            return {}