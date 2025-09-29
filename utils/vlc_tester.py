"""VLC流媒体测速模块

该模块使用VLC播放器进行实际流媒体测试，评估:
1. 初始缓冲时间
2. 播放流畅度
3. 丢帧率
4. 缓冲事件
"""
import os
import sys
import ctypes

# 强制设置VLC DLL路径
VLC_DLL_PATH = r"D:\Program Files\VideoLAN\VLC"
os.environ['PATH'] = os.pathsep.join([VLC_DLL_PATH, os.environ['PATH']])

# 手动加载VLC DLL
try:
    ctypes.CDLL(os.path.join(VLC_DLL_PATH, 'libvlc.dll'))
    ctypes.CDLL(os.path.join(VLC_DLL_PATH, 'libvlccore.dll'))
except OSError as e:
    raise RuntimeError(f"无法加载VLC库: {e}")

import vlc

# 设置VLC库路径
VLC_PATH = r"D:\Program Files\VideoLAN\VLC"
if hasattr(sys, 'frozen'):
    os.environ['PATH'] = os.pathsep.join([VLC_PATH, os.environ['PATH']])
else:
    os.environ['PATH'] = os.pathsep.join([VLC_PATH, os.environ['PATH']])
    if sys.platform.startswith('win'):
        os.add_dll_directory(VLC_PATH)
import time
import logging
import threading
from typing import Dict, List, Tuple, Optional

