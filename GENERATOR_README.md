# RavenLaunch CN Generator — B-mode experimental build

This tool creates a separate localized EXE from a user-selected `IchaLaunch.exe`; the official input is **never overwritten**. It does not use PID/HWND, cross-process overlay windows, or a hardcoded version/SHA allowlist.

## Implementation

- Read the PyInstaller CArchive and find one `run` entry compiled for CPython 3.14.
- Insert a small pre-import hook into a new `run` code object; embed the **entire unchanged original run CodeType** as a constant.
- The hook intercepts the *existing import machinery* when the original launcher later imports `ichalaunch.ui.main_window` and `ichalaunch.ui.widgets.launch_button`.
- Patch custom draw routines `NavTabButton.paintEvent` and `LaunchButton._paint_label`, only during drawing. `text()` returns Chinese while drawing, and still returns the original English in all other business paths.
- Rebuild CArchive entries, offsets, compressed lengths, TOC and cookie; preserve the original bootloader, PYZ, Qt assets and unrelated modules.
- Validate the rebuilt archive and script CodeType before writing a new EXE. Fail closed on unknown structural layouts; the parser checks **technical format compatibility**, not vendor version identity.

Current dictionary: HOME→主页, ADDONS→插件, CLIENT→客户端, SETTINGS→设置, PLAY→开始游戏, INSTALL→安装, UPDATE→更新.

## Usage

GUI: run `RavenLaunch-CN-Generator.exe`, choose the official EXE, choose an unused output path, click **生成中文版 EXE**.

Developer CLI with Python 3.14:

```powershell
python tools/cn_generator_core.py "C:\path\IchaLaunch.exe" --out "C:\path\IchaLaunch-CN.exe"
```

## Limitations and verification

- Currently supports PyInstaller CArchive with **CPython 3.14**, a `run` script and the investigated `ichalaunch` widget class names. There is **no manufacturer-version allowlist**. Other Python versions require a separate code-object serialization engine.
- Version update may alter class names, import order or custom painting. In such cases the hook is best-effort; it does not intentionally break game launching, but **runtime success is not guaranteed**.
- A static EXE creation test is not proof of a working GUI. Windows functional tests must verify appearance, button clicks, DPI, window drag, application update flows and actual game launching.
- Do not claim the generated EXE has been functionally validated until a Windows desktop test is actually performed.
- Generated EXEs do not preserve original publisher signatures. Keep the original executable and launch the modified EXE only if you trust the selected source.

## Same-version launcher update false positive (2026-11-17)

The official `ichalaunch.core.self_update` contains a rule to offer an update when the semantic version matches but the EXE SHA-256 differs (legitimate same-version hotfix). A generated localized EXE always has a different digest, so previously it falsely offered `Update RavenLaunch to v1.6.28` even when the selected official source was already v1.6.28.

The generator now embeds the **selected original EXE SHA-256** in the generated bootstrap and, at import-time, replaces only `ichalaunch.core.self_update._running_launcher_sha256` for the official release pin comparison. It does **not** alter the existing vendor `update_should_offer` predicate, remove version checks, bypass downloaded-update checksum verification, or suppress genuine newer versions / upstream hotfixes. This is an import-time compatibility adapter, **not** an installer file-integrity proof. If a newer official update is offered, installing it will replace the localized EXE and the user must run the generator against the new official file again.

Static and synthetic CI testing is not evidence that the real Windows launcher update check or its cache handling has been verified. Test on the original and new generated executable, ideally after normal cache refresh.

## 词库格式（简化版）

`translations/zh_CN.json` 现在是单层英文→中文映射，不使用 `schema`、`nav` 或 `launch` 分类；每行一组：

```json
{
  "HOME": "主页",
  "ADDONS": "插件",
  "CLIENT": "客户端",
  "SETTINGS": "设置",
  "PLAY": "开始游戏",
  "INSTALL": "安装",
  "UPDATE": "更新"
}
```

生成器 GUI 的「自定义词库（可选）」可以直接选择此格式的 UTF-8 JSON。CLI 用 `--dictionary translations/zh_CN.json` 指定文件。未选时使用打包进生成器的内置词库；更新外部 JSON 无需重新编译生成器。

