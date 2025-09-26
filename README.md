# IPTV频道爬取与优化工具

## 项目概述
本项目是一个自动化爬取IPTV频道数据并生成优化M3U文件的工具，主要功能包括：
- 从指定网站爬取IPTV频道数据
- 自动检测频道可用性和连接速度
- 生成按速度排序的M3U播放列表
- 提供频道分类和过滤功能

## 安装指南

### 系统要求
- Python 3.8+
- Windows/Linux/macOS

### 依赖安装
```bash
# 克隆项目
git clone https://github.com/yoongger/iptv-crawler.git
cd iptv-crawler

# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.\.venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 依赖项列表
- requests >= 2.28.0
- beautifulsoup4 >= 4.11.1
- concurrent-log-handler >= 0.9.20
- tqdm >= 4.64.0

## 使用说明

### 基本用法
```bash
# 完整流程（爬取+优化）
python main.py

# 仅执行M3U文件优化
python main.py --optimize-only
```

### 参数说明
| 参数 | 说明 |
|------|------|
| `--optimize-only` | 仅优化现有M3U文件，不执行爬取 |
| `--max-workers NUM` | 设置并发线程数（默认10） |
| `--timeout SECONDS` | 设置请求超时时间（默认5秒） |

### 输出文件
- `output/m3u/`: 生成的M3U文件（按速度排序）
- `output/data/iptv_channels.json`: 原始频道数据
- `output/logs/`: 处理日志和结果

## 贡献指南

### 开发环境设置
1. Fork项目仓库
2. 安装开发依赖：
   ```bash
   pip install -r requirements-dev.txt
   ```
3. 配置pre-commit钩子：
   ```bash
   pre-commit install
   ```

### 代码规范
- 遵循PEP 8风格指南
- 为新增功能编写单元测试
- 提交前运行所有测试：
  ```bash
  pytest tests/
  ```

### 提交Pull Request
1. 从最新main分支创建特性分支
2. 提交清晰的commit message
3. 确保所有测试通过
4. 更新相关文档

## 许可证
本项目采用 [MIT License](LICENSE)。

## 项目结构
```
iptv/
├── config/        # 配置文件
├── crawler/       # 爬虫核心逻辑
├── models/        # 数据模型
├── output/        # 生成文件
├── tests/         # 测试代码
└── utils/         # 工具函数
```

## 联系信息
如有问题请联系：yoongger@gmail.com