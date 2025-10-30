"""M3U文件稳定性测试模块（简化版）

该模块专门用于测试多个M3U文件的稳定性，记录历史存活时长和稳定性指标，
最终输出最优选的单个M3U文件。

注意：此版本已移除数据库依赖，使用JSON文件存储数据。
"""
import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from utils.m3u_optimizer import M3UOptimizer


@dataclass
class StabilityMetrics:
    """稳定性指标数据结构"""
    file_path: str
    source_ip: str
    total_channels: int
    available_channels: int
    availability_rate: float
    avg_speed: float
    stability_score: float
    uptime_hours: float
    last_test_time: datetime
    test_count: int
    first_seen: datetime
    consecutive_failures: int
    success_rate: float


class M3UStabilityTester:
    """M3U文件稳定性测试器（无数据库版本）"""
    
    def __init__(self, m3u_dir: str, data_file: Optional[str] = None, test_interval_hours: int = 6):
        """初始化稳定性测试器
        
        Args:
            m3u_dir: M3U文件目录
            data_file: 数据文件路径，默认为m3u_dir/stability_data.json
            test_interval_hours: 测试间隔时间（小时）
        """
        self.m3u_dir = m3u_dir
        self.data_file = data_file if data_file is not None else os.path.join(m3u_dir, "stability_data.json")
        self.test_interval_hours = test_interval_hours
        
        # 创建目录
        os.makedirs(m3u_dir, exist_ok=True)
        
        # 配置日志
        self.logger = logging.getLogger("M3UStabilityTester")
        self.logger.setLevel(logging.INFO)
        
        # 初始化数据文件
        self._init_data_file()
        
        # 初始化优化器（用于测试文件可用性）
        self.optimizer = M3UOptimizer(m3u_dir, max_workers=5, timeout=10)
        
    def _init_data_file(self):
        """初始化数据文件"""
        if not os.path.exists(self.data_file):
            # 创建空的JSON数据文件
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({"stability_records": [], "file_metadata": {}}, f, ensure_ascii=False, indent=2)
    
    def _load_data(self):
        """加载数据文件"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            # 如果文件损坏或不存在，重新初始化
            self._init_data_file()
            return {"stability_records": [], "file_metadata": {}}
    
    def _save_data(self, data):
        """保存数据到文件"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _record_test_result(self, file_path: str, source_ip: str, 
                          total_channels: int, available_channels: int,
                          avg_speed: float, stability_score: float, 
                          success: bool):
        """记录单次测试结果到数据文件"""
        data = self._load_data()
        
        current_time = datetime.now().isoformat()
        availability_rate = available_channels / total_channels if total_channels > 0 else 0
        
        # 添加测试记录
        record = {
            "file_path": file_path,
            "source_ip": source_ip,
            "total_channels": total_channels,
            "available_channels": available_channels,
            "availability_rate": availability_rate,
            "avg_speed": avg_speed,
            "stability_score": stability_score,
            "test_time": current_time,
            "success": success
        }
        
        data["stability_records"].append(record)
        
        # 更新文件元数据
        if file_path not in data["file_metadata"]:
            data["file_metadata"][file_path] = {
                "first_seen": current_time,
                "total_tests": 0,
                "successful_tests": 0,
                "consecutive_failures": 0,
                "max_uptime_hours": 0
            }
        
        metadata = data["file_metadata"][file_path]
        metadata["total_tests"] += 1
        
        if success:
            metadata["successful_tests"] += 1
            metadata["consecutive_failures"] = 0
        else:
            metadata["consecutive_failures"] += 1
        
        # 计算最大在线时长
        if success:
            first_seen = datetime.fromisoformat(metadata["first_seen"])
            current_time_dt = datetime.fromisoformat(current_time)
            uptime_hours = (current_time_dt - first_seen).total_seconds() / 3600
            metadata["max_uptime_hours"] = max(metadata["max_uptime_hours"], uptime_hours)
        
        self._save_data(data)
    
    def _calculate_stability_score(self, file_path: str) -> float:
        """计算文件的稳定性评分（0-100）"""
        data = self._load_data()
        
        # 获取最近24小时的测试记录
        twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
        
        recent_records = []
        for record in data["stability_records"]:
            if record["file_path"] == file_path:
                test_time = datetime.fromisoformat(record["test_time"])
                if test_time >= twenty_four_hours_ago:
                    recent_records.append(record)
        
        if not recent_records:
            return 50.0  # 默认评分
        
        # 计算成功率
        successful_tests = sum(1 for r in recent_records if r["success"])
        success_rate = successful_tests / len(recent_records)
        
        # 计算平均可用率
        avg_availability = sum(r["availability_rate"] for r in recent_records) / len(recent_records)
        
        # 计算稳定性评分（成功率权重0.6，可用率权重0.4）
        stability_score = (success_rate * 0.6 + avg_availability * 0.4) * 100
        
        return min(stability_score, 100)
    
    def _get_file_uptime(self, file_path: str) -> float:
        """计算文件的总在线时长（小时）"""
        data = self._load_data()
        
        if file_path in data["file_metadata"]:
            return data["file_metadata"][file_path].get("max_uptime_hours", 0)
        return 0
    
    def test_m3u_file(self, file_path: str) -> Optional[StabilityMetrics]:
        """测试单个M3U文件的稳定性
        
        Args:
            file_path: M3U文件路径
            
        Returns:
            稳定性指标，如果测试失败返回None
        """
        try:
            # 解析M3U文件
            channels = self.optimizer.parse_m3u_file(file_path)
            if not channels:
                self.logger.warning(f"文件 {file_path} 没有频道数据")
                return None
            
            # 提取源IP（从文件名中提取）
            file_name = os.path.basename(file_path)
            source_ip = self.optimizer._extract_source_ip(file_path, file_name)
            
            # 测试文件可用性
            test_result = self.optimizer.test_m3u_file(file_path)
            if not test_result:
                self.logger.warning(f"文件 {file_path} 测试失败")
                return None
            
            # 解析测试结果（返回的是元组）
            is_valid, avg_score, available_count, total_count = test_result
            availability_rate = available_count / total_count if total_count > 0 else 0
            
            # 计算稳定性评分
            stability_score = self._calculate_stability_score(file_path)
            
            # 计算在线时长
            uptime_hours = self._get_file_uptime(file_path)
            
            # 获取文件元数据
            data = self._load_data()
            metadata = data["file_metadata"].get(file_path, {})
            
            # 记录测试结果
            self._record_test_result(
                file_path, source_ip, 
                total_count, available_count,
                avg_score, stability_score, 
                is_valid
            )
            
            # 构建稳定性指标
            metrics = StabilityMetrics(
                file_path=file_path,
                source_ip=source_ip,
                total_channels=total_count,
                available_channels=available_count,
                availability_rate=availability_rate,
                avg_speed=avg_score,
                stability_score=stability_score,
                uptime_hours=uptime_hours,
                last_test_time=datetime.now(),
                test_count=metadata.get('total_tests', 1),
                first_seen=datetime.fromisoformat(metadata.get('first_seen', datetime.now().isoformat())),
                consecutive_failures=metadata.get('consecutive_failures', 0),
                success_rate=metadata.get('successful_tests', 0) / max(metadata.get('total_tests', 1), 1)
            )
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"测试文件 {file_path} 时出错: {e}")
            return None
    
    def run_stability_test(self):
        """运行稳定性测试"""

        
        # 获取所有M3U文件
        m3u_files = [os.path.join(self.m3u_dir, f) for f in os.listdir(self.m3u_dir) 
                     if f.endswith('.m3u') and os.path.isfile(os.path.join(self.m3u_dir, f))]
        
        if not m3u_files:
            self.logger.warning("未找到任何M3U文件")
            return
        

        
        # 测试每个文件
        valid_files = []
        for file_path in m3u_files:
            try:
                metrics = self.test_m3u_file(file_path)
                if metrics and metrics.availability_rate > 0:
                    valid_files.append(metrics)

                else:
                    self.logger.warning(f"文件 {os.path.basename(file_path)} 测试失败或不可用")
            except Exception as e:
                self.logger.error(f"测试文件 {os.path.basename(file_path)} 时出错: {e}")
        
        if not valid_files:
            self.logger.warning("稳定性测试未找到可用文件")
            return
        
        # 按稳定性评分排序
        valid_files.sort(key=lambda x: x.stability_score, reverse=True)
        

        
        # 输出最优文件
        best_file = valid_files[0]
        self.logger.info(f"最优文件: {os.path.basename(best_file.file_path)} - "
                       f"综合评分: {best_file.stability_score:.2f}")
        
        return valid_files
    
    def test_all_files(self):
        """测试所有文件（兼容main.py的调用）"""
        return self.run_stability_test()
    
    def select_and_save_best_file(self, results, best_filename):
        """选择并保存最优文件（兼容main.py的调用）"""
        if not results:
            return None
        
        # 按稳定性评分排序
        results.sort(key=lambda x: x.stability_score, reverse=True)
        best_file = results[0]
        
        # 复制最优文件到指定文件名
        try:
            import shutil
            best_file_path = os.path.join(self.m3u_dir, best_filename)
            shutil.copy2(best_file.file_path, best_file_path)
            self.logger.info(f"最优文件已保存为: {best_filename}")
            return best_file
        except Exception as e:
            self.logger.error(f"保存最优文件失败: {e}")
            return None


if __name__ == "__main__":
    # 测试代码
    tester = M3UStabilityTester("output/m3u")
    tester.run_stability_test()