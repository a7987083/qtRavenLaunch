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

## B2.4.1 — 扩大 Qt 显示层适配与可观察性

生成器新增**按页面作用域**的 GUI 文本适配器，模块映射与真实原版 Python 3.14 字节码核对：

- `ichalaunch.ui.pages.home.HomePage`
- `ichalaunch.ui.pages.client.ClientPage`
- `ichalaunch.ui.pages.addons.AddonsPage`
- `ichalaunch.ui.pages.addons_114.Raven114AddonsPanel`
- 原有 `ichalaunch.ui.pages.settings.SettingsPage` 适配改进

仅对页内 `QLabel`、`QAbstractButton` 和若干已知自绘 Qt 控件尝试翻译。来源必须是该页构造函数 `__init__.__code__.co_consts` 中出现过的**静态原文**（HOME 额外包含确认的 `refresh/_fill_whats_new`），且原文在用户填好的单层词库中有非空译文。跳过输入框、对象名表明是 status/progress/loading/path/state 的控件、`PLAY/UPDATE/INSTALL` 等关键业务状态值。显示范围仍有限，未做全局 `setText()` 劫持。UI 布局和绘制外观保持原有 Qt 机制。

**运行时翻译命中日志**：用户启动新生成的 `IchaLaunch-CN.exe`，程序在 `%LOCALAPPDATA%\\RavenLaunch-CN\\translation-coverage.jsonl`（无法使用该目录时回退至 TEMP）记录最近会话的页适配状态、命中词条和控件适配失败。不会记录输入框内容或动态私密文本。GUI 增加「查看翻译诊断」按钮：从最后一个 `session-start` 开始统计，并输出 `translation-coverage-summary.json`，记录 `ready_pages`、`applied_keys`、`adapter_warnings` 和 `unobserved_translated_keys`。

**注意**：`unobserved_translated_keys` 仅表示**本次运行尚未观察到**，包括尚未打开页面的词条。静态原文提取 ≠ 运行时命中 ≠ 真实 Windows UI 完整回归。当前默认词库补充 HOME / ADDONS 已在原版 CodeType 中出现过的界面标签（共 67 条）。

确认这次更新是否生效的最小步骤：使用最新生成器生成不同文件名的 `IchaLaunch-CN.exe`；打开 HOME、SETTINGS、CLIENT、ADDONS 并观察中文；在生成器点击「查看翻译诊断」，检查适配器 ready 和 applied。保留官方原版 EXE；检查启动器更新提示是否仍正常。

此阶段未获得真实 Windows GUI 对这些新 Hook 的回归证据，仅 Python3.14 合成 Qt 控件测试/Windows CI 构建可用于确认语法和模拟行为。

## B2.4.2 — 绘制期 GlueComboBox 筛选汉化与 CLIENT 动态刷新

结合用户真实 Windows 截图和 `translation-coverage-summary.json`（5 个页面适配器 ready、67 个去重翻译键命中、一个 `TitleLockup` 控件不支持）：

