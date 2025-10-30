#!/usr/bin/env python3
"""检查频道数据和IP历史记录"""

import json
import os

# 检查频道数据文件
channel_file = 'output/data/iptv_channels.json'
if os.path.exists(channel_file):
    with open(channel_file, 'r', encoding='utf-8') as f:
        channels = json.load(f)
    
    print('=== 频道数据中的location字段 ===')
    for i, channel in enumerate(channels[:5]):
        print(f'{i+1}. IP: {channel.get("source_ip", "无")}')
        print(f'   分类: {channel.get("category", "无")}')
        print(f'   位置: {channel.get("location", "无")}')
        print()
else:
    print('频道数据文件不存在')

# 检查IP历史记录文件
history_file = 'output/data/ip_crawl_history.json'
if os.path.exists(history_file):
    print('IP历史记录文件存在')
    with open(history_file, 'r', encoding='utf-8') as f:
        history = json.load(f)
    
    print('=== IP历史记录中的location字段 ===')
    for i, record in enumerate(history[:3]):
        print(f'{i+1}. IP: {record.get("ip", "无")}')
        print(f'   分类: {record.get("category", "无")}')
        print(f'   位置: {record.get("location", "无")}')
        print()
else:
    print('IP历史记录文件不存在')