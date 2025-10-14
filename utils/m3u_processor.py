"""M3U文件处理模块"""
import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Tuple
from models.channel import Channel

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
                headers={'User-Agent': 'VLC/3.0.0'}
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
            if self.logger:
                self.logger.debug(f"频道 {channel.name} 检测失败: {e}")
        return float('inf')

    def _sort_channels_by_speed(self, channels: List[Channel]) -> List[Channel]:
        """按连接速度排序频道
        
        Args:
            channels: 频道列表
            
        Returns:
            排序后的频道列表
        """
        if self.logger:
            self.logger.info(f"正在测试 {len(channels)} 个频道的连接速度...")
        
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
        for source_ip, source_channels in grouped_channels.items():
            # 获取源信息
            source_info = source_channels[0] if source_channels else None
            category = source_info.category if source_info else "未知分类"
            channel_count = len(source_channels)
            
            # 创建文件名：源名称_频道数_存活时间_地理信息.m3u
            timestamp = time.strftime("%Y%m%d")
            location = self._extract_location(category)
            filename = f"{source_ip}_{channel_count}ch_{timestamp}_{location}.m3u"
            filepath = f"output/m3u/{filename}"
            
            # 确保目录存在
            os.makedirs("output/m3u", exist_ok=True)
            
            # 保存带测速排序的M3U文件
            sorted_channels = self._sort_channels_by_speed(source_channels)
            
            # 计算可用率（基于实际测速结果）
            valid_count = sum(1 for c in sorted_channels if self._test_channel_speed(c) < float('inf'))
            availability = valid_count / len(source_channels) if source_channels else 0
            
            # 只有当实际检测到可用频道时才显示可用率
            if valid_count > 0:
                availability_pct = int(availability * 100)
                filename = f"{source_ip}_{channel_count}ch_{timestamp}_{location}_可用{availability_pct}%.m3u"
            else:
                filename = f"{source_ip}_{channel_count}ch_{timestamp}_{location}_未检测.m3u"
                
            filepath = f"output/m3u/{filename}"
            
            # 保存文件
            self.save_to_m3u(sorted_channels, filepath)
            
        # 最后生成一个全局排序的文件
        self.save_global_sorted_m3u(channels)

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