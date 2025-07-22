# import requests
# import re
# import time
# from datetime import timedelta

# def get_youku_duration(url):
#     """
#     获取优酷视频时长（单位：秒）
#     参数:
#         url: 优酷视频播放页链接
#     返回:
#         视频时长（秒）或 None（获取失败时）
#     """
#     headers = {
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
#         'Accept-Language': 'zh-CN,zh;q=0.9',
#         'Referer': 'https://www.youku.com/'
#     }
    
#     try:
#         # 获取视频页面HTML
#         response = requests.get(url, headers=headers, timeout=10)
#         response.raise_for_status()  # 检查HTTP错误
#         html_content = response.text
        
#         # 使用正则表达式查找seconds值
#         # 匹配模式: "seconds":"123" 或 seconds:456
#         pattern = r'(?:seconds|"seconds")\s*[:=]\s*"(\d+)"'
#         match = re.search(pattern, html_content)
        
#         if match:
#             return int(match.group(1))
        
#         # 备用方案：尝试其他可能的字段名
#         backup_patterns = [
#             r'"duration"\s*:\s*(\d+)',    # "duration":360
#             r'"videoDuration"\s*:\s*(\d+)',# "videoDuration":360
#             r'"time"\s*:\s*"(\d+)"'        # "time":"360"
#         ]
        
#         for pattern in backup_patterns:
#             match = re.search(pattern, html_content)
#             if match:
#                 return int(match.group(1))
        
#         return None
    
#     except requests.exceptions.RequestException as e:
#         print(f"网络请求失败: {e}")
#         return None
#     except Exception as e:
#         print(f"解析错误: {e}")
#         return None

# def format_duration(seconds):
#     """
#     将秒数格式化为易读的时间字符串
#     参数:
#         seconds: 视频时长（秒）
#     返回:
#         格式化的时间字符串 (HH:MM:SS 或 MM:SS)
#     """
#     if seconds is None:
#         return "未知"
    
#     # 转换为时间增量对象
#     td = timedelta(seconds=seconds)
    
#     # 提取时间组件
#     hours, remainder = divmod(seconds, 3600)
#     minutes, seconds = divmod(remainder, 60)
    
#     # 根据时长选择合适的格式
#     if hours > 0:
#         return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
#     else:
#         return f"{minutes:02d}:{seconds:02d}"

# # 使用示例
# if __name__ == "__main__":
#     # 示例优酷视频链接（请替换为实际链接）
#     video_urls = [
#         "https://v.youku.com/v_show/id_XNTkxMzY2MjExNg==.html",
#         "https://v.youku.com/v_show/id_XNjQ3OTg4NTM4OA==.html",
#         "https://v.youku.com/v_show/id_XNTkzNjcwOTkwOA==.html"
#     ]
    
#     for url in video_urls:
#         print(f"\n解析视频: {url}")
        
#         # 获取原始秒数
#         seconds = get_youku_duration(url)
#         print(f"原始秒数: {seconds}")
        
#         # 格式化输出
#         formatted = format_duration(seconds)
#         print(f"格式化时长: {formatted}")
        
#         # 避免请求过快
#         time.sleep(1)


# from selenium import webdriver
# from selenium.webdriver.chrome.options import Options
# import time

# # 设置 Chrome 无头模式
# options = Options()
# options.add_argument('--headless')
# options.add_argument('--disable-gpu')

# driver = webdriver.Chrome(options=options)
# driver.get("https://www.youku.com")

# # 等待页面加载和 JS 执行（可以适当延长等待时间）
# time.sleep(5)

# cookies = driver.get_cookies()
# for cookie in cookies:
#     if cookie['name'] in ['_m_h5_tk', '_m_h5_tk_enc']:
#         print(f"{cookie['name']} = {cookie['value']}")

# driver.quit()


import re
from collections import Counter

