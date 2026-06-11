# ClipTranslate 重构设计方案

## 背景

ClipTranslate 是一个基于腾讯云 TMT 的剪贴板快捷翻译工具。当前代码存在严重 bug（线程启动方式错误、JSON 注入风险）、架构问题（全局变量泛滥、UI 与逻辑耦合）和质量问题（无类型注解、无日志、缺少入口保护）。

## 目标

1. 修复所有严重 bug
2. 采用 MVC 分层架构，实现高内聚、低耦合
3. 提升代码可测试性和可维护性
4. 添加类型注解和日志系统
5. 保持现有功能不变

## 新文件架构

```
ClipTranslate/
├── main.py              # 应用入口，负责组装各模块
├── config.py            # 配置管理：读写 config.ini、路径处理
├── translator.py        # 翻译核心：腾讯云 TMT API 封装
├── app_ui.py            # GUI：customtkinter 界面（Application 类）
├── notifier.py          # 通知：Windows Toast 封装
├── ClipTranslate.py     # 保留原入口（兼容旧打包方式），内部转发到 main
└── resource/
    └── config.ini
```

## 模块设计

### 1. config.py — 配置管理

**职责**：配置文件的读写、默认值管理、配置验证、跨平台路径处理。

**类**：`ConfigManager`

| 属性/方法 | 签名 | 说明 |
|-----------|------|------|
| `DEFAULT_CONFIG` | `dict[str, str]` | 默认配置字典 |
| `SUPPORTED_LANGUAGES` | `list[str]` | 支持的目标语言列表 |
| `__init__` | `config_path: str \| Path \| None = None` | 初始化，自动确保配置文件存在 |
| `config_file` | `property -> Path` | 配置文件 Path 对象（只读） |
| `load` | `() -> dict[str, str]` | 加载配置并返回字典 |
| `save` | `(data: dict[str, str]) -> None` | 保存配置到文件 |
| `ensure_exists` | `() -> None` | 配置文件不存在时创建默认配置 |
| `validate` | `(data: dict[str, str]) -> list[str]` | 验证配置，返回错误信息列表 |

**路径处理**：使用 `pathlib.Path` 替代字符串拼接，确保跨平台兼容（Windows / Linux / macOS）。

### 2. translator.py — 翻译核心

**职责**：腾讯云 TMT API 调用、剪贴板操作、键盘模拟、快捷键监听。

**类 1**：`TranslateConfig`（`@dataclass`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `secret_id` | `str` | 腾讯云 SecretId |
| `secret_key` | `str` | 腾讯云 SecretKey |
| `project_id` | `str` | 腾讯云 ProjectId |
| `target_lang` | `str` | 目标语言代码 |

**类 2**：`TranslationEngine`

| 属性/方法 | 签名 | 说明 |
|-----------|------|------|
| `API_VERSION` | `str = "2018-03-21"` | TMT API 版本（类常量） |
| `REGION` | `str = "ap-guangzhou"` | 腾讯云地域（类常量） |
| `ENDPOINT` | `str = "tmt.tencentcloudapi.com"` | API 端点（类常量） |
| `SERVICE` | `str = "tmt"` | 服务名称（类常量） |
| `__init__` | `(config: TranslateConfig) -> None` | 初始化凭据 |
| `translate` | `(text: str) -> str \| None` | 翻译文本，成功返回结果，失败返回 None 并记录日志 |

**关键修复**：
- 使用 `json.dumps()` 构建请求参数，彻底消除 JSON 注入风险和 `JSONDecodeError` 误报。
- 异常处理区分：腾讯云 SDK 异常（配置错误）、网络异常、空结果异常。

**类 3**：`ClipboardTranslator`

| 属性/方法 | 签名 | 说明 |
|-----------|------|------|
| `__init__` | `(config: TranslateConfig, notifier: Callable[[str], None] \| None = None) -> None` | 初始化引擎和键盘控制器 |
| `hotkey` | `property -> str` | 当前绑定的快捷键 |
| `hotkey.setter` | `(value: str) -> None` | 更换快捷键时自动重新绑定 |
| `start` | `() -> None` | 启动快捷键监听（非阻塞，内部使用 `keyboard.add_hotkey`） |
| `stop` | `() -> None` | 停止快捷键监听（`keyboard.remove_all_hotkeys`） |
| `change_hotkey` | `(new_hotkey: str) -> None` | 外部调用更换快捷键（兼容旧接口） |
| `_execute` | `() -> None` | 执行复制→翻译→粘贴流程（私有） |