1. **ADDONS 下拉筛选**：原版 `ichalaunch.ui.widgets.glue_combo.GlueComboBox.paintEvent` 从 `currentText()` 取文字并用 QPainter.drawText 绘制；原版 `AddonsPage._apply_filter_mode` 同样读取 `currentText()` 来决定 Installed/Available 过滤。不能直接改 model `DisplayRole`、`setItemText` 或返回中文给业务代码。
2. 增加 `_cn_patch_glue_combo`，只在 `paintEvent` 作用域内返回中文 `currentText()`；下拉框使用 `QStyledItemDelegate.initStyleOption` 修改绘制选项的 `option.text`，**不修改 Qt Model ItemData、原生 `currentText()`、`itemText()`**。若未来版本的下拉框已有非默认 delegate，安全跳过并写 `combo-delegate-skipped` 诊断，不覆盖别人的 Delegate。
3. **CLIENT 动态子界面**：原版 3.14 字节码报告 `ClientPage._add_presets_page`、`refresh_from_settings`、`refresh_plan`、`_refresh_patch9_banner` 涉及正文构建/刷新。增加这些受限构造/刷新方法的静态词常量到页面译文候选，并在完成后重新扫描 page scoped QLabel/QAbstractButton/自绘白名单。状态栏/输入框路径、进度对象和必要业务状态仍排除；不承诺所有远端/动态字符串都覆盖。
4. **1.14 动态列表**：`Raven114AddonsPanel._build_rows`、`refresh_status` 后重新执行 page scoped 扫描，但插件描述可能来自远端 catalog，静态词库不会自动覆盖。
5. 新增 Python 3.14 模拟 Qt 测试：筛选 `currentText()/itemText()` 均返回原始英文、绘制才中文、下拉 `option.text` 中文、CLIENT 的 helper/刷新静态标签可更新而 `client_status` 保持原值。合成测试不能代替真实 PySide6 Windows GUI 回归。
6. **GAME UPDATE 弹窗尚未安全适配**：截图确认文字未翻译，但弹窗创建/动态 %d 拼接需要按原版 3.14 具体调用链定位，不能全局拦截 QDialog/QMessageBox 状态文案。下轮优先解析该弹窗。
7. 当前版本不是全界面完整汉化。任何“已命中”仅表示触发过 Python 翻译，不证明最终 Qt 视觉、点击、筛选、下拉都已经实机通过。

实机回归应重点验证：ADDONS 的 Installed/Available/Update Available/All 四个筛选，选择后仍显示正确列表；ClientPage 预设/Launch/Performance 页显示、搜索及按钮行为；启动器更新 SHA 误报仍不复现；报错时提供 `%LOCALAPPDATA%\\RavenLaunch-CN\\translation-coverage.jsonl`。

## CLIENT 实机漏翻译反馈与 B2.4.3 限定修复（2026-11-17）

用户最新两张 Windows 实机截图证明 CLIENT 页面下列项目仍英文：侧边 Presets/Launch/Performance / Fixes/HD Graphics/Visual / QoL/Advanced，预设说明 `Choose a preset to configure client mods automatically. Manual changes switch to Custom — use Apply Changes to install.`、`Client only — no preset-managed mods enabled.`，底部动态 `Pending: Install Auto-clear WDB cache`。部分操作按钮和主标题已经中文，说明旧页面 Hook 并非整体失败。

对照用户此前上传的真实 `translation-coverage-summary.json`：`Presets` 与完整预设说明**不在当时有效词库的已翻译键中**；`Launch`/Performance / Fixes/HD Graphics/Visual / QoL/Advanced/Client only… 等已有译文但未命中。旧 `_cn_static_literals()` 只收集浅层 `co_consts`，且 UI helper 筛选过窄，可能漏掉嵌套 UI 构造方法与 sidebars。