**边界：** 词库只提供英文/中文对应关系；当前 Hook 仍只在 `NavTabButton.paintEvent` 和 `LaunchButton._paint_label` 的绘制过程中读取翻译。不代表添加 SETTINGS 页面普通标签即可自动替换，也不会全局拦截 `QWidget.setText` 或改动业务状态。重复键、空值、嵌套对象等不合法输入会被拒绝。

Glyphshift 的 JSON / CSV 原文可由 `tools/translation_collector.py` 导出到审核候选列表，审核后将英文/中文键值复制进这个简单词库；导入器不自动写入正式词库。详情见 `docs/GLYPHSHIFT_RESEARCH.md`。


## B2.2 — SETTINGS 静态 UI 文本首批适配（2026-11-17）

基于用户 Windows SETTINGS 截图中的确定英文，单层词库新增 `GAME CLIENT`、`GAME LOCATION`、`ADDONS FOLDER`、`EXISTING INSTALL`、`INSTALL...`、`BROWSE...`、`VERIFY`、`RESET CLIENT LINK` 以及部分设置说明文字；目前共 21 个英文→中文词条。

`tools/cn_generator_core.py` 在 `ichalaunch.ui.pages.settings` 被导入后给 `SettingsPage` 安装作用域受限的后处理适配器：构造完成、`refresh()`、`_refresh_game_client()` 后，递归检索本页面的 `QLabel`、`QAbstractButton`，仅对代码里明确允许的 SETTINGS 静态英文词条应用词库译文。

- 不修改原版 EXE，仍然在生成的新 EXE 中接入。
- **不是全局 setText Hook**：不处理输入框、窗口外的状态栏或任意动态业务文字；更新用源文件 SHA 的修复保持原样。
- 为了防止使用者在 JSON 中添加业务状态词后发生错误，SETTINGS 应用位置仍受独立的静态白名单约束；添加新词条不保证即刻生效。
- `SETTINGS` 标题若不属于 SettingsPage 的 QLabel，需要后续按真实 Qt 对象结构适配。
- 当前 SETTINGS 的人工翻译是否全部匹配真实 Qt `.text()`、布局是否截断以及所有按钮能否正常响应，**等待用户 Windows 实机回归**。CI 仅用合成 QWidget 测试自定义适配器。

## B2.2 首次实机反馈后的修复：实际 Qt 字符串与自定义控件

用户 Windows 运行 B2.2 的截图证实：导航按钮仍为中文，但 SETTINGS 页面几乎完全保持英文，包括 `GAME CLIENT`、`BROWSE...`、`VERIFY`、`SAVE`。这是**实际 GUI 回归失败**，不得将先前 CI 成功理解为页面汉化成功。

已直接从相同官方 SHA 的 `IchaLaunch.exe` → PyInstaller PYZ → `ichalaunch.ui.pages.settings` 的 `SettingsPage.__init__` CodeType 常量核实实际英文键：
- `Settings`、`Game client`、`Game location`、`AddOns folder`、`Browse…`、`Install…`、`Verify`、`Reset Client Link`、`Save` 等是**源码原文**；截图中许多大写字母是渲染效果，而不是输入到 Qt 的实际 `.text()`。
- 1.12 / 1.14 选项等字符串内部有双空格，省略号使用 Unicode U+2026；旧 JSON 中全大写、ASCII `...`、单空格无法匹配。
- 设置页导入 `GradientLabel`、`GluePanelButton`、`ThemeRadioButton`、`ThemeCheckBox`；先前扫描范围仅 QLabel/QAbstractButton，会遗漏自定义 QWidget 实现。
- 已更换 `_CN_SETTINGS_UI_KEYS` 为来自原始 CodeType 的精确原文，扩展为设置页内 QWidget 子控件遍历，但**只允许标准 QLabel/QAbstractButton 或四种上述白名单自绘类**、只允许列入 SETTINGS 静态文本白名单的键；明确拒绝输入框和业务状态文本，不使用全局 setText Hook。
- 单层 `translations/zh_CN.json` 保持 `"英文": "中文"` 格式，按原始常量修正了键，新增 Save、维护/更新等静态词条；本次补充的 Python 3.14 合成 GUI 控件测试覆盖大小写、自绘按钮、输入框排除、refresh 后翻译。
- **仍未 Windows 实机回归验证新版 SETTINGS 截图**。如仍显示英文，需先确认运行中的新版 EXE 对应新版生成器，接着查找实际类 API 是否缺少 `text()/setText()`，再考虑局部类适配，不能盲目添加词条。
