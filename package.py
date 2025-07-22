# import PyInstaller.__main__

# # 这里的是不需要打包进去的三方模块，可以减少软件包的体积
# excluded_modules = [
#     "scipy",
#     "matplotlib",
# ]

# append_string = []
# for mod in excluded_modules:
#     append_string += [f'--exclude-module={mod}']

# PyInstaller.__main__.run([
#     '-y',  # 如果dist文件夹内已经存在生成文件，则不询问用户，直接覆盖
#     # '-p', 'src', # 设置 Python 导入模块的路径（和设置 PYTHONPATH 环境变量的作用相似）。也可使用路径分隔符（Windows 使用分号;，Linux 使用冒号:）来分隔多个路径
#     'main.py',  # 主程序入口
#     # '--onedir',  # -D 文件夹
#     '--onefile', # -F 单文件
#     # '--nowindowed', # -c 无窗口
#     '--windowed',  # -w 有窗口
#     '-n', 'xTools',
#     '-i', 'ui/res/logo.ico',
#     '--add-data=ui/res;ui/res',  # 用法：pyinstaller main.py –add-data=src;dest。windows以;分割，mac,linux以:分割
#     *append_string
# ])

import PyInstaller.__main__
import os
import platform

# === 设置参数 ===
ENTRY_FILE = 'main.py'  # 入口文件名
APP_NAME = 'DanmuTools'     # 生成的可执行文件名
ICON_PATH = './ui/res/bug-report.ico'  # 图标路径
RESOURCE_PATH = 'ui/res'  # 需要打包进去的静态资源目录

# === Windows使用 ; 分隔，其他使用 : 分隔 ===
sep = ';' if platform.system() == 'Windows' else ':'

# 不需要打包的三方库，减少体积
excluded_modules = [
    'scipy',
    'matplotlib',
    'tkinter',
    'numpy',
    'pandas',
    'Jinja2',
    'pytest',
    'IPython',
    'unittest',
    'pydoc',
    'xmlrpc',
    'sqlite3',
    'distutils',
    'test',
    'turtle',
]

# 拼接参数
exclude_args = [f'--exclude-module={mod}' for mod in excluded_modules]

PyInstaller.__main__.run([
    '-y',  # 自动覆盖旧文件
    '--onefile',  # 打包为单文件
    '--windowed',  # 不弹出控制台
    '-n', APP_NAME,
    '-i', ICON_PATH,
    '--add-data=ui/res;ui/res',  # 加载资源文件夹
    ENTRY_FILE,
    *exclude_args
])