**关键修复**：
- **请求锁**：使用 `threading.Lock()` 防止连续请求，解决 TODO 中的问题。
- **剪贴板状态保存**：在执行前保存原始剪贴板内容，异常时恢复，避免破坏用户剪贴板。
- **键盘模拟容错**：`copy()` 和 `paste()` 添加异常捕获。
- **正确的线程启动**：`target=self.start`（不带括号）。

### 3. notifier.py — 通知封装

**职责**：统一通知接口，便于未来扩展（如支持 macOS/Linux 通知）。

**类**：`Notifier`

| 属性/方法 | 签名 | 说明 |
|-----------|------|------|
| `APP_NAME` | `str = "ClipTranslate"` | 应用名称（类常量） |
| `DEFAULT_ICON` | `str = "resource/ui.png"` | 默认图标路径（类常量） |
| `__init__` | `(icon_path: str \| None = None) -> None` | 初始化 WindowsToaster |
| `notify` | `(message: str) -> None` | 发送系统通知 |

### 4. app_ui.py — GUI 界面

**职责**：所有 customtkinter UI 组件的创建和管理，不包含业务逻辑。

**类**：`ClipTranslateApp`

| 属性/方法 | 签名 | 说明 |
|-----------|------|------|
| `__init__` | `() -> None` | 初始化窗口、加载配置、创建模块实例 |
| `_build_ui` | `() -> None` | 构建所有 UI 组件 |
| `_load_settings` | `() -> None` | 从 ConfigManager 加载配置到 UI 控件 |
| `_save_settings` | `() -> None` | 从 UI 控件读取并保存到 ConfigManager |
| `_on_save` | `() -> None` | 保存按钮回调：保存配置 + 刷新 translator |
| `_on_set_hotkey` | `() -> None` | 设置快捷键按钮回调：读取新快捷键并更新 translator |
| `_on_toggle_theme` | `() -> None` | 切换明暗主题 |
| `_create_tray_icon` | `() -> None` | 创建系统托盘图标（后台线程） |
| `_minimize_to_tray` | `() -> None` | 窗口最小化时隐藏到托盘 |
| `_show_popup` | `(message: str, duration: int = 2000) -> None` | 显示临时无边框弹窗 |
| `run` | `() -> None` | 启动主循环和状态检查 |

**设计要点**：
- 所有 UI 控件为实例属性（非全局变量）。
- `translator` 和 `config_manager` 为实例属性，通过依赖注入组装。
- `refresh_class()` 改为直接更新 `translator.config` 和 `translator.hotkey`，不重新创建实例。
- 窗口状态检查使用 `app.after()` 而非独立线程。

### 5. main.py — 应用入口

**职责**：启动应用，提供标准入口。

```python
def main() -> None:
    app = ClipTranslateApp()
    app.run()

if __name__ == "__main__":
    main()
```

### 6. ClipTranslate.py — 兼容入口

**职责**：保留原文件名以便旧打包脚本兼容，内部转发到 `main.py`。

```python
from main import main

if __name__ == "__main__":
    main()
```

## 数据流

```
用户操作 → app_ui.py (GUI 事件)
    ↓
config.py (读写配置)
    ↓
translator.py (调用 TMT API)
    ↓
notifier.py (通知结果)
    ↓
剪贴板 / 系统通知
```

## 关键修复清单

| 原问题 | 修复方式 |
|--------|----------|
| `target=translator.set_hotkey()` 带括号 | `target=translator.start` 不带括号 |
| JSON 字符串拼接注入 | `json.dumps()` 构建参数 |
| `time.sleep(1)` 脆弱同步 | 保存/恢复剪贴板状态 + 增加重试机制 |
| 全局变量 | 全部封装为实例属性 |
| 无入口保护 | `main.py` 添加 `if __name__ == "__main__":` |
| 重新创建 translator 实例 | 直接更新 `config` 和 `hotkey` 属性 |
| 重复翻译无保护 | `threading.Lock()` 请求锁 |
| 反斜杠路径 | `pathlib.Path` 跨平台路径 |
| `Image.LANCZOS` 兼容性 | 兼容 Pillow 9 和 10+ |
| 无日志 | 引入 `logging` 模块，按级别输出 |

## 非功能要求

- **Python 版本**：>= 3.9（保留 `dict[str, str]` 等内置泛型）
- **向后兼容**：配置文件格式不变，用户配置自动迁移
- **打包兼容**：保留 `ClipTranslate.py` 文件名，旧打包命令仍然有效
- **日志路径**：`resource/app.log`，按天轮转
