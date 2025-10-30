"""主入口文件"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from crawler.simple_ip_crawler import SimpleIPCrawler
from crawler.channel_crawler import ChannelCrawler
from utils.m3u_processor import M3UProcessor
from utils.m3u_optimizer import M3UOptimizer
from utils.stability_tester import M3UStabilityTester
from config.logger import setup_logger
from config.constants import OUTPUT_M3U_DIR, OUTPUT_LOG_DIR, OUTPUT_DATA_DIR, BEST_STABLE_FILENAME, VLC_PATH
import json
import os
import glob
import time
import argparse
import re

def load_existing_ips(logger):
    """加载已爬取的IP地址记录，用于IP级别去重"""
    existing_ips = set()
    
    # 检查IP爬取记录文件
    ip_history_file = f"{OUTPUT_DATA_DIR}/ip_crawl_history.json"
    if os.path.exists(ip_history_file):
        try:
            with open(ip_history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for ip_record in data:
                    ip = ip_record.get('ip', '')
                    if ip:  # 只添加非空的IP地址
                        existing_ips.add(ip)
            if logger:
                logger.info(f"从历史记录加载了 {len(existing_ips)} 个已爬取的IP地址")
        except json.JSONDecodeError as e:
            if logger:
                logger.warning(f"IP爬取历史记录文件格式错误，将重新创建: {e}")
            # 如果文件格式错误，删除文件以便重新创建
            try:
                os.remove(ip_history_file)
                logger.info("已删除损坏的IP爬取历史记录文件")
            except Exception as delete_error:
                logger.error(f"删除损坏文件失败: {delete_error}")
        except Exception as e:
            if logger:
                logger.warning(f"加载IP爬取历史失败: {e}")
    
    return existing_ips

def save_ip_crawl_history(ip_addresses, logger):
    """保存IP爬取历史记录"""
    try:
        ip_history_file = f"{OUTPUT_DATA_DIR}/ip_crawl_history.json"
        os.makedirs(OUTPUT_DATA_DIR, exist_ok=True)
        
        # 读取现有记录
        existing_records = []
        if os.path.exists(ip_history_file):
            try:
                with open(ip_history_file, 'r', encoding='utf-8') as f:
                    existing_records = json.load(f)
            except json.JSONDecodeError:
                logger.warning("IP爬取历史记录文件格式错误，将重新创建")
        
        # 创建IP地址到记录的映射
        existing_ip_map = {record['ip']: record for record in existing_records}
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # 更新或添加新记录
        for ip_info in ip_addresses:
            ip = getattr(ip_info, 'ip', '')
            if not ip:
                continue
                
            record_data = {
                'ip': ip,
                'url': getattr(ip_info, 'url', ''),
                'category': getattr(ip_info, 'category', '未知分类'),
                'channel_count': getattr(ip_info, 'channel_count', 0),
                'location': getattr(ip_info, 'location', '未知位置'),
                'online_time': getattr(ip_info, 'online_time', ''),
                'last_crawled': current_time
            }
            
            if ip in existing_ip_map:
                # 更新现有记录
                existing_ip_map[ip].update(record_data)
            else:
                # 添加新记录
                record_data['first_crawled'] = current_time
                existing_ip_map[ip] = record_data
        
        # 保存更新后的记录
        with open(ip_history_file, 'w', encoding='utf-8') as f:
            json.dump(list(existing_ip_map.values()), f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存 {len(existing_ip_map)} 个IP地址的爬取记录到 {ip_history_file}")
            
    except Exception as e:
        logger.error(f"保存IP爬取历史失败: {e}")

def run_single_cycle(start_page=1, end_page=None, skip_existing=True, sources='酒店源,组播源,秒播源'):
    """执行单次爬取和优化
    
    Args:
        start_page: 抓取起始页，默认为1
        end_page: 抓取结束页，默认为None（抓取所有页）
        skip_existing: 是否跳过已抓取的IP地址，默认为True
        sources: 指定抓取的源类别，用逗号分隔，默认为所有源
    """
    logger = setup_logger("IPTV爬虫", "iptv_crawler.log")
    
    try:
        # 初始化各模块
        ip_crawler = SimpleIPCrawler()
        channel_crawler = ChannelCrawler()
        m3u_processor = M3UProcessor(logger)
        
        # 解析源类别参数
        source_list = [s.strip() for s in sources.split(',') if s.strip()]
        logger.info(f"开始爬取IPTV频道数据，起始页: {start_page}, 结束页: {end_page}, 跳过已抓取IP: {skip_existing}, 抓取源: {source_list}")
        
        # 加载已爬取的IP地址记录用于IP级别去重
        existing_ips = set()
        if skip_existing:
            existing_ips = load_existing_ips(logger)
            logger.info(f"已存在 {len(existing_ips)} 个已爬取的IP地址，将进行IP级别去重")
        else:
            logger.info("跳过已抓取IP功能已禁用，将重新抓取所有IP地址")
        
        # 1. 获取所有IP地址
        ip_addresses = ip_crawler.parse_main_page(start_page=start_page, end_page=end_page, sources=source_list)
        logger.info(f"找到 {len(ip_addresses)} 个IP地址")
        
        # 过滤掉已爬取的IP地址
        new_ip_addresses = []
        for ip_info in ip_addresses:
            if ip_info.ip not in existing_ips:
                new_ip_addresses.append(ip_info)
                logger.info(f"新IP地址: {ip_info.ip} - {ip_info.location}")
            else:
                logger.info(f"跳过已爬取的IP地址: {ip_info.ip}")
        
        logger.info(f"过滤后，需要爬取的IP地址数量: {len(new_ip_addresses)}")
        
        all_channels = []
        successfully_crawled_ips = []  # 记录成功爬取的IP
        
        for ip_info in new_ip_addresses:
            try:
                # 2. 获取每个IP的频道列表链接
                channel_links = channel_crawler.parse_ip_detail_page(ip_info)
                logger.info(f"IP {ip_info.ip} 有 {len(channel_links)} 个频道列表")
                
                ip_channels = []  # 当前IP的频道
                
                for channel_info in channel_links:
                    # 3. 获取每个频道列表的具体频道
                    channels = channel_crawler.parse_channel_list_page(channel_info)
                    
                    # 添加当前IP的频道
                    ip_channels.extend(channels)
                    
                    logger.info(f"从 {channel_info['channel_url']} 获取到 {len(channels)} 个频道")
                    
                    # 避免请求过于频繁
                    time.sleep(2)
                
                # 更新IP信息的频道数量
                ip_info.channel_count = len(ip_channels)
                
                # 添加当前IP的频道到总列表
                all_channels.extend(ip_channels)
                
                # 记录成功爬取的IP
                successfully_crawled_ips.append(ip_info)
                
                logger.info(f"IP {ip_info.ip} 爬取完成，共获取 {len(ip_channels)} 个频道")
                
            except Exception as e:
                logger.error(f"处理IP {ip_info.ip} 时出错: {e}")
                # 即使出错，也记录该IP已被爬取（避免重复爬取）
                ip_info.channel_count = 0  # 设置频道数量为0
                successfully_crawled_ips.append(ip_info)
                continue
        
        if all_channels:
            # 先保存IP爬取历史记录，确保M3U处理器能获取到正确的信息
            if successfully_crawled_ips:
                save_ip_crawl_history(successfully_crawled_ips, logger)
                logger.info(f"已保存 {len(successfully_crawled_ips)} 个IP的爬取记录")
            
            # 保存新爬取的频道为M3U文件（只保存一次，避免重复）
            m3u_processor.save_individual_m3u_files(all_channels)
            
            # 保存为JSON
            os.makedirs(OUTPUT_DATA_DIR, exist_ok=True)
            with open(f"{OUTPUT_DATA_DIR}/iptv_channels.json", 'w', encoding='utf-8') as f:
                json.dump([c.__dict__ for c in all_channels], f, ensure_ascii=False, indent=2)
            
            logger.info(f"爬取完成！共找到 {len(all_channels)} 个频道")
            print(f"文件已保存为: output/m3u/ 目录下的多个M3U文件和 output/data/iptv_channels.json")
            
            # 不再创建备份目录，所有M3U文件都保存在output/m3u目录中
            m3u_files = [f for f in os.listdir(OUTPUT_M3U_DIR) if f.endswith('.m3u')]
            logger.info(f"当前有 {len(m3u_files)} 个原始M3U文件在 {OUTPUT_M3U_DIR} 目录中")
            print(f"📁 当前有 {len(m3u_files)} 个原始M3U文件在 {OUTPUT_M3U_DIR} 目录中")
            
        else:
            logger.warning("未找到任何频道数据")
            print("未找到任何频道数据")
            
        # 执行M3U文件优化
        logger.info("开始执行M3U文件优化...")
        print("开始执行M3U文件优化...")
        
        # 添加VLC路径到系统PATH
        vlc_path = VLC_PATH
        if vlc_path not in os.environ.get("PATH", ""):
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + vlc_path
        
        # 使用VLC测试模式（带超时控制）
        optimizer = M3UOptimizer(OUTPUT_M3U_DIR, OUTPUT_LOG_DIR, use_vlc=True)
        optimizer.optimize_m3u_files()
        
        # 执行稳定性测试
        logger.info("开始执行M3U文件稳定性测试...")
        print("开始执行M3U文件稳定性测试...")
        
        try:
            stability_tester = M3UStabilityTester(OUTPUT_M3U_DIR, test_interval_hours=6)
            results = stability_tester.test_all_files()
            
            if results:
                # 选择最优文件并保存为固定文件名
                best_file = stability_tester.select_and_save_best_file(results, BEST_STABLE_FILENAME)
                if best_file:
                    logger.info(f"稳定性测试完成，推荐最优文件: {os.path.basename(best_file.file_path)}")
                    print(f"🎯 稳定性测试完成，推荐最优文件: {os.path.basename(best_file.file_path)}")
                    print(f"💾 最优文件已保存为: {BEST_STABLE_FILENAME}")
                else:
                    logger.warning("稳定性测试未能选择出最优文件或保存失败")
                    print("⚠️ 稳定性测试未能选择出最优文件或保存失败")
            else:
                logger.warning("稳定性测试未找到可用文件")
                print("⚠️ 稳定性测试未找到可用文件")
                
        except Exception as stability_error:
            logger.error(f"稳定性测试出错: {stability_error}")
            print(f"❌ 稳定性测试出错: {stability_error}")
            
    except Exception as e:
        logger.error(f"爬取过程中发生错误: {e}")
        print(f"错误: {e}")

def run_cycle_with_optimize_only():
    """仅执行M3U文件优化的单次运行"""
    logger = setup_logger("M3U优化", "m3u_optimizer.log")
    logger.info("仅执行M3U文件优化模式")
    print("仅执行M3U文件优化模式")
    
    # 确保输出目录存在
    os.makedirs(OUTPUT_M3U_DIR, exist_ok=True)
    os.makedirs(OUTPUT_LOG_DIR, exist_ok=True)
    
    # 添加VLC路径到系统PATH
    vlc_path = VLC_PATH
    if vlc_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + vlc_path
    
    # 使用VLC测试模式（带超时控制）
    optimizer = M3UOptimizer(OUTPUT_M3U_DIR, OUTPUT_LOG_DIR, use_vlc=True)
    optimizer.optimize_m3u_files()
    
    # 执行稳定性测试
    logger.info("开始执行M3U文件稳定性测试...")
    print("开始执行M3U文件稳定性测试...")
    
    try:
        stability_tester = M3UStabilityTester(OUTPUT_M3U_DIR, test_interval_hours=6)
        results = stability_tester.test_all_files()
        
        if results:
            # 选择最优文件并保存为固定文件名
            best_file = stability_tester.select_and_save_best_file(results, BEST_STABLE_FILENAME)
            if best_file:
                logger.info(f"稳定性测试完成，推荐最优文件: {os.path.basename(best_file.file_path)}")
                print(f"🎯 稳定性测试完成，推荐最优文件: {os.path.basename(best_file.file_path)}")
                print(f"💾 最优文件已保存为: {BEST_STABLE_FILENAME}")
            else:
                logger.warning("稳定性测试未能选择出最优文件或保存失败")
                print("⚠️ 稳定性测试未能选择出最优文件或保存失败")
        else:
            logger.warning("稳定性测试未找到可用文件")
            print("⚠️ 稳定性测试未找到可用文件")
            
    except Exception as stability_error:
        logger.error(f"稳定性测试出错: {stability_error}")
        print(f"❌ 稳定性测试出错: {stability_error}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='IPTV频道爬取和优化工具')
    parser.add_argument('--optimize-only', action='store_true', help='仅执行M3U文件优化，不爬取新数据')
    parser.add_argument('--hours', type=int, default=0, help='循环运行的小时数，0表示只运行一次')
    parser.add_argument('--interval', type=int, default=60, help='每次运行的间隔时间（分钟），默认60分钟')
    parser.add_argument('--start-page', type=int, default=1, help='抓取起始页，默认为1')
    parser.add_argument('--end-page', type=int, default=None, help='抓取结束页，默认为None（抓取所有页）')
    parser.add_argument('--skip-existing', action='store_true', help='跳过已抓取的IP地址，默认为True')
    parser.add_argument('--no-skip-existing', action='store_true', help='不跳过已抓取的IP地址，重新抓取所有IP')
    parser.add_argument('--sources', type=str, default='酒店源,组播源,秒播源', help='指定抓取源IP类别，用逗号分隔，如：酒店源,组播源 或 秒播源')
    args = parser.parse_args()
    
    # 处理跳过已抓取IP的参数逻辑
    skip_existing = True  # 默认跳过已抓取IP
    if args.no_skip_existing:
        skip_existing = False
    elif args.skip_existing:
        skip_existing = True
    
    if args.hours == 0:
        # 单次运行
        if args.optimize_only:
            run_cycle_with_optimize_only()
        else:
            run_single_cycle(start_page=args.start_page, end_page=args.end_page, skip_existing=skip_existing, sources=args.sources)
    else:
        # 循环运行
        total_cycles = args.hours
        interval_minutes = args.interval
        current_cycle = 1
        
        print(f"开始循环运行，总时长: {total_cycles}小时，间隔: {interval_minutes}分钟")
        
        while current_cycle <= total_cycles:
            print(f"\n=== 第 {current_cycle}/{total_cycles} 次运行 ===")
            print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            try:
                if args.optimize_only:
                    run_cycle_with_optimize_only()
                else:
                    run_single_cycle(start_page=args.start_page, end_page=args.end_page, skip_existing=skip_existing, sources=args.sources)
                    
                print(f"第 {current_cycle} 次运行完成")
                
                # 如果不是最后一次运行，则等待
                if current_cycle < total_cycles:
                    wait_seconds = interval_minutes * 60
                    print(f"等待 {interval_minutes} 分钟后继续...")
                    time.sleep(wait_seconds)
                    
            except Exception as e:
                print(f"第 {current_cycle} 次运行出错: {e}")
                # 出错后等待一段时间再继续
                if current_cycle < total_cycles:
                    wait_seconds = interval_minutes * 60
                    print(f"出错后等待 {interval_minutes} 分钟后继续...")
                    time.sleep(wait_seconds)
            
            current_cycle += 1
        
        print(f"\n循环运行完成！总运行次数: {total_cycles}")