def count_font_values_text(file_path):
    """
    直接以文本方式统计文件中 'font': 'XX' 的出现次数
    
    :param file_path: 文本文件路径
    :return: 包含统计结果的字典，格式为 {font值: 出现次数}
    """
    font_counter = Counter()
    # font_pattern = re.compile(r'<font>(\d+)</font>')  # 匹配 <font>数字</font> 爱奇艺字体
    # font_pattern = re.compile(r'"pos\\+":(\d+)')        # 匹配 "pos":数字 优酷位置
    font_pattern = re.compile(r'"size\\+":(\d+)')      # 匹配 "size": "数字" 优酷字体
    
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 查找所有匹配的font值
            matches = font_pattern.findall(line)
            for font in matches:
                font_counter[font] += 1
    
    return dict(font_counter.most_common())

# 使用示例
if __name__ == "__main__":
    file_path = "youku_danmu.txt"  # 替换为你的文件路径
    font_stats = count_font_values_text(file_path)
    
    print("不同值的统计结果（纯文本方式）：")
    for font, count in font_stats.items():
        print(f"值 '{font}': {count}次")
    
    # 输出统计摘要
    total = sum(font_stats.values())
    print(f"\n总计: {total}条记录")
    print(f"不同值数量: {len(font_stats)}种")
    if font_stats:
        most_common = max(font_stats.items(), key=lambda x: x[1])
        print(f"最常见的值: '{most_common[0]}' ({most_common[1]}次)")


# import re
# import time
# import math
# import zlib
# import requests
# import xmltodict

# class IqiyiDanmuDownloader:
#     """爱奇艺弹幕下载器"""
#     MAX_DURATION = 7200  # 2小时，单位: 秒

#     def __init__(self, video_url, output_file="danmu.txt"):
#         self.url = video_url
#         self.output_file = output_file

#     def extract_video_id(self):
#         """从URL中提取tvid"""
#         headers = {
#             "User-Agent": "Mozilla/5.0",
#             "Referer": self.url,
#         }
#         ts = int(time.time() * 1000)
#         url = f"https://www.iqiyi.com/prelw/player/lw/lwplay/accelerator.js?format=json&timestamp={ts}"
#         resp = requests.get(url, headers=headers, timeout=8)
#         data = resp.json()
#         return str(data.get("tvid", ""))

#     def get_duration(self, tvid):
#         """获取视频时长"""
#         url = f"https://pcw-api.iqiyi.com/video/video/baseinfo/{tvid}?t={int(time.time())}"
#         headers = {"User-Agent": "Mozilla/5.0"}
#         try:
#             resp = requests.get(url, headers=headers, timeout=8)
#             data = resp.json()
#             return int(data.get("data", {}).get("durationSec", 0))
#         except Exception:
#             return 0  # 网络异常时返回0

#     def fetch_danmaku_segment(self, tvid, part):
#         """获取单段弹幕数据"""
#         xx = tvid[-4:-2]
#         yy = tvid[-2:]
#         url = f"https://cmts.iqiyi.com/bullet/{xx}/{yy}/{tvid}_300_{part}.z"
#         try:
#             resp = requests.get(url, timeout=8)
#             if resp.status_code != 200 or not resp.content:
#                 return None
#             try:
#                 raw = zlib.decompress(resp.content)
#             except Exception:
#                 return None
#             return raw.decode('utf-8')  # 直接返回原始XML数据
#         except Exception:
#             return None

#     def save_danmu_to_txt(self, danmu_data):
#         """将弹幕数据保存到txt文件"""
#         with open(self.output_file, 'w', encoding='utf-8') as f:
#             f.write(danmu_data)
#         print(f"弹幕数据已保存到: {self.output_file}")

#     def run(self):
#         """执行下载任务"""
#         try:
#             print("开始获取视频ID...")
#             tvid = self.extract_video_id()
#             if not tvid:
#                 print("错误: 无法获取 tvid")
#                 return

#             print(f"获取到视频ID: {tvid}")
#             print("获取视频时长...")
#             duration = self.get_duration(tvid)
#             if duration <= 0:
#                 print("警告: 无法获取视频时长，默认抓取2小时弹幕")
#                 duration = self.MAX_DURATION

#             print(f"视频时长: {duration}秒")
#             total_parts = math.ceil(duration / 300)
#             print(f"需要下载的弹幕分段数: {total_parts}")