本轮：
- `tools/cn_generator_core.py` 中 `_cn_static_literals` 改为递归读取 CodeType 和 tuple/frozenset 的字符串常量，`_cn_client_ui_literals` 从 `ClientPage` 中带 `_build_/_add_/_create_/_refresh_/refresh/_sync_/_update_/show` 前缀的 UI 方法收集静态候选，排除已知状态方法 `set_check_status/set_checking/set_updates/clear_pending_update/_sync_status_host/_sync_game_lock_actions`。仍仅检查限定页面与安全控件。
- 针对 `ichalaunch.ui.widgets.glue_panel_button.GluePanelButton` 增加 import-time `paintEvent` 范围的 `text()` 译文适配，同时 CLIENT 页扫描跳过该类，以避免直接 `setText` 修改左侧导航业务值。这个点目前经过合成 mock 测试，**尚未核实目标真实 GluePanelButton.paintEvent 是否以 self.text() 获取绘制文本**，需实机验证；即使导入 patch 失败也会 fail-open 保留英文并在诊断记 `adapter-error`。
- 单层 `translations/zh_CN.json` 从 67 扩至 86 条，新增截图真实文案和 Presets/Launch/Performance / Fixes/HD Graphics/Visual / QoL/Advanced 等。**用户选择外部自定义 JSON 时不会自动合并仓库的新增译文**，需要自行合入相应新键；`""` 空译文仍跳过。
- 新增 Python3.14 合成测试：嵌套 UI 函数常量能收集但状态 setter 常量不应收集；GluePanelButton.paintEvent 临时显示中文，调用前后 `text()` 始终英文。第一处真实 CI 错误：测试样本使用双转义 `\\n` 而非换行，Run `44052350382` 在 `fixture.py` SyntaxError；Commit `43ef06ba` 修复后 Run `44052492032` 成功。
- **未改动 Pending 动态状态、GAME UPDATE 弹窗或 1.14 外部插件说明的业务文字**。Pending 属于动态字符串，应查清生成位置和读回路径，不能直接全局替换 QLabels；不应把这条描述成已修复。
- 实机验证：用最新 generator 重新生成新 EXE，确认使用的 JSON 包含相关英文键；打开 CLIENT 页并切换左侧 5+ 分类；检查侧边显示和导航功能，查看 `translation-coverage.jsonl` 的 `paint-adapter-ready` / `adapter-error`。若左侧仍英文，需要继续用真实 Python 3.14 字节码核对 GluePanelButton 的绘制字段，不能猜测其 API。

## B2.4.6 — CLIENT 模组说明 / Launch 选项回归修复

用户真实 Windows 截图证明上一版 CatNavButton 已经成功将左侧 Presets/Launch/Performance/HD Graphics/Visual/Advanced 显示成中文，导航问题得到首次实机可视确认。当前未完成的是右侧 CLIENT 模组列表（Vanilla Tweaks V2 描述和 Not installed）以及 Launch 页面的一批自绘复选框文字。

本次按原版 `IchaLaunch.exe` 中 `PYZ.pyz` 可解析 CodeType 元数据确认：
- `ichalaunch.ui.widgets.theme_checkbox.ThemeCheckBox.paintEvent` 在 Python 绘制过程中访问 `self.text()` 并调用 `QPainter.drawText`；
- `ichalaunch.ui.widgets.theme_radio.ThemeRadioButton.paintEvent` 使用同类路径。
新增两个专属 Import Hook，使用现有 `_cn_patch_widget` 仅在 `paintEvent` 中把 `text()` 暂时返回词库中文，函数外一律保持英文，包括 `isChecked()` 勾选业务状态。**是否所有截图中的控件均属于这两类，仍需实机观察，CI 只模拟该行为。**

审计发现当前 GitHub 内置 `translations/zh_CN.json` 并没有用户截图的 8 条 Launch 复选框原文；已经按真实截图补齐。若使用外部自定义 JSON，需要由用户合入这些键值，生成器绝不改写其原词库。

用户截图 `Patches WoW.exe (not a DLL)...` 的 Vanilla Tweaks 说明来自 CLIENT 模组信息，不一定在 ClientPage 构造代码常量中。新增极窄 `_CN_CLIENT_DETAIL_KEYS`，**只允许两条已确认的纯说明字符串** 在 `ClientPage` 下的 QLabel 上绕过构造常量约束应用词库，仍不碰行状态 `Not installed`、模组名版本及动态业务值。其它目录/下载远端说明仍未覆盖。

补 `tests/test_cn_generator.py` 模拟自绘 Checkbox/Radio 保持勾选和值，和 CLIENT 说明 QLabel 翻译但跳过状态/模组标识。
需要用户 Windows 重新生成并打开 Launch/Performance 页面，检查中文截断、复选框可点击、勾选值正确、模组信息清单及无更新误报；本轮未实机验证，不可宣称全部修好。

## B2.4.7 — Config.wtf / dxvk.conf 专用设置弹窗翻译（2026-11-17）

