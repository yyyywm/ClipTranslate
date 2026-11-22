# 快捷翻译工具

欢迎使用 **快捷翻译工具**，这是一个高效、易用的翻译辅助软件，旨在帮助用户通过快捷键快速翻译文本。

## 特性

- **快捷键激活**：一键激活翻译功能，无需离开当前工作环境。
- **多语言支持**：支持中文与多种语言的互译。
- **智能识别**：自动检测文本语言，无需手动设置源语言。
- **一键粘贴**：翻译结果直接粘贴到所选位置，方便粘贴使用。

## 使用方法

### 已发布版本

1. 解压下载下来的压缩包，双击exe文件即可运行。
2. 选择文本并使用快捷键（默认为`Ctrl+i`），翻译结果将自动粘贴。

### 源码自行食用

```bash
git clone git@github.com:shengxi-rise/ClipTranslate.git
pip install -r requirements.txt
python ClipTranslate.py
```

#### 应用打包

在 Windows 上安装项目依赖后，从项目根目录打开 PowerShell 并运行以下命令。

```powershell
python -m pip install "pyinstaller>=6"
python -m PyInstaller --noconfirm --windowed --icon "resource\logo.ico" --add-data "resource\logo.ico:resource" --add-data "resource\ui.png:resource" ClipTranslate.py
```

`--icon` 设置 EXE 的图标。两项 `--add-data` 将窗口、托盘和通知使用的图标放到包内的 `resource` 目录。打包完成后，运行 `dist\ClipTranslate\ClipTranslate.exe`。发布时请分发整个 `dist\ClipTranslate` 目录，保留其中的 `_internal` 目录。

`--noconfirm` 会替换现有的 `dist\ClipTranslate`。如果需要保留旧 EXE 的设置，请先备份 `dist\ClipTranslate\resource\config.ini` 到输出目录之外，打包完成后再恢复。源码目录的 `resource\config.ini` 和 EXE 的配置分别保存。配置文件可能含有 API Key，请勿将其随发布包分发。

### 配置参数获取方法如下👇

1. 登录腾讯云，打开**腾讯机器翻译（TMT）**，开启即可。每个用户每个月有**500万字符**的免费文本翻译额度。

   ![image-20240821174125886](https://gitee.com/shengxi-rise/img/raw/master/ywmpic/202408211741013.png)

2. 进入**访问管理**界面，创建**API访问密钥**。注意secretkey只有在创建完成的时候才会显示，没记下的话需要自己通过算法计算。忘记密钥还是建议重新创建

   ![image-20240821174916908](https://gitee.com/shengxi-rise/img/raw/master/ywmpic/202408211749038.png)

## 依赖

- **`customtkinter`**：现代风格的 `tkinter` 扩展库，用于创建美观的 GUI。
- **`keyboard`**：监听和捕捉键盘事件，支持快捷键绑定。
- **`Pillow`**：处理图像的库，用于加载、操作和保存图像。
- **`pynput`**：模拟和监控键盘输入操作。
- **`pyperclip`**：与剪贴板交互，用于复制和粘贴文本。
- **`pystray`**：创建系统托盘图标和菜单，支持托盘交互。
- **`tencentcloud_sdk_python_common`**：腾讯云公共 SDK 库，用于处理 API 通信。
- **`tencentcloud_sdk_python_tmt`**：腾讯云机器翻译 SDK，用于调用翻译服务。

## 软件截图

![image-20240831172328346](https://gitee.com/shengxi-rise/img/raw/master/ywmpic/202408311723410.png)

## 开发者

- **Name**: ywm
- **Email**: [ywmssh@gmail.com](mailto:ywmssh@gmail.com)

## 开发状态

- [x] 基本功能已经实现
- [x] 用图形库封装，提高用户自定义程度
- [x] 应用打包
- [x] 构建action自动发布

## TODO

### feature

- 自动检验密钥是否正确，添加反馈弹窗
- ~~允许用户自定义目标语言~~
- 用户可自行选择粘贴文本，还是直接翻译
- 使用无限免费的API进行封装
- ......

### refactor

- 重构代码，将UI和逻辑都封装成类，简洁更方便调用

### BUG

- 使用某些快捷键的时候，存在翻译不了的情况

