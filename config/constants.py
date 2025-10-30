"""常量配置"""
BASE_URL = "https://tonkiang.us"

# 网络请求配置
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}
API_HEADERS = {
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': f'{BASE_URL}/hotellist.html'
}

# 路径与文件名配置
OUTPUT_DIR = "output"
OUTPUT_M3U_DIR = f"{OUTPUT_DIR}/m3u"
OUTPUT_LOG_DIR = f"{OUTPUT_DIR}/logs"
OUTPUT_DATA_DIR = f"{OUTPUT_DIR}/data"
BEST_STABLE_FILENAME = "best_stable_channels.m3u"

# 外部程序路径（如VLC）
VLC_PATH = r"D:\\Program Files\\VideoLAN\\VLC"