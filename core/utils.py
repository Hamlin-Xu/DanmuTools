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