用户 Windows 实机截图确认 `ConfigWtfSettingsDialog` 与 `DxvkConfSettingsDialog` 两个自定义弹窗的标题、说明、各配置项标签仍大量显示英文；此前 CLIENT 左侧分类实机汉化正常。新一轮原版 `PYZ.pyz` 的静态元数据再次核对：真实弹窗类定义于 `ichalaunch.ui.widgets.dialogs`，配置项分别来自 `ichalaunch.game.config_wtf_edits.CVAR_SPECS`、`ichalaunch.game.dxvk_conf_edits.DXVK_SPECS`，Specs 提供展示用途的 `label`、`group`、`hint` 与用于配置写入的 `name` 等字段。

- 新增 `_cn_patch_config_editors` Import Hook：对两种专用弹窗的 `__init__` 做最小后处理，仅扫描其 `QLabel` 子控件，只有内容属于经过批准的固定弹窗介绍/标题或 Spec 的 `label/group/hint` 并存在非空词库翻译时才调用 `setText()`。**不修改** Spec 对象、CVAR/DXVK 配置键、滑块数值、编辑字段、QComboBox 项目或 currentData。
- 硬性限制：这不是所有配置弹窗全控件汉化。对自绘控件的额外覆盖仍需真实 Windows 验证；只有截图中已确认或 PYZ Spec 确认的英文键才应认为已知。
- `translations/zh_CN.json` 增加约 46 个 Config.wtf/DXVK label、group、标题及简介译文，仍使用用户指定的单层 `"English":"中文"` 格式。外部自定义 JSON 不会自动获得这些新增条目，必须自行合并或选择未指定自定义词库使用内置字典。
- `tests/test_cn_generator.py` 增加合成 Qt QLabel/两个配置弹窗测试：期待只翻译展示标签，不修改组合框实际数据、滑块值及 Spec.name。首个真实 CI 错误 Run `44061061730`：原代码把 constructor 所有字符串常量作为候选，导致合成测试里的无关业务 QLabel 被翻译。后续 `75f03512` 将范围严格限制为 Spec 展示字段及四个明确介绍/标题，消除危险的构造函数字符串全量翻译。
- 运行时日志新增 `config-label-applied`，`tools/translation_diagnostics.py` 汇总可计入实际适配命中；如果没打开弹窗则该项不应期望出现。
- **未验证**：真实 Windows 上弹窗视觉中文显示、长说明是否截断、关闭与 Save 是否正常、Config.wtf/dxvk.conf 文件实际写入内容。CI synthetic mock 不能代替实机验证。
- CLIENT `Vanilla Tweaks V2` 的长说明在用户截图中依旧英文，虽然内置词库已有该原文并限制允许 QLabel 翻译，推断可能是动态创建/不同控件类型，**尚未解决**；应优先定位真实行组件和刷新调用链，不能宣称已修复。

## B2.4.8 — 四类原生确认弹窗的显示层翻译

用户的七张 Windows 截图（其中三类重复）归并为四个真实弹窗：
1. `Addon folder name mismatch`：文件夹名称与 .toc 的动态确认；
2. `Recommended addon forks`：推荐分支说明与每条已安装/推荐仓库信息；
3. `GAME UPDATE`：不匹配的官方游戏文件数量、更新说明与稍后/立即更新；
4. `Reset Client Link`：清除保存的 WoW 路径的确认。

根据目标 `IchaLaunch.exe` 的 `PYZ.pyz` 真实字节（不以 Python3.13 反汇编 3.14 opcode）：`ichalaunch.ui.widgets.metal_framed_dialog.MetalFramedDialog.__init__(parent,title,text)` 负责建立 `QLabel` 标题 `ThemedDialogTitle` 和正文 `ThemedDialogBody`。在 `ichalaunch.ui.widgets.dialogs` 可核对 `RecommendedForkSwapDialog`、`confirm_addon_toc_renamer` 和对应英文标题/完整说明常量；在 `ichalaunch.ui.main_window` 可核对 `GAME UPDATE`、`Later`、`Update now`、`Reset Client Link` 和正文常量。

