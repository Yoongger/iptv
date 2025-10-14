"""主入口文件"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from crawler.ip_crawler import IPCrawler
from crawler.channel_crawler import ChannelCrawler
from utils.m3u_processor import M3UProcessor
from utils.m3u_optimizer import M3UOptimizer
from config.logger import setup_logger
import json
import os
import glob
import time
import argparse

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='IPTV频道爬取和优化工具')
    parser.add_argument('--optimize-only', action='store_true', help='仅执行M3U文件优化，不爬取新数据')
    args = parser.parse_args()
    
    logger = setup_logger("IPTV爬虫", "iptv_crawler.log")
    
    try:
        # 初始化各模块
        ip_crawler = IPCrawler()
        channel_crawler = ChannelCrawler()
        m3u_processor = M3UProcessor(logger)
        
        logger.info("开始爬取IPTV频道数据")
        
        # 1. 获取所有IP地址
        ip_addresses = ip_crawler.parse_main_page()
        logger.info(f"找到 {len(ip_addresses)} 个IP地址")
        
        all_channels = []
        
        for ip_info in ip_addresses:
            try:
                # 2. 获取每个IP的频道列表链接
                channel_links = channel_crawler.parse_ip_detail_page(ip_info)
                logger.info(f"IP {ip_info.ip} 有 {len(channel_links)} 个频道列表")
                
                for channel_info in channel_links:
                    # 3. 获取每个频道列表的具体频道
                    channels = channel_crawler.parse_channel_list_page(channel_info)
                    all_channels.extend(channels)
                    logger.info(f"从 {channel_info['channel_url']} 获取到 {len(channels)} 个频道")
                    
                    # 避免请求过于频繁
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"处理IP {ip_info.ip} 时出错: {e}")
                continue
        
        if all_channels:
            # 保存新爬取的频道为M3U文件
            m3u_processor.save_individual_m3u_files(all_channels)
            
            # 保存为JSON
            os.makedirs('output/data', exist_ok=True)
            with open('output/data/iptv_channels.json', 'w', encoding='utf-8') as f:
                json.dump([c.__dict__ for c in all_channels], f, ensure_ascii=False, indent=2)
            
            logger.info(f"爬取完成！共找到 {len(all_channels)} 个频道")
            print(f"文件已保存为: output/m3u/ 目录下的多个M3U文件和 output/data/iptv_channels.json")
        else:
            logger.warning("未找到任何频道数据")
            print("未找到任何频道数据")
            
        # 执行M3U文件优化
        logger.info("开始执行M3U文件优化...")
        print("开始执行M3U文件优化...")
        
        # 添加VLC路径到系统PATH
        vlc_path = r"D:\Program Files\VideoLAN\VLC"
        if vlc_path not in os.environ["PATH"]:
            os.environ["PATH"] += os.pathsep + vlc_path
        
        # 使用VLC测试模式（带超时控制）
        optimizer = M3UOptimizer("output/m3u", "output/logs", use_vlc=True)
        optimizer.optimize_m3u_files()
            
    except Exception as e:
        logger.error(f"爬取过程中发生错误: {e}")
        print(f"错误: {e}")

def optimize_only():
    """仅执行M3U文件优化"""
    logger = setup_logger("M3U优化", "m3u_optimizer.log")
    logger.info("仅执行M3U文件优化模式")
    print("仅执行M3U文件优化模式")
    
    # 确保输出目录存在
    os.makedirs('output/m3u', exist_ok=True)
    os.makedirs('output/logs', exist_ok=True)
    
    # 添加VLC路径到系统PATH
    vlc_path = r"D:\Program Files\VideoLAN\VLC"
    if vlc_path not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + vlc_path
    
    # 使用VLC测试模式（带超时控制）
    optimizer = M3UOptimizer("output/m3u", "output/logs", use_vlc=True)
    optimizer.optimize_m3u_files()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='IPTV频道爬取和优化工具')
    parser.add_argument('--optimize-only', action='store_true', help='仅执行M3U文件优化，不爬取新数据')
    args = parser.parse_args()
    
    if args.optimize_only:
        optimize_only()
    else:
        main()