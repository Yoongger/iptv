"""M3U文件稳定性测试模块

该模块专门用于测试多个M3U文件的稳定性，记录历史存活时长和稳定性指标，
最终输出最优选的单个M3U文件。
"""
import os
import json
import time
import logging
import sqlite3
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path
from utils.m3u_optimizer import M3UOptimizer
from utils.speed_tester import SpeedTester


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
    """M3U文件稳定性测试器"""
    
    def __init__(self, m3u_dir: str, db_path: Optional[str] = None, test_interval_hours: int = 6):
        """初始化稳定性测试器
        
        Args:
            m3u_dir: M3U文件目录
            db_path: 数据库文件路径，默认为m3u_dir/stability.db
            test_interval_hours: 测试间隔时间（小时）
        """
        self.m3u_dir = m3u_dir
        self.db_path = db_path if db_path is not None else os.path.join(m3u_dir, "stability.db")
        self.test_interval_hours = test_interval_hours
        
        # 创建目录
        os.makedirs(m3u_dir, exist_ok=True)
        
        # 配置日志
        self.logger = logging.getLogger("M3UStabilityTester")
        self.logger.setLevel(logging.INFO)
        
        # 初始化数据库
        self._init_database()
        
        # 初始化优化器（用于测试文件可用性）
        self.optimizer = M3UOptimizer(m3u_dir, max_workers=5, timeout=10)
        
    def _init_database(self):
        """初始化SQLite数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建稳定性记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stability_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                source_ip TEXT NOT NULL,
                total_channels INTEGER,
                available_channels INTEGER,
                availability_rate REAL,
                avg_speed REAL,
                stability_score REAL,
                test_time DATETIME NOT NULL,
                success BOOLEAN NOT NULL
            )
        ''')
        
        # 创建文件元数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_metadata (
                file_path TEXT PRIMARY KEY,
                source_ip TEXT,
                first_seen DATETIME,
                last_seen DATETIME,
                total_tests INTEGER DEFAULT 0,
                successful_tests INTEGER DEFAULT 0,
                consecutive_failures INTEGER DEFAULT 0,
                max_uptime_hours REAL DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
        
        self.logger.info(f"数据库初始化完成: {self.db_path}")
    
    def _record_test_result(self, file_path: str, source_ip: str, 
                          total_channels: int, available_channels: int,
                          avg_speed: float, stability_score: float, 
                          success: bool):
        """记录单次测试结果到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        current_time = datetime.now()
        availability_rate = available_channels / total_channels if total_channels > 0 else 0
        
        # 插入测试记录
        cursor.execute('''
            INSERT INTO stability_records 
            (file_path, source_ip, total_channels, available_channels, 
             availability_rate, avg_speed, stability_score, test_time, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (file_path, source_ip, total_channels, available_channels,
              availability_rate, avg_speed, stability_score, current_time, success))
        
        # 更新文件元数据
        cursor.execute('''
            INSERT OR REPLACE INTO file_metadata 
            (file_path, source_ip, first_seen, last_seen, total_tests, 
             successful_tests, consecutive_failures, max_uptime_hours)
            VALUES (?, ?, COALESCE((SELECT first_seen FROM file_metadata WHERE file_path = ?), ?), 
                    ?, COALESCE((SELECT total_tests FROM file_metadata WHERE file_path = ?), 0) + 1,
                    COALESCE((SELECT successful_tests FROM file_metadata WHERE file_path = ?), 0) + ?,
                    CASE WHEN ? = 0 THEN COALESCE((SELECT consecutive_failures FROM file_metadata WHERE file_path = ?), 0) + 1 ELSE 0 END,
                    COALESCE((SELECT max_uptime_hours FROM file_metadata WHERE file_path = ?), 0))
        ''', (file_path, source_ip, file_path, current_time, current_time, 
              file_path, file_path, 1 if success else 0, 
              1 if success else 0, file_path, file_path))
        
        # 更新最大在线时长
        if success:
            cursor.execute('''
                UPDATE file_metadata 
                SET max_uptime_hours = (
                    SELECT MAX(julianday(last_seen) - julianday(first_seen)) * 24 
                    FROM stability_records 
                    WHERE file_path = ? AND success = 1
                    GROUP BY file_path
                )
                WHERE file_path = ?
            ''', (file_path, file_path))
        
        conn.commit()
        conn.close()
    
    def _calculate_stability_score(self, file_path: str) -> float:
        """计算文件的稳定性评分（0-100）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取最近24小时的测试记录
        twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
        
        cursor.execute('''
            SELECT COUNT(*) as total_tests,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_tests,
                   AVG(availability_rate) as avg_availability,
                   AVG(avg_speed) as avg_speed
            FROM stability_records 
            WHERE file_path = ? AND test_time > ?
        ''', (file_path, twenty_four_hours_ago))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result or result[0] == 0:
            return 0.0
        
        total_tests, successful_tests, avg_availability, avg_speed = result
        
        # 计算稳定性评分公式：
        # 成功率权重: 40%
        # 可用率权重: 30%
        # 速度权重: 20%
        # 测试次数权重: 10%
        
        success_rate = successful_tests / total_tests if total_tests > 0 else 0
        availability_score = avg_availability if avg_availability else 0
        speed_score = min(avg_speed / 100, 1) if avg_speed else 0  # 速度在100ms内得满分
        test_count_score = min(total_tests / 10, 1)  # 测试次数越多越可靠
        
        stability_score = (
            success_rate * 0.4 +
            availability_score * 0.3 +
            speed_score * 0.2 +
            test_count_score * 0.1
        ) * 100
        
        return min(stability_score, 100)
    
    def _get_file_uptime(self, file_path: str) -> float:
        """计算文件的总在线时长（小时）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT MAX(max_uptime_hours) 
            FROM file_metadata 
            WHERE file_path = ?
        ''', (file_path,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] else 0.0
    
    def test_single_file(self, file_path: str) -> Optional[StabilityMetrics]:
        """测试单个M3U文件的稳定性"""
        try:
            self.logger.info(f"开始测试文件: {os.path.basename(file_path)}")
            
            # 使用优化器测试文件可用性
            is_valid, avg_speed, available_channels, total_channels = self.optimizer.test_m3u_file(file_path)
            
            # 提取源IP
            source_ip = self.optimizer._extract_source_ip(file_path, os.path.basename(file_path))
            
            # 计算稳定性评分
            stability_score = self._calculate_stability_score(file_path)
            
            # 获取在线时长
            uptime_hours = self._get_file_uptime(file_path)
            
            # 记录测试结果
            self._record_test_result(
                file_path, source_ip, total_channels, available_channels,
                avg_speed, stability_score, is_valid
            )
            
            # 构建稳定性指标
            metrics = StabilityMetrics(
                file_path=file_path,
                source_ip=source_ip,
                total_channels=total_channels,
                available_channels=available_channels,
                availability_rate=available_channels / total_channels if total_channels > 0 else 0,
                avg_speed=avg_speed,
                stability_score=stability_score,
                uptime_hours=uptime_hours,
                last_test_time=datetime.now(),
                test_count=0,  # 这个从数据库查询
                first_seen=datetime.now(),  # 这个从数据库查询
                consecutive_failures=0,  # 这个从数据库查询
                success_rate=1.0 if is_valid else 0.0
            )
            
            # 从数据库获取更准确的历史数据
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT first_seen, total_tests, successful_tests, consecutive_failures
                FROM file_metadata WHERE file_path = ?
            ''', (file_path,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                first_seen_str, total_tests, successful_tests, consecutive_failures = result
                metrics.first_seen = datetime.fromisoformat(first_seen_str) if first_seen_str else datetime.now()
                metrics.test_count = total_tests if total_tests else 0
                metrics.success_rate = successful_tests / total_tests if total_tests and total_tests > 0 else 0.0
                metrics.consecutive_failures = consecutive_failures if consecutive_failures else 0
            
            self.logger.info(f"文件测试完成: {os.path.basename(file_path)} - "
                           f"可用率: {metrics.availability_rate:.2%}, "
                           f"稳定性: {metrics.stability_score:.2f}, "
                           f"在线时长: {metrics.uptime_hours:.1f}h")
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"测试文件 {file_path} 时出错: {e}")
            return None
    
    def test_all_files(self) -> List[StabilityMetrics]:
        """测试所有M3U文件的稳定性"""
        # 获取所有M3U文件
        m3u_files = [f for f in os.listdir(self.m3u_dir) 
                     if f.endswith('.m3u') and not f.startswith('all_channels_')]
        
        if not m3u_files:
            self.logger.warning("未找到任何M3U文件")
            return []
        
        self.logger.info(f"找到 {len(m3u_files)} 个M3U文件，开始稳定性测试")
        
        results = []
        for file_name in m3u_files:
            file_path = os.path.join(self.m3u_dir, file_name)
            metrics = self.test_single_file(file_path)
            if metrics:
                results.append(metrics)
        
        self.logger.info(f"稳定性测试完成，共测试 {len(results)} 个文件")
        return results
    
    def select_best_file(self, metrics_list: List[StabilityMetrics]) -> Optional[StabilityMetrics]:
        """从测试结果中选择最优文件
        
        选择标准（按优先级）：
        1. 稳定性评分（最高）
        2. 在线时长（最长）
        3. 可用率（最高）
        4. 平均速度（最快）
        """
        if not metrics_list:
            return None
        
        # 综合评分公式
        def calculate_comprehensive_score(metrics: StabilityMetrics) -> float:
            return (
                metrics.stability_score * 0.4 +  # 稳定性权重40%
                min(metrics.uptime_hours / 100, 1) * 100 * 0.3 +  # 在线时长权重30%（100小时为满分）
                metrics.availability_rate * 100 * 0.2 +  # 可用率权重20%
                max(0, 1 - metrics.avg_speed / 1000) * 100 * 0.1  # 速度权重10%（1000ms内）
            )
        
        # 计算每个文件的综合评分
        scored_files: List[Tuple[StabilityMetrics, float]] = []
        for metrics in metrics_list:
            score = calculate_comprehensive_score(metrics)
            scored_files.append((metrics, score))
        
        # 按综合评分排序
        scored_files.sort(key=lambda x: x[1], reverse=True)
        
        best_metrics, best_score = scored_files[0]
        
        self.logger.info("最优文件选择结果:")
        self.logger.info(f"🏆 最优文件: {os.path.basename(best_metrics.file_path)}")
        self.logger.info(f"📊 综合评分: {best_score:.2f}")
        self.logger.info(f"🔒 稳定性: {best_metrics.stability_score:.2f}")
        self.logger.info(f"⏱️  在线时长: {best_metrics.uptime_hours:.1f}h")
        self.logger.info(f"✅ 可用率: {best_metrics.availability_rate:.2%}")
        self.logger.info(f"⚡ 平均速度: {best_metrics.avg_speed:.2f}ms")
        
        # 输出所有文件排名
        self.logger.info("所有文件排名:")
        for i, (metrics, score) in enumerate(scored_files[:5]):  # 只显示前5名
            status = "🏆" if i == 0 else f"{i+1}."
            self.logger.info(f"{status} {os.path.basename(metrics.file_path)} - "
                           f"评分: {score:.2f}, 稳定性: {metrics.stability_score:.2f}")
        
        return best_metrics
    
    def run_periodic_stability_test(self, duration_hours: int = 24):
        """运行周期性稳定性测试
        
        Args:
            duration_hours: 测试持续时间（小时）
        """
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=duration_hours)
        
        self.logger.info(f"开始周期性稳定性测试，持续 {duration_hours} 小时")
        self.logger.info(f"开始时间: {start_time}, 结束时间: {end_time}")
        
        test_count = 0
        best_files_history = []
        
        while datetime.now() < end_time:
            test_count += 1
            self.logger.info(f"第 {test_count} 轮稳定性测试开始")
            
            # 测试所有文件
            results = self.test_all_files()
            
            if results:
                # 选择最优文件
                best_file = self.select_best_file(results)
                if best_file:
                    best_files_history.append({
                        'test_time': datetime.now(),
                        'best_file': os.path.basename(best_file.file_path),
                        'stability_score': best_file.stability_score,
                        'uptime_hours': best_file.uptime_hours
                    })
                
                # 保存本轮测试结果
                self._save_test_report(results, test_count)
            
            # 等待下一轮测试
            if datetime.now() + timedelta(hours=self.test_interval_hours) < end_time:
                self.logger.info(f"等待 {self.test_interval_hours} 小时后进行下一轮测试...")
                time.sleep(self.test_interval_hours * 3600)
            else:
                break
        
        # 生成最终报告
        self._generate_final_report(best_files_history, duration_hours)
        
        self.logger.info(f"周期性稳定性测试完成，共进行 {test_count} 轮测试")
    
    def _save_test_report(self, results: List[StabilityMetrics], test_round: int):
        """保存单轮测试报告"""
        report_dir = os.path.join(self.m3u_dir, "stability_reports")
        os.makedirs(report_dir, exist_ok=True)
        
        report_data = {
            'test_round': test_round,
            'test_time': datetime.now().isoformat(),
            'total_files': len(results),
            'files': []
        }
        
        for metrics in results:
            report_data['files'].append({
                'file_path': metrics.file_path,
                'source_ip': metrics.source_ip,
                'total_channels': metrics.total_channels,
                'available_channels': metrics.available_channels,
                'availability_rate': metrics.availability_rate,
                'avg_speed': metrics.avg_speed,
                'stability_score': metrics.stability_score,
                'uptime_hours': metrics.uptime_hours,
                'test_count': metrics.test_count,
                'success_rate': metrics.success_rate
            })
        
        report_file = os.path.join(report_dir, f"stability_test_round_{test_round}.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
    
    def _generate_final_report(self, best_files_history: List[Dict], duration_hours: int):
        """生成最终稳定性测试报告"""
        if not best_files_history:
            self.logger.warning("没有测试数据，无法生成最终报告")
            return
        
        # 统计最优文件出现频率
        file_frequency: Dict[str, int] = {}
        for record in best_files_history:
            file_name = record['best_file']
            file_frequency[file_name] = file_frequency.get(file_name, 0) + 1
        
        # 找出最稳定的文件
        most_stable_file = max(file_frequency.items(), key=lambda x: x[1])
        
        report_data = {
            'test_duration_hours': duration_hours,
            'total_test_rounds': len(best_files_history),
            'start_time': best_files_history[0]['test_time'].isoformat() if best_files_history else '',
            'end_time': best_files_history[-1]['test_time'].isoformat() if best_files_history else '',
            'most_stable_file': {
                'file_name': most_stable_file[0],
                'appearance_count': most_stable_file[1],
                'appearance_rate': most_stable_file[1] / len(best_files_history)
            },
            'best_files_history': best_files_history,
            'file_frequency': file_frequency,
            'recommendation': f"推荐使用文件: {most_stable_file[0]} (出现频率: {most_stable_file[1]}/{len(best_files_history)})"
        }
        
        report_file = os.path.join(self.m3u_dir, "final_stability_report.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
        
        self.logger.info(f"最终稳定性报告已保存: {report_file}")
        self.logger.info(f"🎯 推荐最优文件: {most_stable_file[0]}")
        self.logger.info(f"📈 出现频率: {most_stable_file[1]}/{len(best_files_history)} "
                       f"({most_stable_file[1]/len(best_files_history):.2%})")

    def save_best_file_as_fixed_name(self, best_file_path: str, fixed_filename: str = "best_stable_channels.m3u") -> bool:
        """将最优文件保存为固定文件名
        
        Args:
            best_file_path: 最优文件的完整路径
            fixed_filename: 固定文件名，默认为"best_stable_channels.m3u"
            
        Returns:
            是否成功保存
        """
        try:
            # 构建目标文件路径（保存在m3u目录下）
            target_path = os.path.join(self.m3u_dir, fixed_filename)
            
            # 复制文件
            shutil.copy2(best_file_path, target_path)
            
            self.logger.info(f"✅ 最优文件已保存为固定文件名: {fixed_filename}")
            self.logger.info(f"📁 源文件: {os.path.basename(best_file_path)}")
            self.logger.info(f"📁 目标文件: {fixed_filename}")
            
            # 验证文件是否成功复制
            if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                self.logger.info(f"✅ 文件复制验证成功，文件大小: {os.path.getsize(target_path)} 字节")
                return True
            else:
                self.logger.error("❌ 文件复制失败，目标文件不存在或为空")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ 保存最优文件为固定文件名时出错: {e}")
            return False

    def select_and_save_best_file(self, metrics_list: List[StabilityMetrics], 
                                fixed_filename: str = "best_stable_channels.m3u") -> Optional[StabilityMetrics]:
        """选择最优文件并保存为固定文件名
        
        Args:
            metrics_list: 稳定性指标列表
            fixed_filename: 固定文件名
            
        Returns:
            最优文件的稳定性指标，如果失败返回None
        """
        best_file = self.select_best_file(metrics_list)
        
        if best_file:
            # 保存为固定文件名
            success = self.save_best_file_as_fixed_name(best_file.file_path, fixed_filename)
            if success:
                self.logger.info(f"🎉 最优文件选择并保存完成: {fixed_filename}")
                return best_file
            else:
                self.logger.error("❌ 最优文件保存失败")
                return None
        else:
            self.logger.warning("⚠️ 未找到最优文件，无法保存")
            return None


def main():
    """主函数 - 示例用法"""
    import logging
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建稳定性测试器
    tester = M3UStabilityTester("output/m3u", test_interval_hours=6)
    
    # 运行单次测试
    print("开始单次稳定性测试...")
    results = tester.test_all_files()
    
    if results:
        best_file = tester.select_best_file(results)
        print(f"\n🎯 最优文件: {os.path.basename(best_file.file_path)}")
    else:
        print("未找到可用的M3U文件")
    
    # 运行周期性测试（示例：测试1小时，实际使用时可以设置为24小时或更长）
    # tester.run_periodic_stability_test(duration_hours=1)


if __name__ == "__main__":
    main()