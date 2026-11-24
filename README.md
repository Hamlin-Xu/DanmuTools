# DanmuTools 弹幕下载工具

🎬 **DanmuTools** 是一个支持多平台弹幕抓取的桌面工具，适用于视频分析、弹幕可视化、评论研究等场景。现已支持 **爱奇艺、哔哩哔哩（B站）、优酷、腾讯视频** 四大主流平台，并可下载剧集全集弹幕。

## 支持平台

| 平台 | 单集下载 | 全集下载 | 按剧集名称搜索 |
| --- | :---: | :---: | :---: |
| 爱奇艺（iqiyi.com） | ✅ | ✅ | ✅ |
| 哔哩哔哩（bilibili.com） | ✅ | ✅ | ✅ |
| 优酷（youku.com） | ✅ | ✅ | ✅ |
| 腾讯视频（v.qq.com） | ✅ | ✅ | ✅ |

## 功能特色

- 自动识别视频链接所属平台并解析弹幕数据
- **两种输入方式**：粘贴视频链接，或直接输入剧集名称搜索后下载（链接解析不到时可用名称方式）
- **全集下载**：自动枚举剧集全部分集，逐集下载弹幕并按集分文件保存
- 实时抓取进度显示，单集失败不会中断整个全集任务
- 弹幕导出为标准 XML（兼容 Bilibili 本地播放器）
- 图形化界面（基于 PyQt5），抓取任务多线程执行，界面流畅不卡顿

> **全集下载实现说明**：
> - 腾讯视频：通过 `PageServer/GetPageData` 分集列表接口枚举；
> - 优酷：从播放页 `__INITIAL_DATA__` 取 `showId`，再走开放 API `shows/videos.json` 枚举；
> - 爱奇艺：以专辑 ID 调 `tvg/v2/selector` 枚举（链接不含专辑 ID 时自动按剧名搜索）；
> - B站：番剧走 `pgc/view/web/season`，UP 主分P合集走 `web-interface/view`。
>
> 若某平台接口临时变动，勾选全集时会自动降级为当前单集下载并给出提示。

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

**方式一：链接下载**

1. 输入方式选择「链接下载」，粘贴视频/剧集链接，选择平台（也可保留「自动检测」）
2. 设置弹幕保存路径
3. **（可选）勾选“全集下载”**：输入番剧/剧集链接时，会下载全部集数弹幕，并自动按集保存到 `保存路径/剧名/NN_集标题.xml`
4. 点击“开始下载”，实时查看进度

**方式二：按剧集名称搜索**

1. 输入方式切换为「按剧集名称搜索」，输入剧集名称（如 `名侦探柯南`、`狂飙`、`龙族`）
2. 选择平台（选择具体平台可加快搜索；保留「自动检测」则四平台一起搜）
3. 点击「搜索剧集」，在弹出的候选列表里选择目标剧集（显示平台、年份、类型、集数）
4. 勾选“全集下载”后点击“开始下载”，即按集保存全部弹幕

> 勾选“全集下载”后，若枚举不到分集（如普通单集视频、未开播剧集），会自动按单集下载。

## 项目结构
```
DanmuTools/
├── main.py                  # 主程序入口
├── core/
│   ├── base.py              # BaseFetcher 抽象类（单集/全集通用流程、搜索解析）
│   ├── search.py            # 四平台剧集搜索与候选排序
│   ├── bilibili.py          # B站弹幕抓取器（番剧/分P合集）
│   ├── iqiyi.py             # 爱奇艺弹幕抓取器
│   ├── tencent.py           # 腾讯视频弹幕抓取器
│   ├── youku.py             # 优酷弹幕抓取器
│   └── utils.py             # 工具函数（XML 导出）
├── ui/
│   └── main_window.py       # 主窗口与搜索选择对话框
└── README.md
```

## 示例链接

B站：https://www.bilibili.com/bangumi/play/ep8014873

腾讯：https://v.qq.com/x/cover/mzc00200fr1ry1o/m00441h6knj.html

爱奇艺：https://www.iqiyi.com/v_19rrjzcqm4.html

优酷：https://v.youku.com/v_show/id_XMzMzNTc4NTU1Mg==.html

## 开发说明

- 所有弹幕抓取器均继承自 `BaseFetcher`，实现统一接口：`extract_video_id()`、`get_video_info()`、`_run_single()`、`enumerate_episodes()`、`_fetch_episode(ep)`
- 全集流程由 `BaseFetcher._run_series()` 调度：先 `enumerate_episodes()` 枚举分集，再逐集调用 `_fetch_episode()` 复用单集逻辑
- 名称搜索由 `core/search.py` 统一实现：各平台搜索接口 → `pick_best()` 按标题匹配度（并跳过预约中/无分集的条目）挑选最佳剧集 → 交给对应 `BaseFetcher` 枚举分集
- 腾讯视频：`vid` 从播放链接 `/x/cover/{cid}/{vid}.html` 提取，分集与时长来自 `GetPageData`，弹幕按 30 秒分段拉取
- 优酷：纯 `requests` 获取 `_m_h5_tk` token 并签名请求弹幕接口，**不依赖 Selenium / Chrome**
- 爱奇艺：分集通过 `tvg/v2/selector`（按 key 排序 + md5 签名）获取，弹幕按 300 秒一段的 `.z` 文件分段请求
- 图形界面基于 PyQt5，抓取任务使用 QThread 保证界面不卡顿

## License

本项目仅供学习和研究使用，禁止商业用途。详情见 LICENSE 文件。

---
