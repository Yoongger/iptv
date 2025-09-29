#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import traceback
import subprocess
import logging
from typing import Dict, List, Any, Optional, Tuple

# 配置日志
log_dir = os.path.join('output', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'auto_optimize_{time.strftime("%Y%m%d_%H%M%S")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('auto_optimizer')

class ErrorHandler:
    """错误处理类，用于捕获、分析和修复错误"""
    
    def __init__(self):
        self.error_fixes: Dict[str, Any] = {
            'FileNotFoundError': self._fix_file_not_found,
            'ImportError': self._fix_import_error,
            'TypeError': self._fix_type_error,
            'KeyError': self._fix_key_error,
            'IndexError': self._fix_index_error,
            'AttributeError': self._fix_attribute_error,
            'ValueError': self._fix_value_error,
            'UnicodeDecodeError': self._fix_unicode_error,
            'PermissionError': self._fix_permission_error,
        }
        self.fix_attempts: Dict[str, int] = {}
        self.max_attempts = 3
    
    def _fix_file_not_found(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复文件未找到错误"""
        error_msg = str(error)
        filename = error_msg.split("'")[1] if "'" in error_msg else None
        
        if not filename:
            return False, "无法确定缺失的文件名"
        
        # 检查是否是配置文件缺失
        if filename.endswith('.json') or filename.endswith('.yaml') or filename.endswith('.yml'):
            dir_path = os.path.dirname(filename)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"创建目录: {dir_path}")
            
            # 创建空配置文件
            with open(filename, 'w', encoding='utf-8') as f:
                if filename.endswith('.json'):
                    f.write('{}')
                else:
                    f.write('# 自动生成的配置文件\n')
            
            logger.info(f"创建了空配置文件: {filename}")
            return True, f"创建了缺失的配置文件: {filename}"
        
        # 检查是否是输出目录缺失
        if 'output' in filename or 'data' in filename:
            dir_path = os.path.dirname(filename)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"创建目录: {dir_path}")
                return True, f"创建了缺失的目录: {dir_path}"
        
        return False, f"无法自动修复文件缺失: {filename}"
    
    def _fix_import_error(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复导入错误"""
        error_msg = str(error)
        module_name = error_msg.split("'")[1] if "'" in error_msg else None
        
        if not module_name:
            return False, "无法确定缺失的模块名"
        
        # 尝试安装缺失的模块
        try:
            logger.info(f"尝试安装缺失的模块: {module_name}")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', module_name])
            return True, f"成功安装缺失的模块: {module_name}"
        except subprocess.CalledProcessError:
            return False, f"无法安装模块: {module_name}"
    
    def _fix_type_error(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复类型错误"""
        # 这里只能处理一些常见的类型错误
        error_msg = str(error)
        
        if "NoneType" in error_msg and "subscriptable" in error_msg:
            return False, "检测到空对象被当作字典或列表使用，请检查数据初始化"
        
        if "NoneType" in error_msg and "attribute" in error_msg:
            return False, "检测到空对象被当作对象使用，请检查对象初始化"
        
        return False, "无法自动修复类型错误"
    
    def _fix_key_error(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复键错误"""
        # 分析堆栈跟踪，找到发生错误的文件和行号
        for line in traceback_str.split('\n'):
            if 'File "' in line and '.py"' in line:
                file_info = line.split('File "')[1].split('", line')[0]
                if os.path.exists(file_info):
                    return False, f"字典键错误，请检查文件 {file_info} 中的字典访问"
        
        return False, "无法自动修复键错误"
    
    def _fix_index_error(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复索引错误"""
        return False, "索引超出范围，请检查列表或数组的访问"
    
    def _fix_attribute_error(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复属性错误"""
        return False, "对象属性错误，请检查对象的属性访问"
    
    def _fix_value_error(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复值错误"""
        error_msg = str(error)
        
        # 处理编码错误
        if "codec can't decode" in error_msg:
            return False, "编码错误，请检查文件编码"
        
        return False, "值错误，请检查输入参数"
    
    def _fix_unicode_error(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复Unicode错误"""
        return False, "Unicode解码错误，请检查文件编码"
    
    def _fix_permission_error(self, error: Exception, traceback_str: str) -> Tuple[bool, str]:
        """修复权限错误"""
        error_msg = str(error)
        filename = error_msg.split("'")[1] if "'" in error_msg else None
        
        if not filename:
            return False, "无法确定权限错误的文件"
        
        # 尝试修改文件权限
        try:
            if os.path.exists(filename):
                import stat
                current_mode = os.stat(filename).st_mode
                os.chmod(filename, current_mode | stat.S_IRUSR | stat.S_IWUSR)
                logger.info(f"修改了文件权限: {filename}")
                return True, f"修改了文件权限: {filename}"
        except Exception as e:
            return False, f"无法修改文件权限: {str(e)}"
        
        return False, "无法自动修复权限错误"
    
    def handle_error(self, error: Exception) -> Tuple[bool, str]:
        """处理错误，尝试自动修复"""
        error_type = type(error).__name__
        traceback_str = traceback.format_exc()
        
        # 记录错误信息
        logger.error(f"捕获到错误: {error_type} - {str(error)}")
        logger.error(f"错误堆栈: {traceback_str}")
        
        # 检查是否超过最大尝试次数
        if error_type in self.fix_attempts and self.fix_attempts[error_type] >= self.max_attempts:
            logger.warning(f"错误 {error_type} 已达到最大修复尝试次数 {self.max_attempts}")
            return False, f"达到最大修复尝试次数 {self.max_attempts}"
        
        # 尝试修复错误
        if error_type in self.error_fixes:
            # 增加尝试次数
            self.fix_attempts[error_type] = self.fix_attempts.get(error_type, 0) + 1
            
            # 调用对应的修复函数
            fixed, message = self.error_fixes[error_type](error, traceback_str)
            
            if fixed:
                logger.info(f"成功修复错误: {message}")
            else:
                logger.warning(f"无法自动修复错误: {message}")
            
            return fixed, message
        else:
            logger.warning(f"未知错误类型: {error_type}，无法自动修复")
            return False, f"未知错误类型: {error_type}"


def run_optimize_command():
    """运行优化命令并处理可能的错误"""
    error_handler = ErrorHandler()
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info("开始执行 python main.py --optimize-only 命令")
            
            # 执行命令并捕获输出
            process = subprocess.Popen(
                [sys.executable, 'main.py', '--optimize-only'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            
            # 实时获取输出
            while True:
                output_line = process.stdout.readline()
                if output_line == '' and process.poll() is not None:
                    break
                if output_line:
                    logger.info(f"命令输出: {output_line.strip()}")
            
            # 获取错误输出
            stderr = process.stderr.read()
            if stderr:
                logger.warning(f"命令错误输出: {stderr}")
            
            # 检查返回码
            return_code = process.poll()
            if return_code == 0:
                logger.info("命令执行成功")
                return True
            else:
                logger.error(f"命令执行失败，返回码: {return_code}")
                raise Exception(f"命令执行失败: {stderr}")
                
        except Exception as e:
            retry_count += 1
            logger.error(f"执行出错 (尝试 {retry_count}/{max_retries}): {str(e)}")
            
            # 尝试自动修复错误
            fixed, message = error_handler.handle_error(e)
            
            if fixed:
                logger.info(f"修复成功，重试执行命令: {message}")
                # 等待一小段时间再重试
                time.sleep(2)
            else:
                logger.error(f"无法自动修复错误: {message}")
                if retry_count >= max_retries:
                    logger.critical(f"达到最大重试次数 {max_retries}，终止执行")
                    print("\n\n警报: 无法自动修复错误，请手动检查！\n\n")
                    return False
                # 等待更长时间再重试
                time.sleep(5)
    
    return False


if __name__ == "__main__":
    logger.info("=== 自动优化程序启动 ===")
    logger.info(f"日志文件: {log_file}")
    
    try:
        # 终止可能正在运行的Python进程
        if sys.platform == 'win32':
            logger.info("尝试终止当前所有Python测试进程")
            os.system('taskkill /f /im python.exe 2>nul')
        else:
            logger.info("在非Windows平台上跳过进程终止")
        
        # 运行优化命令
        success = run_optimize_command()
        
        if success:
            logger.info("=== 自动优化程序成功完成 ===")
            print("\n优化成功完成！详细日志请查看:", log_file)
        else:
            logger.error("=== 自动优化程序失败 ===")
            print("\n优化过程中遇到错误！详细日志请查看:", log_file)
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("用户中断了程序执行")
        print("\n程序被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"发生未捕获的异常: {str(e)}")
        logger.critical(traceback.format_exc())
        print(f"\n发生严重错误: {str(e)}")
        print(f"详细日志请查看: {log_file}")
        sys.exit(1)