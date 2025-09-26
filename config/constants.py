"""常量配置"""
BASE_URL = "https://tonkiang.us"
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