# DanmuTools 弹幕下载工具

🎬 **DanmuTools** 是一个支持多平台弹幕抓取的桌面工具，适用于视频分析、弹幕可视化、评论研究等场景。现已支持 **爱奇艺、哔哩哔哩（B站）、优酷、腾讯视频** 四大主流平台。

## 支持平台

- 爱奇艺（iqiyi.com）
- 哔哩哔哩（bilibili.com）
- 优酷（youku.com）
- 腾讯视频（v.qq.com）

## 功能特色

- 自动识别视频链接并解析弹幕数据
- 实时抓取进度显示
- 弹幕导出为标准 XML（兼容 Bilibili 本地播放器）
- 图形化界面（基于 PyQt5）
- 抓取任务多线程执行，界面流畅不卡顿

## 安装依赖

建议使用 Python 3.9 及以上版本，并推荐虚拟环境：

```bash
pip install -r requirements.txt
```

## 使用方法

### 启动图形界面

```bash
python main.py
```
<img width="666" height="339" alt="image" src="https://github.com/user-attachments/assets/b87738fc-7892-41db-a4e8-105aca990312" />


### 操作流程

1. 粘贴视频链接，并选择平台（可自动识别）
2. 设置弹幕保存路径
3. 点击“开始下载”，实时查看进度
4. 下载完成后，弹幕以 `.xml` 格式保存

## 项目结构
```
DanmuTools/
├── main.py                  # 主程序入口（含 GUI）
├── core/
│   ├── base.py              # BaseFetcher 抽象类
│   ├── bilibili.py          # B站弹幕抓取器
│   ├── iqiyi.py             # 爱奇艺弹幕抓取器
│   ├── tencent.py           # 腾讯视频弹幕抓取器
│   └── youku.py             # 优酷弹幕抓取器
│   └── utils.py             # 工具类函数
├── ui/                      # 图标、样式资源
└── README.md
```

## 示例链接

B站：https://www.bilibili.com/video/BV1cwKAz3EmJ/?spm_id_from=333.1007.tianma.1-1-1.click

腾讯：https://v.qq.com/x/cover/mzc00200fr1ry1o/m00441h6knj.html

爱奇艺：https://www.iqiyi.com/v_19rrnfnjyw.html?s3=pca_115_IP_card&s4=0&vfrmblk=pca_115_IP_card&vfrm=3&s2=3&vfrmrst=0

优酷：https://v.youku.com/v_show/id_XMzMzNTc4NTU1Mg==.html?s=cc003400962411de83b1

## 开发说明

- 所有弹幕抓取器均继承自 `BaseFetcher`，并实现统一的接口
- 图形界面基于 PyQt5，抓取任务使用 QThread 保证界面不卡顿

## License

本项目仅供学习和研究使用，禁止商业用途。详情见 LICENSE 文件。

---