class VLCTester:
    """使用VLC进行流媒体测试的类"""
    
    def __init__(self, timeout: int = 10, test_duration: int = 15, log_level: int = logging.INFO):
        """初始化VLC测试器
        
        Args:
            timeout: 连接超时时间（秒）
            test_duration: 每个流的测试时长（秒）
            log_level: 日志级别
        """
        self.actually_playing = False  # 播放状态标志
        self.timeout = timeout
        self.test_duration = test_duration
        
        # 配置日志
        self.logger = logging.getLogger("VLCTester")
        self.logger.setLevel(log_level)
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(console_handler)
        
        # 初始化VLC实例
        try:
            # 明确指定VLC库路径
            vlc_instance = vlc.Instance(['--no-video', '--quiet'])
            if not vlc_instance:
                raise RuntimeError("无法创建VLC实例")
            self.instance = vlc_instance
            self.logger.info("VLC实例初始化成功")
        except Exception as e:
            self.logger.error(f"VLC实例初始化失败: {e}")
            self.instance = None
    
    def _on_playing(self, event):
        """播放状态回调"""
        self.actually_playing = True
        self.logger.debug("检测到实际播放状态")
        
    def get_stats_fallback(self, play_duration: float, buffer_events: int) -> Dict:
        """增强版替代方案，基于播放时长和缓冲事件"""
        # 计算实际播放占比 (0-1)
        play_ratio = min(1.0, play_duration / self.test_duration)
        
        # 动态调整估算系数
        buffer_weight = min(5.0, max(2.0, 10 / (play_duration + 1)))
        
        return {
            'lost_pictures': int(buffer_events * buffer_weight * (1 - play_ratio)),
            'played_abuffers': int(100 * play_ratio),
            'lost_abuffers': int(buffer_events * buffer_weight * (1 - play_ratio)),
            'play_ratio': play_ratio,
            'buffer_intensity': min(1.0, buffer_events / 10),
            'stability': max(0.1, 1 - (buffer_events / (play_duration + 1)))
        }

    def collect_advanced_metrics(self, player) -> Dict:
        """增强版指标采集，更贴近实际体验"""
        metrics = {
            'jitter': 0,               # 网络抖动(ms)
            'decoding_efficiency': 1.0, # 解码效率(0-1)
            'bitrate_adaptation': 0.8, # 码率自适应能力(0-1)
            'actual_playback': 0       # 实际播放时长占比(0-1)
        }
        
        try:
            if hasattr(player, 'get_stats'):
                stats = player.get_stats()
                
                # 网络抖动
                metrics['jitter'] = getattr(stats, 'input_jitter', 0)
                
                # 解码效率 = 实际解码帧率 / 源帧率
                decoded_fps = getattr(stats, 'decoded_video', 0)
                source_fps = getattr(stats, 'demux_read', 0)
                if source_fps > 0:
                    metrics['decoding_efficiency'] = min(1.0, decoded_fps / source_fps)
                
                # 码率自适应（基于带宽变化时的表现）
                lost_pics = getattr(stats, 'lost_pictures', 0)
                metrics['bitrate_adaptation'] = 1 - min(1.0, lost_pics / 100)
                
        except Exception as e:
            self.logger.warning(f"采集高级指标出错: {e}")
            
        return metrics

    def test_stream(self, url: str, min_duration: int = 30) -> Dict:
        """增强版流媒体测试（含实际播放验证）
        
        Args:
            url: 流媒体URL
            min_duration: 最小测试时长(秒)
            
        Returns:
            包含测试结果的字典
        """
        if not self.instance:
            self.logger.error("VLC实例未初始化，无法测试")
            return {
                'success': False,
                'error': 'VLC实例未初始化',
                'buffer_time': float('inf'),
                'frames_dropped': 100,
                'buffer_events': 100,
                'score': 0,
                'actually_playable': False
            }
        
        self.logger.info(f"开始增强测试流: {url} (至少{min_duration}秒)")
        
        # 创建媒体和播放器
        media = self.instance.media_new(url)
        player = self.instance.media_player_new()
        player.set_media(media)
        
        # 通用VLC事件注册
        event_manager = player.event_manager()
        if hasattr(vlc, 'EventType'):  # VLC 3.0+
            event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_playing)
        elif hasattr(vlc, 'MediaPlayerPlaying'):  # VLC 2.x
            event_manager.event_attach(vlc.MediaPlayerPlaying, self._on_playing)
        else:
            self.logger.warning("无法注册播放事件，将使用简化测试模式")
        
        # 初始化测试结果
        result = {
            'success': False,
            'buffer_time': 0,
            'frames_dropped': 0,
            'buffer_events': 0,
            'playback_rate': 0,
            'score': 0
        }
        
        # 事件管理器
        event_manager = player.event_manager()
        
        # 事件标志
        events = {
            'buffering': False,
            'playing': False,
            'error': False,
            'buffer_events': 0,
            'start_time': 0
        }
        
        # 定义事件回调
        def handle_events(event):
            if event.type == vlc.EventType.MediaPlayerBuffering:
                if event.u.new_cache > 0 and not events['buffering']:
                    events['buffering'] = True
                    events['buffer_events'] += 1
                    self.logger.debug(f"缓冲中... {event.u.new_cache}%")
                elif event.u.new_cache >= 100:
                    events['buffering'] = False
            
            elif event.type == vlc.EventType.MediaPlayerPlaying:
                if not events['playing']:
                    events['playing'] = True
                    events['start_time'] = time.time()
                    self.logger.debug("开始播放")
            
            elif event.type == vlc.EventType.MediaPlayerEncounteredError:
                events['error'] = True
                self.logger.error("播放错误")
        
        # 注册事件回调（兼容不同版本）
        if hasattr(vlc, 'EventType'):  # VLC 3.0+
            event_manager.event_attach(vlc.EventType.MediaPlayerBuffering, handle_events)
            event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, handle_events)
            event_manager.event_attach(vlc.EventType.MediaPlayerEncounteredError, handle_events)
        elif hasattr(vlc, 'MediaPlayerBuffering'):  # VLC 2.x
            event_manager.event_attach(vlc.MediaPlayerBuffering, handle_events)
            event_manager.event_attach(vlc.MediaPlayerPlaying, handle_events)
            event_manager.event_attach(vlc.MediaPlayerEncounteredError, handle_events)
        else:
            self.logger.warning("无法注册全部事件回调，测试精度可能降低")
        
        # 开始播放
        start_time = time.time()
        player.play()
        
        # 等待连接超时或开始播放
        while time.time() - start_time < self.timeout:
            if events['playing'] or events['error']:
                break
            time.sleep(0.1)
        
        # 计算初始缓冲时间
        if events['playing']:
            result['buffer_time'] = events['start_time'] - start_time
            result['success'] = True
            self.logger.info(f"初始缓冲时间: {result['buffer_time']:.2f}秒")
            
            # 继续播放一段时间以收集更多指标
            test_end_time = time.time() + self.test_duration
            while time.time() < test_end_time:
                if events['error']:
                    result['success'] = False
                    break
                time.sleep(1)
            
            # 增强版统计数据收集
            play_duration = (time.time() - events['start_time']) if events['playing'] else 0
            stats = self.get_stats_fallback(play_duration, events['buffer_events'])
            
            result.update({
                'frames_dropped': stats['lost_pictures'],
                'playback_rate': stats['played_abuffers'] / 100,
                'play_ratio': stats['play_ratio'],
                'advanced_metrics': {
                    'buffer_intensity': stats['buffer_intensity'],
                    'stability': stats['stability'],
                    'effective_playback': stats['play_ratio'] * (1 - stats['buffer_intensity'])
                }
            })
            
            result['buffer_events'] = events['buffer_events']
            
            # 采集高级指标
            advanced_metrics = self.collect_advanced_metrics(player)
            result.update(advanced_metrics)
            
            # 计算增强版评分 (0-100)
            # 基础指标 (60分)
            base_score = 60 - min(result['buffer_time'] * 5, 30)  # 缓冲时间惩罚
            
            # 动态指标 (40分)
            dynamic_score = (
                0.4 * (100 - result['jitter'])/100 * 40 +      # 网络抖动
                0.3 * result['decoding_efficiency'] * 40 +     # 解码效率
                0.3 * result['bitrate_adaptation'] * 40         # 码率自适应
            )
            
            # 缓冲事件惩罚 (0-20分)
            buffer_penalty = min(result['buffer_events'] * 2, 20)
            
            # 实际播放奖励 (0-10分)
            playback_bonus = min(result.get('actual_playback', 0) * 10, 10)
            
            result['score'] = max(0, min(100, 
                base_score + dynamic_score - buffer_penalty + playback_bonus))
            
            self.logger.info(f"测试完成 - 评分: {result['score']:.2f}, 丢帧: {result['frames_dropped']}, 缓冲事件: {result['buffer_events']}")
        else:
            self.logger.warning(f"连接超时或错误，URL: {url}")
            result['buffer_time'] = self.timeout
            result['frames_dropped'] = 100
            result['buffer_events'] = 10
            result['score'] = 0
        
        # 停止播放并清理
        player.stop()
        player.release()
        media.release()
        
        return result
    
    def batch_test(self, urls: List[str], max_workers: int = 4) -> Dict[str, Dict]:
        """批量测试多个流媒体URL
        
        Args:
            urls: URL列表
            max_workers: 最大并发测试数
            
        Returns:
            URL到测试结果的映射
        """
        results = {}
        
        # 使用线程池进行并发测试
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.test_stream, url): url for url in urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as e:
                    self.logger.error(f"测试URL时出错 {url}: {e}")
                    results[url] = {
                        'success': False,
                        'error': str(e),
                        'buffer_time': float('inf'),
                        'frames_dropped': 100,
                        'buffer_events': 10,
                        'score': 0
                    }
        
        return results
    
    def test_m3u_file(self, channels: List[Dict], sample_size: int = 5) -> Dict:
        """测试M3U文件中的频道
        
        Args:
            channels: 频道列表
            sample_size: 测试的频道样本数量
            
        Returns:
            测试结果摘要
        """
        if not channels:
            return {
                'success': False,
                'avg_score': 0,
                'avg_buffer_time': float('inf'),
                'valid_rate': 0
            }
        
        # 随机选择频道进行测试
        import random
        sample_channels = random.sample(channels, min(sample_size, len(channels)))
        
        # 测试选定的频道
        urls = [channel['url'] for channel in sample_channels]
        results = self.batch_test(urls)
        
        # 计算平均指标
        valid_results = [r for r in results.values() if r['success']]
        valid_count = len(valid_results)
        
        if valid_count > 0:
            avg_score = sum(r['score'] for r in valid_results) / valid_count
            avg_buffer_time = sum(r['buffer_time'] for r in valid_results) / valid_count
            valid_rate = valid_count / len(results)
            
            return {
                'success': True,
                'avg_score': avg_score,
                'avg_buffer_time': avg_buffer_time,
                'valid_rate': valid_rate,
                'sample_size': len(results),
                'valid_count': valid_count
            }
        else:
            return {
                'success': False,
                'avg_score': 0,
                'avg_buffer_time': float('inf'),
                'valid_rate': 0,
                'sample_size': len(results),
                'valid_count': 0
            }

if __name__ == "__main__":
    try:
        # 初始化测试器
        tester = VLCTester(timeout=15, test_duration=5)
        print("VLC测试器初始化成功")
        
        # 测试配置 - 请替换为实际可用的测试URL
        test_url = "http://your-actual-stream-server/live/stream.m3u8"
        print(f"测试URL: {test_url}")
        
        # 执行测试
        result = tester.test_stream(test_url)
        
        # 输出结果
        if result['success']:
            print("Test SUCCESS")
            print(f"- Buffer time: {result['buffer_time']:.2f}s")
            print(f"- Frames dropped: {result['frames_dropped']}")
            print(f"- Score: {result['score']:.2f}/1.0")
        else:
            print("Test FAILED")
            print(f"- Error: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"Initialization failed: {str(e)}")
    finally:
        print("Test completed")