#             all_danmu_raw = []
#             for part in range(1, total_parts + 1):
#                 print(f"正在下载第 {part}/{total_parts} 段弹幕...")
#                 part_data = self.fetch_danmaku_segment(tvid, part)
#                 if part_data:
#                     all_danmu_raw.append(part_data)
#                 time.sleep(0.1)  # 避免请求过于频繁

#             combined_danmu = "\n".join(all_danmu_raw)
#             self.save_danmu_to_txt(combined_danmu)
#             print("弹幕下载完成!")

#         except Exception as e:
#             print(f"爱奇艺弹幕下载出错: {str(e)}")

# if __name__ == "__main__":
#     # 使用示例
#     video_url = "https://www.iqiyi.com/v_19rrnfnjyw.html?s3=pca_115_IP_card&s4=0&vfrmblk=pca_115_IP_card&vfrm=3&s2=3&vfrmrst=0"
#     output_file = "danmu.txt"
    
#     downloader = IqiyiDanmuDownloader(video_url, output_file)
#     downloader.run()

# import json
# import base64
# import time
# import string
# import random
# import hashlib
# import requests
# import re
# from time import mktime, strptime
# from selenium import webdriver
# from selenium.webdriver.chrome.options import Options

# class YoukuDanmuDownloader:
#     """优酷弹幕原始数据下载器"""
    
#     def __init__(self, video_url, output_file="youku_danmu.txt"):
#         self.url = video_url
#         self.output_file = output_file
#         self.running = True

#     def stop(self):
#         self.running = False

#     def extract_video_id(self):
#         """从URL中提取vid"""
#         match = re.search(r'id_(X[\w=]+)\.html', self.url)
#         return match.group(1) if match else None

#     def gen_guid(self, length=22):
#         """生成随机guid"""
#         return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

#     def get_sign(self, token, t, appkey, data):
#         """生成签名"""
#         s = f"{token}&{t}&{appkey}&{data}"
#         return hashlib.md5(s.encode('utf-8')).hexdigest()

#     def get_youku_cookie_str(self, wait_time=5):
#         """使用Selenium获取优酷cookie"""
#         cookie_dict = {}
#         options = Options()
#         options.add_argument('--headless')
#         options.add_argument('--disable-gpu')
        
#         driver = webdriver.Chrome(options=options)
#         try:
#             driver.get("https://www.youku.com")
#             time.sleep(wait_time)
            
#             cookies = driver.get_cookies()
#             for cookie in cookies:
#                 name = cookie.get('name')
#                 value = cookie.get('value')
#                 if name in ['_m_h5_tk', '_m_h5_tk_enc']:
#                     cookie_dict[name] = value
#         finally:
#             driver.quit()
        
#         return "; ".join(f"{k}={v}" for k, v in cookie_dict.items())

#     def get_youku_duration(self):
#         """
#         获取优酷视频时长（单位：秒）
#         参数:
#             url: 优酷视频播放页链接
#         返回:
#             视频时长（秒，int类型）或 None（获取失败时）
#         """
#         headers = {
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
#             'Accept-Language': 'zh-CN,zh;q=0.9',
#             'Referer': 'https://www.youku.com/'
#         }
        
#         try:
#             response = requests.get(self.url, headers=headers, timeout=10)
#             response.raise_for_status()
#             html_content = response.text
#             # 先尝试常见的seconds字段
#             pattern = r'(?:seconds|"seconds")\s*[:=]\s*"(\d+)"'
#             match = re.search(pattern, html_content)
#             if match:
#                 return int(match.group(1))
#             # 尝试其他字段
#             backup_patterns = [
#                 r'"duration"\s*:\s*(\d+)',
#                 r'"videoDuration"\s*:\s*(\d+)',
#                 r'"time"\s*:\s*"(\d+)"'
#             ]
#             for pattern in backup_patterns:
#                 match = re.search(pattern, html_content)
#                 if match:
#                     return int(match.group(1))
#             return None
#         except requests.exceptions.RequestException as e:
#             print(f"网络请求失败: {e}")
#             return None
#         except Exception as e:
#             print(f"解析错误: {e}")
#             return None

