"""VLC流媒体测速模块 - 简化版本

该模块使用VLC播放器进行实际流媒体测试，评估:
1. 初始缓冲时间
2. 播放流畅度
3. 丢帧率
4. 缓冲事件
"""
import os
import sys
import ctypes
import time
import logging
import threading
import signal
from typing import Dict, List, Tuple, Optional

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

class VLCTester:
    """使用VLC进行流媒体测试的类 - 简化版本"""
    
    def __init__(self, timeout: int = 3, test_duration: int = 5, log_level: int = logging.INFO):
        """初始化VLC测试器
        
        Args:
            timeout: 连接超时时间（秒）
            test_duration: 每个流的测试时长（秒）
            log_level: 日志级别
        """
        self.timeout = timeout
        self.test_duration = test_duration
        self.force_timeout = 3  # 强制超时3秒
        
        # 配置日志
        self.logger = logging.getLogger("VLCTester")
        self.logger.setLevel(log_level)
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(console_handler)
        
        self.logger.info("VLC测试器已初始化")

    def _on_playing(self, event):
        """播放状态回调"""
        self.logger.debug("检测到播放状态")
        
    def _on_error(self, event):
        """错误状态回调"""
        self.logger.error("播放错误")
        
    def _on_end_reached(self, event):
        """结束状态回调"""
        self.logger.debug("播放结束")

    def test_stream(self, url: str) -> Dict:
        """测试单个流的可用性和质量 - 简化版本
        
        Args:
            url: 流地址
            
        Returns:
            包含测试结果的字典
        """
        self.logger.info(f"开始增强测试流: {url} (至少{self.test_duration}秒)")
        
        start_time = time.time()
        result = {
            "available": False,
            "score": 0.0,
            "buffer_time": float('inf'),
            "stability": 0.0,
            "error": None,
            "test_duration": 0.0
        }
        
        player = None
        media = None
        instance = None
        
        try:
            # 创建VLC实例 - 使用最简配置
            args = [
                '--intf', 'dummy',
                '--no-video-title-show',
                '--no-audio',
                '--network-caching=300',  # 极短缓存时间
                '--live-caching=300',
                '--file-caching=300',
                '--quiet',
                '--no-interact'
            ]
            
            instance = vlc.Instance(args)
            if not instance:
                result["error"] = "无法创建VLC实例"
                return result
                
            player = instance.media_player_new()
            if not player:
                result["error"] = "无法创建播放器"
                return result
            
            # 设置事件管理器
            try:
                event_manager = player.event_manager()
                event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_playing)
                event_manager.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)
                event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end_reached)
            except:
                self.logger.warning("无法设置事件管理器")
            
            # 创建媒体对象
            media = instance.media_new(url)
            if not media:
                result["error"] = "无法创建媒体对象"
                return result
                
            player.set_media(media)
            
            # 开始播放
            ret = player.play()
            if ret != 0:
                result["error"] = f"播放失败，返回码: {ret}"
                return result
            
            # 等待连接建立 - 使用极短超时
            connection_timeout = min(self.force_timeout, self.timeout)
            connection_start = time.time()
            
            while time.time() - connection_start < connection_timeout:
                # 强制超时检查
                if time.time() - start_time > self.force_timeout:
                    self.logger.warning(f"强制超时退出: {url}")
                    result["error"] = "强制超时"
                    return result
                
                state = player.get_state()
                if state == vlc.State.Playing:
                    break
                elif state == vlc.State.Error:
                    result["error"] = "播放错误"
                    self.logger.error("播放错误")
                    return result
                elif state == vlc.State.Ended:
                    result["error"] = "流结束"
                    return result
                    
                time.sleep(0.05)  # 非常频繁的检查
            
            # 再次检查强制超时
            if time.time() - start_time > self.force_timeout:
                self.logger.warning(f"强制超时退出: {url}")
                result["error"] = "强制超时"
                return result
            
            # 检查是否成功开始播放
            if player.get_state() != vlc.State.Playing:
                result["error"] = "连接超时"
                self.logger.warning(f"连接超时或错误，URL: {url}")
                return result
            
            # 记录缓冲时间
            buffer_time = time.time() - start_time
            result["buffer_time"] = buffer_time
            
            # 测试播放稳定性 - 极短测试时间
            test_duration = min(2, self.test_duration)  # 最多测试2秒
            test_start = time.time()
            stable_count = 0
            total_checks = 0
            
            while time.time() - test_start < test_duration:
                # 强制超时检查
                if time.time() - start_time > self.force_timeout:
                    self.logger.warning(f"强制超时退出: {url}")
                    break
                    
                state = player.get_state()
                if state == vlc.State.Playing:
                    stable_count += 1
                elif state == vlc.State.Error:
                    break
                    
                total_checks += 1
                time.sleep(0.1)  # 频繁检查
            
            # 计算稳定性
            if total_checks > 0:
                stability = stable_count / total_checks
                result["stability"] = stability
                
                # 计算综合评分 - 降低要求
                if stability > 0.5:  # 50%以上时间稳定播放
                    result["available"] = True
                    # 评分考虑缓冲时间和稳定性
                    score = stability * 0.7  # 稳定性权重70%
                    if buffer_time < 1:
                        score += 0.3  # 快速缓冲加分30%
                    elif buffer_time < 2:
                        score += 0.2  # 中等缓冲加分20%
                    elif buffer_time < 3:
                        score += 0.1  # 慢速缓冲加分10%
                    
                    result["score"] = min(score, 1.0)
            
            result["test_duration"] = time.time() - start_time
            
        except Exception as e:
            result["error"] = str(e)
            self.logger.error(f"测试异常: {e}")
            
        finally:
            # 强制清理资源
            try:
                if player:
                    try:
                        player.stop()
                        time.sleep(0.05)  # 短暂等待
                    except:
                        pass
                    try:
                        player.release()
                    except:
                        pass
                        
                if media:
                    try:
                        media.release()
                    except:
                        pass
                        
                if instance:
                    try:
                        instance.release()
                    except:
                        pass
            except:
                pass
        
        return result

    def batch_test(self, urls: List[str], max_workers: int = 2) -> Dict[str, Dict]:
        """批量测试多个流媒体URL - 减少并发数
        
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
                    results[url] = future.result(timeout=self.force_timeout + 1)  # 额外超时保护
                except Exception as e:
                    self.logger.error(f"测试URL时出错 {url}: {e}")
                    results[url] = {
                        'available': False,
                        'error': str(e),
                        'buffer_time': float('inf'),
                        'stability': 0.0,
                        'score': 0.0
                    }
        
        return results

if __name__ == "__main__":
    try:
        # 初始化测试器
        tester = VLCTester(timeout=3, test_duration=2)
        print("VLC测试器初始化成功")
        
        # 测试配置 - 请替换为实际可用的测试URL
        test_url = "http://your-actual-stream-server/live/stream.m3u8"
        print(f"测试URL: {test_url}")
        
        # 执行测试
        result = tester.test_stream(test_url)
        
        # 输出结果
        if result['available']:
            print("Test SUCCESS")
            print(f"- Buffer time: {result['buffer_time']:.2f}s")
            print(f"- Stability: {result['stability']:.2f}")
            print(f"- Score: {result['score']:.2f}")
        else:
            print("Test FAILED")
            print(f"- Error: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"Initialization failed: {str(e)}")
    finally:
        print("Test completed")