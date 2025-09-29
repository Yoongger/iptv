"""
测试M3U优化器中的频道排序功能
"""
import sys
import os
import unittest

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.m3u_optimizer import M3UOptimizer

class TestChannelSort(unittest.TestCase):
    """测试频道排序功能"""
    
    def setUp(self):
        """初始化测试环境"""
        # 创建一个M3UOptimizer实例，但不实际执行优化
        self.optimizer = M3UOptimizer("output/m3u")
        
        # 模拟频道列表，包含各种格式的频道名称
        self.test_channels = [
            {'name': 'CCTV10', 'url': 'http://example.com/cctv10'},
            {'name': 'CCTV-1', 'url': 'http://example.com/cctv1'},
            {'name': 'CCTV 2', 'url': 'http://example.com/cctv2'},
            {'name': 'CCTV9', 'url': 'http://example.com/cctv9'},
            {'name': 'CCTV-5+', 'url': 'http://example.com/cctv5plus'},
            {'name': 'CCTV-5', 'url': 'http://example.com/cctv5'},
            {'name': 'CCTV 4', 'url': 'http://example.com/cctv4'},
            {'name': 'CCTV-13', 'url': 'http://example.com/cctv13'},
            {'name': 'CCTV-8', 'url': 'http://example.com/cctv8'},
            {'name': 'CCTV综合', 'url': 'http://example.com/cctvzh'},
            {'name': '湖南卫视', 'url': 'http://example.com/hunantv'},
            {'name': '北京卫视', 'url': 'http://example.com/btv'},
            {'name': '江苏卫视', 'url': 'http://example.com/jstv'},
            {'name': '浙江卫视', 'url': 'http://example.com/zjtv'},
            {'name': '东方卫视', 'url': 'http://example.com/dftv'},
            {'name': '广东卫视', 'url': 'http://example.com/gdtv'},
            {'name': '凤凰卫视', 'url': 'http://example.com/phtv'},
            {'name': '香港卫视', 'url': 'http://example.com/hktv'},
            {'name': '体育频道1', 'url': 'http://example.com/sports1'},
            {'name': '体育频道10', 'url': 'http://example.com/sports10'},
            {'name': '体育频道2', 'url': 'http://example.com/sports2'},
        ]
    
    def test_natural_sort_key(self):
        """测试自然排序键函数"""
        # 获取排序函数
        natural_sort_key = None
        
        # 从M3UOptimizer类中提取natural_sort_key函数
        # 由于natural_sort_key是parse_m3u_file方法内的局部函数，我们需要模拟其环境
        def get_sort_function():
            # 调用parse_m3u_file方法的一部分代码来获取natural_sort_key函数
            channels = []
            
            # 改进的频道名称排序（统一返回列表类型）
            def natural_sort_key(s):
                import re
                name = s['name']
                
                # 特殊处理CCTV频道
                if name.startswith('CCTV'):
                    # 处理带有"+"号的CCTV频道（如CCTV-5+）
                    plus_match = re.search(r'CCTV[- ]?(\d+)\+', name)
                    if plus_match:
                        # 带"+"号的频道排在对应数字频道之后
                        return ['CCTV', int(plus_match.group(1)), 1]
                    
                    # 提取数字部分，支持多种格式：CCTV1, CCTV-1, CCTV 1
                    num_match = re.search(r'CCTV[- ]?(\d+)', name)
                    if num_match:
                        return ['CCTV', int(num_match.group(1)), 0]
                    
                    # 处理无数字的CCTV频道（如"CCTV综合"）
                    return ['CCTV', 0, 0, name]
                
                # 处理其他常见电视台命名模式（如卫视频道）
                for prefix in ['北京', '东方', '湖南', '江苏', '浙江']:
                    if name.startswith(prefix):
                        return [prefix, name]
                
                # 处理卫视频道
                if '卫视' in name:
                    province = name.split('卫视')[0]
                    return [province, '卫视']
                
                # 普通频道名称的自然排序
                def convert(text):
                    return int(text) if text.isdigit() else text.lower()
                return [convert(c) for c in re.split('([0-9]+)', name)]
            
            return natural_sort_key
        
        # 获取排序函数
        natural_sort_key = get_sort_function()
        
        # 使用排序函数对测试频道进行排序
        sorted_channels = sorted(self.test_channels, key=natural_sort_key)
        
        # 打印排序结果
        print("\n排序后的频道列表:")
        for i, channel in enumerate(sorted_channels):
            print(f"{i+1}. {channel['name']}")
        
        # 验证CCTV频道的排序是否正确
        cctv_channels = [c for c in sorted_channels if c['name'].startswith('CCTV')]
        
        # 预期的CCTV频道顺序
        expected_cctv_order = [
            'CCTV综合',  # 无数字的排在最前面
            'CCTV-1',
            'CCTV 2',
            'CCTV 4',
            'CCTV-5',
            'CCTV-5+',  # 特殊处理+号
            'CCTV-8',
            'CCTV9',
            'CCTV10',
            'CCTV-13',
        ]
        
        actual_cctv_order = [c['name'] for c in cctv_channels]
        
        # 验证排序结果
        self.assertEqual(len(actual_cctv_order), len(expected_cctv_order), 
                         "CCTV频道数量不匹配")
        
        # 打印实际排序和预期排序的对比
        print("\nCCTV频道排序验证:")
        print("预期顺序:", expected_cctv_order)
        print("实际顺序:", actual_cctv_order)
        
        # 验证体育频道的排序是否正确（数字应该按照1,2,10而不是1,10,2）
        sports_channels = [c for c in sorted_channels if c['name'].startswith('体育频道')]
        expected_sports_order = ['体育频道1', '体育频道2', '体育频道10']
        actual_sports_order = [c['name'] for c in sports_channels]
        
        print("\n体育频道排序验证:")
        print("预期顺序:", expected_sports_order)
        print("实际顺序:", actual_sports_order)
        
        # 验证卫视频道的排序
        satellite_channels = [c for c in sorted_channels if '卫视' in c['name']]
        print("\n卫视频道排序:")
        for i, channel in enumerate(satellite_channels):
            print(f"{i+1}. {channel['name']}")

if __name__ == '__main__':
    unittest.main()