`tools/cn_generator_core.py` 新增：
- `_cn_patch_metal_prompts` 仅对原生 `MetalFramedDialog` 完成初始化后的标题/正文 `QLabel` 做检查；`_cn_patch_dialog_family` 在 `ThemedDialog` / `RecommendedForkSwapDialog` 完整构建后补扫一次，以覆盖推荐分支行。
- 必须匹配 **四类明确的英文标题**，且只允许对应弹窗已确认的固定正文、标题或格式模板；不依赖全局 QDialog Hook，不翻译任意 QLabel。
- 动态模板将 `120 published game file(s)...` 中数量、`Folder is ... but the .toc is ... Rename ...` 中的实际文件夹/.toc/目标名称原样插入译文；推荐分支行只翻译 `Installed:`、`Recommended:` 前缀，保留仓库标识。动态原文不写入诊断日志（仅记 title/body 事件类型）。
- 原有 `GluePanelButton` 的绘制期翻译处理 `Later`、`Update now` 等已有真实按钮文案。DialogResult/Yes/No、回调、文件夹重命名行为、更新业务判断及原版 SHA 修复均未修改。
- 默认 `translations/zh_CN.json` 继续是用户指定的单层 JSON，增加四类标题、完整静态说明和带 `{count}/{folder}/{toc}/{target}` 参数的模板。
- `tests/test_cn_generator.py` 增加针对四类弹窗模拟 Qt QLabel 的回归：文件夹/特殊字符不变、计数参数不变、分段 reset 正文可汉化、推荐仓库名称不变、无关标题不受影响。最初几个 CI 失败源于模拟 Reset 两段文案及推荐说明非原版完整字符串，与白名单精确匹配不一致；已改为真实常量及限定分段逻辑，不能为通过测试而放宽业务字符串保护。

此阶段**没有真实 Windows 启动器完整弹窗实机回归**；Python3.14 CI 只证明合成控件行为、打包成功。用户需核对四种弹窗的标题/正文及按钮响应，尤其查看长文本是否被裁切与更新按钮是否仍正确。

## 可选登录服务器地址：realmList 定向改写（2026-11-17）

生成器 GUI 新增「登录服务器地址（可选，留空使用原版）」输入框。只接受普通 ASCII 域名或 IPv4，例如 apac.capycraft.io；**不填时完全保留官方原版内置 realmlist 资源**。CLI 对应参数为 --login-server apac.capycraft.io。拒绝 URL/路径/端口、引号、换行等无效输入。

根据真正的官方 IchaLaunch.exe（SHA-256 e54556fa8711fa577d48b38fe2501d0e41f315b973651799d753929ed13c1697）的 PyInstaller CArchive 字节，确认资源 ichalaunch\\data\\realmlist.wtf，原文 realmList 与 patchList 均为 logon.ravencraft.io。

填写地址时，只改生成版 EXE 中该归档条目的 SET realmList，例如 apac.capycraft.io；**不改 patchList**，不更换客户端资源、游戏文件、更新地址、签名文件或其它 DLL。原版 EXE 不变，原版 SHA 更新比较修复保留。重封装器 assemble() 更新归档偏移，输出回读检查 realmList，原子写入文件。缺少唯一资源、格式异常、输入无效时拒绝输出。

**重要限制：** 修改内置资源还不能证明原版启动器运行时会把该配置写入已安装的客户端，也不证明目标服务器兼容。RavenCraft 的更新/文件校验仍可能覆盖不兼容客户端，避免对 Capycraft 游戏目录使用其更新或修复。Windows CI 仅验证合成归档的资源替换、CRLF 保留、空值完全保留、非法参数拒绝、原版源文件不变和 patchList 不变。真实 Windows 运行及登录未验证。
