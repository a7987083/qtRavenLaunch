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

## B2.3 — 从原版 EXE 导出 zh_CN.json

Windows GUI 新增「**导出原始字符串**」按钮：

1. 选择未修改的官方 `IchaLaunch.exe`。
2. 点击「导出原始字符串」；输出文件默认 `zh_CN.json`，允许自选路径。
3. 程序**离线**扫描 PyInstaller CArchive → `PYZ.pyz` → `ichalaunch.ui.*` 和 `ichalaunch.app` 的 CPython 3.14 CodeType 常量，严格保留字符串的大小写、标点、空格；排除明显 URL、路径、标识符、资源文件名等，词条仍然是**待审 UI 候选**，而不是全部 UI 或安全可替换的文字。
4. 输出 JSON 一行一条：`"原始英文": ""`。填好译文后，直接在 GUI「自定义词库（可选）」选择同一个文件，生成新的 `IchaLaunch-CN.exe`。
5. 未来官方更新，再次选择同一 `zh_CN.json` 导出，提示用户后**保留已经填写的译文，添加新候选为空值**；旧条目不会删除。

开发者命令：
```powershell
py -3.14 tools/extract_strings.py "C:\\path\\IchaLaunch.exe" --out zh_CN.json
```

不启动原版 EXE，不执行其 CodeType，不连接网络，不修改原版文件。PYZ 模块解码失败时停止导出并保留旧词库，避免悄悄丢词条。Python 版本仍严格要求 3.14（打包的 Windows 生成器内自带）。

**重要：** 单层 JSON 不表示全局字符串替换。只有当前 import hook 支持的导航、启动按钮和部分 SETTINGS 文本会显示译文；填入某条新原文不保证生成的程序能显示它。导出也无法保证覆盖运行时拼接、网络文本、图像字及特殊自绘。脚本输出的模块数是静态扫描模块数，不是 UI 已汉化数量。

字典允许译文为空；空译文会被生成器跳过，保留英文，不会把界面文字绘制为空白。生成的 EXE 官方更新 SHA 兼容逻辑维持不变。词库限制为 2 MiB，重复原文键仍拒绝。

## 2026-11-17 用户反馈：无效 JSON 反斜杠与 SETTINGS 文字遗漏

用户使用 B2.3 生成器及自行编辑的 `zh_CN.json` 时看到 `JSONDecodeError: Invalid \\escape: line 1241 column 25 (char 45435)`。这表示 JSON 解析失败，**不是** CArchive 或生成 EXE 失败；当前缺少用户实际第 1241 行内容，不能确认具体破坏者。常见原因为用户手工添加 Windows 路径（如 `C:\\Games`）时没有双重转义。导出器使用 `json.dumps`，正常生成的 JSON 会正确编码反斜杠。

`tools/cn_generator_core.py` 已将解析失败转为人类可读的行列号及邻近字符串提示。处理失败保留原始 JSON 和原版 EXE，绝不盲目自动修复含糊的转义；用户需修改出错行或上传实际 JSON 才能定位。

另一个真实截图显示 SETTINGS 字段提示：

```text
Defaults to Interface\AddOns under the game folder when you set or change the game path. Override only if your addons live elsewhere.
```

原文已在原版 `PYZ.pyz` → `ichalaunch.ui.pages.settings.SettingsPage.__init__` CodeType 常量中确认，不是截图猜测。现在它及其他十余条已核实的 SETTINGS 静态原文已加入局部 `_CN_SETTINGS_UI_KEYS` 和单层词库 `translations/zh_CN.json`。

**保留安全约束：** SETTINGS 适配器只处理 SettingsPage 子控件中的受控静态文字，不改动输入字段、状态栏、业务路由和启动器更新 SHA 逻辑。新增键不保证所有其他 Qt 自绘/动态文字自动汉化。GUI 实机显示及换词库后的游戏功能仍需 Windows 回归。