#     def save_raw_data(self, data):
#         """保存原始数据到文件"""
#         with open(self.output_file, 'w', encoding='utf-8') as f:
#             if isinstance(data, list):
#                 for item in data:
#                     f.write(json.dumps(item, ensure_ascii=False) + "\n")
#             else:
#                 f.write(data)
#         print(f"原始弹幕数据已保存到: {self.output_file}")

#     def run(self):
#         """执行下载任务"""
#         try:
#             print("开始获取视频ID...")
#             self.vid = self.extract_video_id()
#             if not self.vid:
#                 print("错误: 无法从URL中提取优酷视频ID")
#                 return
            
#             print(f"获取到视频ID: {self.vid}")
#             print("获取视频时长...")
#             duration = self.get_youku_duration()
#             if duration is None or duration <= 0:
#                 print("无法获取视频时长信息")
#                 return
#             duration_minutes = max(1, duration // 60 + 1)
#             print(f"视频时长: {duration_minutes}分钟")
            
#             appKey = '24679788'
#             salt = "MkmC9SoIw6xCkSKHhJ7b5D2r51kBiREr"
            
#             print("获取优酷Cookie...")
#             cookie_str = self.get_youku_cookie_str()
#             if not cookie_str:
#                 print("错误: 无法获取优酷Cookie")
#                 return
            
#             token = cookie_str.split("_m_h5_tk=")[1].split("_")[0]
#             guid = self.gen_guid()
            
#             raw_data = []  # 存储原始数据
            
#             for minute in range(duration_minutes):
#                 if not self.running:
#                     break
                
#                 print(f"正在下载第 {minute+1}/{duration_minutes} 分钟弹幕...")
                
#                 ctime = int(time.time() * 1000)
#                 data_dict = {
#                     "ctime": ctime,
#                     "ctype": 10004,
#                     "cver": "v1.0",
#                     "guid": guid,
#                     "mat": minute,
#                     "mcount": 1,
#                     "pid": 0,
#                     "sver": "3.1.0",
#                     "type": 1,
#                     "vid": self.vid
#                 }

#                 msg_json = json.dumps(data_dict, separators=(',', ':'))
#                 msg_base64 = base64.b64encode(msg_json.encode('utf-8')).decode('utf-8')
#                 sign_msg = hashlib.md5((msg_base64 + salt).encode('utf-8')).hexdigest()

#                 post_data = {
#                     **data_dict,
#                     "msg": msg_base64,
#                     "sign": sign_msg
#                 }

#                 post_data_json = json.dumps(post_data, separators=(',', ':'))
#                 sign = self.get_sign(token, ctime, appKey, post_data_json)

#                 params = {
#                     "jsv": "2.6.1",
#                     "appKey": appKey,
#                     "t": ctime,
#                     "sign": sign,
#                     "api": "mopen.youku.danmu.list",
#                     "v": "1.0",
#                     "type": "originaljson",
#                     "timeout": "20000",
#                     "dataType": "jsonp"
#                 }

#                 headers = {
#                     "User-Agent": "Mozilla/5.0",
#                     "Content-Type": "application/x-www-form-urlencoded",
#                     "Cookie": cookie_str
#                 }

#                 resp = requests.post(
#                     "https://acs.youku.com/h5/mopen.youku.danmu.list/1.0/",
#                     params=params,
#                     data={"data": post_data_json},
#                     headers=headers,
#                     timeout=10
#                 )
                
#                 # 保存原始响应数据
#                 raw_response = {
#                     "minute": minute,
#                     "response_text": resp.text,
#                     "status_code": resp.status_code
#                 }
#                 raw_data.append(raw_response)
                
#                 time.sleep(0.5)  # 避免请求过于频繁
            
#             self.save_raw_data(raw_data)
#             print("优酷弹幕原始数据下载完成!")
            
#         except Exception as e:
#             print(f"优酷弹幕下载出错: {str(e)}")

# if __name__ == "__main__":
#     # 使用示例
#     video_url = "https://v.youku.com/v_show/id_XMzMzNTc4NTU1Mg==.html?s=cc003400962411de83b1"
#     output_file = "youku_danmu.txt"
    
#     downloader = YoukuDanmuDownloader(video_url, output_file)
#     try:
#         downloader.run()
#     except KeyboardInterrupt:
#         downloader.stop()
#         print("程序已停止")