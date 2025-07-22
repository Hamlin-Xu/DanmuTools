import os
import time
import requests
import re
from datetime import timedelta
import xml.etree.ElementTree as ET
from typing import List, Dict

def save_as_bilibili_xml(danmu: List[Dict], filename: str):
    """
    保存为B站兼容的XML格式
    
    :param danmu: 弹幕数据列表
    :param filename: 输出文件名
    """
    if not filename.endswith(".xml"):
        filename += ".xml"
    
    # 确保目录存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # 创建XML结构
    root = ET.Element('i')
    ET.SubElement(root, "chatserver").text = "chat.bilibili.com"
    ET.SubElement(root, "chatid").text = "10000"
    ET.SubElement(root, "mission").text = "0"
    ET.SubElement(root, "maxlimit").text = "8000"
    ET.SubElement(root, "source").text = "e-r"
    
    # 添加弹幕数据
    for item in danmu:
        time_sec = float(item.get("time_offset", 0)) / 1000.0
        danmu_type = item.get("mode", 1)
        font_size = item.get("font_size", 25)
        color = item.get("color", 16777215)
        timestamp = item.get("timestamp", int(time.time()))
        user_hash = "0"
        p_attr = f"{time_sec:.3f},{danmu_type},{font_size},{color},{timestamp},0,{user_hash},0"
        
        d = ET.SubElement(root, "d")
        d.set("p", p_attr)
        d.text = item.get("content", "")
    
    # 保存文件
    tree = ET.ElementTree(root)
    tree.write(filename, encoding='utf-8', xml_declaration=True)


def get_youku_duration(url):
    """
    获取优酷视频时长（单位：秒）
    参数:
        url: 优酷视频播放页链接
    返回:
        视频时长（秒，int类型）或 None（获取失败时）
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.youku.com/'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text
        # 先尝试常见的seconds字段
        pattern = r'(?:seconds|"seconds")\s*[:=]\s*"(\d+)"'
        match = re.search(pattern, html_content)
        if match:
            return int(match.group(1))
        # 尝试其他字段
        backup_patterns = [
            r'"duration"\s*:\s*(\d+)',
            r'"videoDuration"\s*:\s*(\d+)',
            r'"time"\s*:\s*"(\d+)"'
        ]
        for pattern in backup_patterns:
            match = re.search(pattern, html_content)
            if match:
                return int(match.group(1))
        return None
    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
        return None
    except Exception as e:
        print(f"解析错误: {e}")
        return None