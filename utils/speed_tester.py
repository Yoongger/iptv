"""播放源测速模块

实现功能：
1. 实时测量播放源延迟和缓冲速度
2. 记录历史测速数据
3. 提供动态排序评分
"""
import logging
import time
import requests
from typing import Dict, List
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

@dataclass
class SpeedMetrics:
    """测速指标数据结构"""
    latency: float = 0       # 平均延迟(ms)
    buffer_speed: float = 0 # 缓冲速度(KB/s)
    success_rate: float = 0 # 成功率(0-1)
    last_tested: float = 0  # 最后测试时间戳
    test_count: int = 0     # 测试次数

class SpeedTester:
    """播放源测速器"""
    
    def __init__(self, max_workers=10, timeout=5):
        self.max_workers = max_workers
        self.timeout = timeout
        self.metrics: Dict[str, SpeedMetrics] = {}
        self.logger = logging.getLogger("SpeedTester")
        
    def test_stream(self, url: str) -> SpeedMetrics:
        """测试单个流的性能指标（增强异常处理版）"""
        metrics = SpeedMetrics()
        start_time = time.time()
        session = requests.Session()
        
        try:
            # 测试连接延迟
            resp = session.head(url, timeout=self.timeout)
            resp.raise_for_status()
            metrics.latency = (time.time() - start_time) * 1000
            
            # 测试缓冲速度
            chunk_size = 1024 * 512  # 512KB
            with session.get(url, stream=True, timeout=self.timeout) as r:
                r.raise_for_status()
                start = time.time()
                downloaded = 0
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded >= chunk_size:  # 下载足够数据后停止
                            break
                duration = time.time() - start
                metrics.buffer_speed = downloaded / duration / 1024  # 转换为KB/s
            
            metrics.success_rate = 1
        except requests.exceptions.RequestException as e:
            metrics.success_rate = 0
            if hasattr(e, 'response') and e.response:
                metrics.latency = (time.time() - start_time) * 1000
        except Exception as e:
            metrics.success_rate = 0
        finally:
            session.close()
        
        metrics.last_tested = time.time()
        return metrics
    
    def update_metrics(self, url: str, new_metrics: SpeedMetrics):
        """更新测速指标(平滑处理)"""
        if url not in self.metrics:
            self.metrics[url] = new_metrics
            self.metrics[url].test_count = 1
            return
        
        # 加权平均(新数据权重0.7，历史数据0.3)
        old = self.metrics[url]
        old.latency = 0.3 * old.latency + 0.7 * new_metrics.latency
        old.buffer_speed = 0.3 * old.buffer_speed + 0.7 * new_metrics.buffer_speed
        old.success_rate = 0.3 * old.success_rate + 0.7 * new_metrics.success_rate
        old.last_tested = time.time()
        old.test_count += 1
    
    def calculate_score(self, url: str) -> float:
        """计算播放源的综合评分"""
        if url not in self.metrics:
            return 0  # 无数据时返回最低分
        
        m = self.metrics[url]
        
        # 加权评分公式 (增强版)
        latency_score = max(0, 1 - m.latency/1000)  # 延迟在1秒内得分为1-0
        buffer_score = min(1, m.buffer_speed/5000)  # 5000KB/s为满分
        stability_score = m.success_rate  # 成功率作为稳定性指标
        return 0.5 * latency_score + 0.3 * buffer_score + 0.2 * stability_score

    def enhanced_test(self, url: str) -> Dict[str, float]:
        """增强版流畅度测试"""
        metrics = self.test_stream(url)
        
        # 构建详细测试结果
        result = {
            'success': metrics.success_rate > 0.5,
            'latency': metrics.latency,
            'buffer_speed': metrics.buffer_speed,
            'stability': metrics.success_rate,
            'score': self.calculate_score(url)
        }
        
        # 额外测试：连续请求稳定性
        if result['success']:
            try:
                stability_scores = []
                for _ in range(3):
                    m = self.test_stream(url)
                    stability_scores.append(m.success_rate)
                result['stability'] = sum(stability_scores) / len(stability_scores)
            except:
                pass
                
        return result
    
    def batch_test(self, urls: List[str]) -> None:
        """批量测试多个URL（线程安全版）"""
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                for url in urls:
                    future = executor.submit(self.test_stream, url)
                    futures.append((url, future))
                
                for url, future in futures:
                    try:
                        metrics = future.result(timeout=self.timeout * 2)
                        self.update_metrics(url, metrics)
                    except Exception as e:
                        self.logger.error(f"测试URL {url} 时出错: {e}")
                        # 记录失败指标
                        self.update_metrics(url, SpeedMetrics(success_rate=0))
        except Exception as e:
            self.logger.error(f"批量测试出错: {e}")
        finally:
            if 'executor' in locals():
                executor.shutdown(wait=True)