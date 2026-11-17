# HANDOFF — RavenLaunch-CN-Generator (2026-11-17)

## Stable baseline and scope
User requested **B mode**: a standalone tool that accepts the official `IchaLaunch.exe` and generates a different `IchaLaunch-CN.exe`. It should not manually ship a fixed translated launcher. User explicitly rejected a vendor version detector/SHA allowlist.

Current repository: `a7987083/qtRavenLaunch`, branch `main`.
**Important repository history event:** at 2026-11-17 06:50:59Z, an externally created commit `c28f82f22ab1724ab4d18b84bae8d00ef1949bbc` titled `Add files via upload` changed branch history to a minimal generator tree. Earlier 2026-11-17 overlay-analysis history is no longer reachable from current `main`. Do not silently force-push or rewrite it; work with the current tree and verify HEAD afresh.

## Implemented
- `tools/cn_generator_core.py`: reads a Windows PyInstaller CPython 3.14 CArchive, finds unique `run` code entry, serializes an import-hook bootstrap containing the unchanged original run code object, rebuilds TOC and cookie into a separate EXE. Rejects overwriting input/existing output. No SHA allowlist.
- `tools/cn_generator_gui.py`: standalone Tkinter generator wizard (select source, choose output, generate, show errors).
- `tests/test_cn_generator.py`: synthetic PyInstaller test cases covering CodeType embedding, original untouched, output collision rejection and invalid EXE rejection.
- `.github/workflows/build-cn-generator.yml`: Windows 3.14 unit test + PyInstaller onefile build.
- `GENERATOR_README.md`: architecture and usage.

## Localization design (experimental)
- Intercepts the original importer for `ichalaunch.ui.main_window.NavTabButton` and `ichalaunch.ui.widgets.launch_button.LaunchButton`.
- Wraps Python custom paint methods `paintEvent` and `_paint_label`; returns translated `text()` **only while painting**. Outside paint, original English text remains available to the game logic.
- Initial dictionary: HOME→主页, ADDONS→插件, CLIENT→客户端, SETTINGS→设置, PLAY→开始游戏, INSTALL→安装, UPDATE→更新.
- Preserves original PYZ, resources, QT libraries, other scripts and bootloader; no cross-process overlay, PID/HWND tracking or DLL injection.

## Verified and unverified
- Initial GitHub Actions build run `44034042888` succeeded for commit `29f62853dc044fcafddb167dd1f6d604805b5587`: Windows CPython 3.14 syntax/unit tests and PyInstaller standalone build. Artifact id `14305804839`, SHA-256 `275d46020711e123f3447886630e7d19357514b2628471cdf102d039eca1573f`, 13,384,281 bytes.
- Local downloaded build: `/mnt/data/RavenLaunch-CN-Generator/RavenLaunch-CN-Generator.exe`.
- **Not verified:** Running generator against the user's actual original EXE on Windows, generated launcher opening, Qt paint replacement, game launch, update behavior, DPI/dragging, real-machine GUI regression.
- Full original EXE is in current-session container at `/mnt/data/IchaLaunch.exe` but local container lacks Python 3.14 and Windows runtime. The CI used only synthetic archives.

## Next action
Run isolated generator against the real original executable on a trusted Windows system and capture first real failure, if any. If the launcher opens, verify only selected navigation and launch text first, then expand dictionary. Do not call CI success a functional validation. Do not restore previous lost Git history by force-push.

## 2026-11-17 原版无更新 / 汉化版提示“Update RavenLaunch to v1.6.28”修复
- 用户 Windows 截图确认：原版不提示更新，汉化版在更新按钮 ToolTip 提示 `Update RavenLaunch to v1.6.28`。
- 真实原版 PYZ `ichalaunch.core.self_update` 解压后静态字符串证据：`Same semver, different EXE hash ... quick-fix without a version bump.`、`True for a newer pin, or a same-version hotfix with a new sha256.`、`_running_launcher_sha256`、`update_should_offer`、`read_cached_launcher_release`。推断当前问题是生成中文 EXE 后本机 SHA 改变，官方同版本 hotfix 比较被触发；未在 Windows 跟踪确认完整条件分支。
- `tools/cn_generator_core.py` 修改：为新生成 EXE 的 bootstrap 嵌入输入官方 EXE 的 SHA-256；拦截 `ichalaunch.core.self_update` 导入，仅替代 `_running_launcher_sha256` 的比较结果为**未修改的输入原版 SHA**。保留 `update_should_offer`、远端 pin、下载文件校验、其他更新功能。现有自动更新若执行，会覆盖汉化版，须重新生成。
- Core commit `6ff78700`；tests `7a1a359c`；README `c3318c3c`。新增 Python3.14 synthetic test，运行成功；GitHub Actions Run `44035628254` completed success，artifact `14307566182`（`RavenLaunch-CN-Generator-Windows`）， ZIP SHA-256 `3e812cb51eb16e71f664528c631191cbdcf05a3746485fb272bac883c45f9b95`。
- **未验证**：用户 Windows 重新生成版是否不再误报、真实 GUI 更新通知处理、缓存一致性；必须让用户实际重生成并启动检查，不能称已实机回归通过。

## 2026-11-17 B2.1 独立词库 + Glyphshift 采集接口
- B2.1 基于 `main` HEAD `7f76a4ca` 开始，没有改写历史；Glyphshift 上游官方仓库 `glyphshift/glyphshift` 的 JSON/CSV 词条 schema 已核对：JSON `entries` 数组/根数组；CSV `source,translation`。
- 新增 `tools/translation_collector.py`：用独立 Python 代码导入 Glyphshift JSON/CSV，输出 `review_required:true` 的候选词条，重复冲突和非法格式拒绝处理；**不会直接覆盖 live 翻译词库**，不能进行全局 Qt setText 替换。新增 `tests/test_translation_collector.py` 共六个测试。
- 新增 `translations/zh_CN.json`：schema 1，`nav` / `launch` 两组已经验证的自绘按钮翻译；没有添加 SETTINGS 其它未验证控件。
- `tools/cn_generator_core.py` 新增 `load_translations()`：从独立 JSON 加载，严格 schema、大小和字符串校验，编译进现有 bootstrap 原生 Qt paint Hook；原版保护和 SHA-256 更新误报修复保持不变。CLI 可 `--dictionary <path>`。
- `tools/cn_generator_gui.py` 新增可选外部词库选择器；未指定时使用 Windows PyInstaller onefile 内置 `zh_CN.json`。
- `.github/workflows/build-cn-generator.yml` 更新：Python 3.14 执行所有 `test_*.py`，打包时 `--add-data "translations/zh_CN.json;translations"`。
- `docs/GLYPHSHIFT_RESEARCH.md` 和 `GENERATOR_README.md` 记录已核对的上游实际格式、导入及边界。
- 尚未对 Glyphshift + IchaLaunch 进行真实 Windows 采集，也未在真实 Windows GUI 回归带词库的新生成器；不得声称此项实机验证通过。
- 下一阶段 B2.2 才汉化 SETTINGS 普通 QWidget；必须先定位 Qt 显示层和业务文本比较，不允许未经审查把全部 `setText` 翻译。

## 2026-11-17 B2.2 SETTINGS + 扁平 JSON 词库
- 用户要求的词库正式改为**单层 UTF-8 JSON**：一行一条 `"HOME": "主页"`，不再包含 `schema`、`nav`、`launch` 等元信息/分类。修改 `translations/zh_CN.json`（现共 21 项）、`tools/cn_generator_core.py`、`tests/test_cn_generator.py`；测试会拒绝重复键、嵌套对象、空翻译。仅更改词库格式，不改原版更新 SHA workaround 和打包算法。
- 旧版扁平化早期两个提交 CI 失败是因为测试仍使用旧 schema；随后 `940a3063` 更新测试，Windows Actions Run `44038495381` success。不得把中间失败视作当前构建状态。
- B2.2 在 `tools/cn_generator_core.py` 增加`ichalaunch.ui.pages.settings` 专属 import hook：替换 `SettingsPage.__init__` 及 `refresh`/`_refresh_game_client` 的后处理；仅检索本页 `QLabel` / `QAbstractButton`，只对 `_CN_SETTINGS_UI_KEYS` 白名单中的精确静态文字应用扁平 JSON 译文。此为首次有限度修改 QLabel/QAbstractButton.text()，**需要真实业务回归**。不全局替换 setText，不影响状态栏 / 输入框 / 其它页面。
- 根据用户 SETTINGS 截图加入 GAME CLIENT、GAME LOCATION、ADDONS FOLDER、EXISTING INSTALL、INSTALL...、BROWSE...、VERIFY、RESET CLIENT LINK 和部分英文说明。部分文字可能因为 UI 对象类别和标点不一致仍显示英文；以 Windows 运行截图定位，不做凭空宣称。
- 加入合成 Qt 测试 `test_settings_static_labels_and_refresh_only`，证明已列入白名单的标签更新、非白名单 `UPDATE` 状态保持英文。Python 3.14 Windows Actions Run `44038920863` completed/success；**实际生成 EXE 后打开 SETTINGS 页面尚未实机验证**。
- 当前工作树所有远端修改均提交 main；不要改写指定历史提交。
- 下一步：使用新版生成器，选择未经改动的原版 EXE，生成新的 IchaLaunch-CN.exe；在 Windows 依次检查 SETTINGS 标题、游戏客户端、游戏目录、按钮、刷新后文本、导航、官方更新提示状态和游戏启动。若有英文未捕获，优先检查对象类型与确切字符串，避免继续盲目添加翻译键。

## 2026-11-17 B2.2 SETTINGS 全英文实机反馈与修正
- 用户最新真实 Windows 截图：顶部旧的导航汉化仍生效；但 SETTINGS 正文 `SETTINGS`, `GAME CLIENT`, `GAME LOCATION`, `BROWSE...`, `VERIFY` 和 `SAVE` 均为英文。此为此前 B2.2 **GUI 回归失败**，此前 CI 不等同实机成功。
- 以原样本 `/mnt/data/IchaLaunch.exe` （SHA-256 `e54556fa8711fa577d48b38fe2501d0e41f315b973651799d753929ed13c1697`）提取 `PYZ.pyz` 中 `ichalaunch.ui.pages.settings` code object；3.13 marshal 可读取该 SettingsPage 模块的 co_consts/元信息但**不用于解释 Python 3.14 指令**。
- 确证 SETTINGS 实际字符串：`Settings`, `Game client`, `Game location`, `AddOns folder`, `Browse…`, `Install…`, `Verify`, `Reset Client Link`, `Save`; 1.12/1.14 描述使用双空格，ellipsis 是 U+2026。旧版字典源键误按截图转为全大写/ASCII 三点，因此不匹配。
- 模块 co_names 同时显示 `GradientLabel`, `GluePanelButton`, `ThemeRadioButton`, `ThemeCheckBox`，旧 SETTINGS 适配器仅遍历 `QLabel/QAbstractButton` 有覆盖风险。
- 新提交 `d6886091`：精确 SETTINGS 原文 allowlist、遍历 SETTINGS 页 `QWidget` descendants，仍只对 standard QLabel/QAbstractButton 或四种明确白名单 Qt 自绘控件且确切匹配静态原文时 setText。绝不全局拦截 setText，输入框和 status label 被排除。
- `d9ec3c46`：调整 `translations/zh_CN.json` 为真实 PYZ 常量键、增加 Save 等，共 34 条；保持纯单层 `"English": "中文"`，无 schema。
- `27b6047c`：Python3.14 mock Qt tests 中验证 GradientLabel/GluePanelButton/普通标签/刷新、输入框及 UPDATE 业务标签排除。
- Windows GitHub Actions `44040239729` **completed/success**，生成器构建并上传 artifact。注意中间 d688 阶段 CI fail 是旧合成测试仍使用过时字符串，已由 27b6 重新校准通过。
- 仍**未验证新版真实 Windows GUI 是否正确显示**。下一步用户用新版生成器从官方 EXE 重新生成新文件，检查 SETTINGS 对应英文变化，以及旧 SHA 更新误报不复现；若仍失败先在真实 Qt 控件核对是否支持 text/setText，避免猜测。
- 用户最后一句“其次”尚未完整表达第二个问题；等待其补充。

## 2026-11-17 B2.3 — 从官方 EXE 自动导出原文到 zh_CN.json
- 用户要求按钮「导出原始字符串」，输出标准单层 `zh_CN.json`，`"英文原文": ""` 一行一个，不含 schema/nav/launch。填写后 GUI 选同一词库生成新版 EXE。官方更新时重新导出，应保留旧译文并增量新增词条。
- `tools/extract_strings.py` 新增：要求 CPython 3.14，使用现有 `read_carchive()`，定位 `PYZ.pyz`，按 PYZ Header 12 字节偏移及 marshal TOC 提取 `ichalaunch.ui.*`、`ichalaunch.app` CodeType；递归扫描 `co_consts` / tuple 中的真实字符串，保留大小写/空格/Unicode 标点；启发式过滤明显路径、资源文件、URL 和技术标识符。**仅是 UI 候选，非完整静态/运行时内容，更不代表全部可安全替换。**
- `export_strings(source, output)` 默认合并旧词库，空译文新键追加、已翻译键保留，不删除旧键；失败时通过先扫描、临时文件、os.replace 保持原词库，禁止覆盖输入 EXE。
- `tools/cn_generator_gui.py` 增加「导出原始字符串」按钮，用户选原版后可用保存对话框决定输出路径；同名已存在时弹窗确认保留译文合并，成功后自动将输出 JSON 选为本次生成的自定义词库。
- `tools/cn_generator_core.py` 中 `load_translations()` 允许空译文，打包时过滤空词条，避免输出空标签；字典最大容量扩至 2MiB，原版更新 SHA 兼容修复/业务状态隔离保持不变。
- `tests/test_extract_strings.py` 对合成 PYZ/CArchive、嵌套 CodeType/tuple 原文、Unicode 省略号、非 UI URL 过滤、空译文、保留旧翻译、重复导出、失败不破坏旧词库、禁止覆盖执行文件等测试。Windows CI 运行 Python3.14；workflow 已编译脚本并执行 `test_*.py`，PyInstaller 可自动捆绑新增 extractor 模块。
- 截至此处代码已推送到 main；**还未在用户真实 Windows 上验证从官方 EXE 完整提取及 GUI 按钮/生成/游戏启动**。因为真实原版 EXE 未上传 GitHub CI，工作流只能运行合成归档测试。若真实文件上失败，优先以首次 Python/GUI 错误为准。
- 用户以前真实 SETTINGS 全英文的回归仍需另行实机确认修复；不要把词库增加等同于扩大 Qt Hook 覆盖。

## 2026-11-17 JSON Invalid \\escape 与 SETTINGS 漏汉化复查
- 用户真实 Windows 生成失败弹窗 `JSONDecodeError: Invalid \\escape: line 1241 column 25 (char 45435)`。根因类别：用户选中的 `zh_CN.json` **不是合法 JSON**；没有上传具体 JSON 行，不能认定是哪个反斜杠。常见路径 `C:\\Games` 在 JSON 必须写双反斜杠 `C:\\\\Games`。自动静态字符串导出器使用 json.dumps 会转义；本次不擅自损坏旧词库自动纠错。
- `tools/cn_generator_core.py` 改进 `load_translations`：捕获 json.JSONDecodeError，报告文件、行列、附近原文、可能的反斜杠问题，保留原 JSON / 目标 EXE，其他有效词库逻辑不变。新增合成测试 `test_invalid_json_escape_reports_exact_location`。
- 另一个用户 SETTINGS 截图包含 `Defaults to Interface\\AddOns under the game folder when you set or change the game path. Override only if your addons live elsewhere.`；此原始字符串已从本地真实 `/mnt/data/_tmp_original.pyz` 的 `ichalaunch.ui.pages.settings.SettingsPage.__init__.co_consts` 读取核对，非渲染猜测。
- 新增该句及 11 条核实的 SETTINGS 固定英文原文到 `_CN_SETTINGS_UI_KEYS`，对应 `translations/zh_CN.json` 中的中文译文；**依旧只对 SettingsPage 的允许控件 setText**，不全局替换；动态、自绘及输入控件不保证覆盖。
- `tests/test_cn_generator.py` 新增 fake QWidget 的长提示精确匹配回归测试；GitHub Windows Python3.14 Actions Run `44044418470` completed/success；此次 CI 不证明用户 Windows 实机 SETTING 页面已成功，需用新 EXE 实测。
- 最新修复在 main；上次 CI 成功到新代码确认后再更新具体 HEAD。用户下次反馈时优先查看 JSON 出错实际行或 Settings 实际运行截图。

## 2026-11-17 B2.4.1 Qt 显示适配扩展 / 运行时命中诊断
- 用户要求正式开始 B2.4.1，重点是让已提取/已填的翻译真正作用于更多 Qt 页面，并说明为什么未命中。依旧不修改官方原版 EXE，B 版生成器输出独立 EXE。
- 实际读取原版 `/mnt/data/_tmp_original.pyz` 的 CodeType 元数据 + Python3.14 `raven-bytecode-314(2).json` 核对：`HomePage` / `ClientPage` / `AddonsPage` / `SettingsPage` / `Raven114AddonsPanel` 是页面类。1.14 Addons 真实类名并非 `Addons114Page`，代码已更正。
- `tools/cn_generator_core.py` 扩展 import-time Qt page adapters，对 HOME/CLIENT/ADDONS/1.14 插件页，分别在初始化、显示及 refresh 时检索页内 QLabel/QAbstractButton/明确自绘类。只替换当前页面构造方法中的 Python 字符串常量（HOME 另参考 refresh/_fill_whats_new）且词库有非空翻译的静态文字。状态、进度、路径、输入框和 PLAY/UPDATE/INSTALL 业务状态明确排除；**不是全局 setText Hook**。SETTINGS 同步扩展为 __init__ 常量精确匹配和受控 tooltip 翻译。
- `translations/zh_CN.json` 从 46 扩至 67 个单层英文→中文词条；新增 HOME Register/Database/Bug Report/Installed/What's New 等和 ADDONS Installed/Available/Check Updates/Update All/Rescan Disk 等真实静态常量。未将字典格式改成 schema 分类。
- 运行时每次生成程序启动在 `%LOCALAPPDATA%/RavenLaunch-CN/translation-coverage.jsonl` 写 `session-start`，按唯一事件记录 `adapter-ready`、`adapter-missing`、`adapter-error`、`unsupported-control`、`applied`、`tooltip-applied`；不记录文本输入框的动态内容，日志写失败不影响启动器。生成器 GUI 新增「查看翻译诊断」，读取最新会话、从当前 JSON 提取有效词条，输出 `translation-coverage-summary.json`，区分实际命中、适配器错误、未观察到的已翻译词条。未观察到不等于失败，页面可能未进入。
- `tools/translation_diagnostics.py` 和 `tests/test_translation_diagnostics.py` 新增摘要器和合成测试。Python3.14 GUI stub 测试 `test_home_adapter_scoped_constructor_refresh_and_diagnostics` 与 missing-class test 通过。
- 第一处真实 CI 回归 Run `44045884870` failure：测试错误地把字面写在 HOME __init__ 中的英文当成外部动态文本，产生 expected untranslated 而实际被翻译；修正测试将该句放在外层闭包，Commit `e8dec37e`。之后 GitHub Actions Run `44046068558` success。
- 最新完整 Windows Actions Run `44046522951` completed/success：Python3.14 syntax + all synthetic tests + PyInstaller EXE build + artifact upload 通过；没有对生成后的真实游戏窗口或实机验证。
- 风险：未知自绘 QWidget 可能没有 text/setText API，日志记录 unsupported-control，不强行修改；动态进度文本和未列入 page constructor 的文字可能仍为英文；类方法级 Hook 与原版官方更新后接口差异需重新验证。业务状态逻辑和 SHA-256 误报修复未移除。
- 下一步用户本机运行最新 generator，再从未经修改的原版 EXE 生成不同输出路径、打开四页、检查视觉、拖动、更新检测和功能，点击「查看翻译诊断」上传 summary.json 或截图，定位实际未命中的控件，再小范围扩展，不盲目全局替换。

## 2026-11-17 B2.4.2：真正修复 ADDONS 筛选显示层，补 CLIENT 异步刷新
- 用户上传 8 张真实 GUI 图片和 `translation-coverage-summary.json`，诊断：`source_hash=e54556fa8711`、五个页面 ready、67 已应用、781 未观察到、唯一 warning `home/TitleLockup`。观察：ADDONS 的 Installed 等筛选按钮和下拉项仍显示英文；CLIENT 修复页左侧 Presets/Launch/Performance/HD Graphics/Advanced 等没有完全汉化；1.14 Cinder 数据描述仍英文；GAME UPDATE 弹窗标题、正文、按钮仍英文。**不能把 67 条 applied 误当 67 条视觉正确**。
- 经原版 `/mnt/data/_tmp_original.pyz` 真实 `ichalaunch.ui.widgets.glue_combo` CodeType 验证：`GlueComboBox.paintEvent` 调用 `self.currentText()` 和 QPainter.drawText；`AddonsPage._apply_filter_mode` 使用 `filter_box.currentText()` 做筛选状态判断。`GlueComboBox.__init__` 设置了 `_MarbleComboView`；该 view 没有自定义 item delegate。禁止直接 `setItemText` 修改筛选语义。
- `tools/cn_generator_core.py` 增加针对 `ichalaunch.ui.widgets.glue_combo.GlueComboBox` 的专用导入适配：`paintEvent` 期间才把 `currentText()` 返回值映射为中文，函数外保持原始英文；popup 中用独立 `QStyledItemDelegate.initStyleOption` 只改 `option.text`，不改 model DisplayRole 或 currentText/itemText。发现已存在非默认 Delegate 就 fail-open 并记 `combo-delegate-skipped`。同文件 `_cn_patch_widget` 新增 optional reader_name 参数，旧 Nav/Launch 仍按 text() 工作。`_CnFinder` 新增 glue_combo。
- CLIENT 增加 `_add_presets_page`、`refresh_from_settings`、`refresh_plan`、`_refresh_patch9_banner` 静态字符串候选，并在后三个刷新函数后进行页面范围安全重扫；1.14 插件页也在 `_build_rows`、`refresh_status` 后重扫。仅对受控 Qt QLabel/QAbstractButton/已知自绘类中精确匹配的 UI 原文尝试 setText；继续排除状态路径和输入框，未做全局 setText。
- `tests/test_cn_generator.py` 新增两个合成测试，确认 combo 按钮和 popup 中文但 currentText/itemText 原始英文不变，以及 ClientPage helper/refresh 有翻译、status 不受影响。中途测试 Python 转义书写出现真实 CI 失败，后续 `343e24de` 更正；最新含全部实现的 CI Run `44050134019` completed/success，Python3.14 tests + standalone Windows EXE build + artifact upload。
- `GENERATOR_README.md` 已记录 B2.4.2 调用链和边界。**尚未实机回归**：真实 PySide6 下 QStyledItemDelegate paint 是否匹配主题布局、四个筛选业务是否完整、ClientPage 异步子控件覆盖、游戏更新弹窗，均未在用户 Windows 验证。
- 重要首个下一任务：真实 Windows 上打开新生成的 IchaLaunch-CN.exe 的 ADDONS 筛选 Installed/Available/Update Available/All 四个选项，检验显示中文但过滤正确；再打开 CLIENT 的 Presets/Launch/Performance/HD Graphics 页面、确认是否增加实际命中。若失败，上传最新 `translation-coverage-summary.json` 和界面截图。
- GAME UPDATE 弹窗的动态数字拼接仍未进行安全适配；应以目标版真实 Py3.14 字节码定位弹窗构造函数/具体调用点，再做显示层翻译，禁止把全局 QDialog.setText 当作解决方案。

## 2026-11-17 B2.4.3 CLIENT sidebar / presets 实机漏翻译后续修复
- 用户真实 Windows CLIENT 截图明确仍为英文：侧边 `Presets`、`Launch`、`Performance / Fixes`、`HD Graphics`、`Visual / QoL`、`Advanced`；预设介绍 `Choose a preset to configure client mods automatically. Manual changes switch to Custom — use Apply Changes to install.` 和 `Client only — no preset-managed mods enabled.`；底部状态 `Pending: Install Auto-clear WDB cache`。截图中的主标题、部分按钮、Ultra versions 文字汉化已生效。
- 上一版用户 `translation-coverage-summary.json` 对照：`Launch` 等已存在非空翻译但 `unobserved`；`Presets` 和完整预设介绍在用户当时词库中缺失（不是 Hook 的证明）。
- `tools/cn_generator_core.py` `_cn_static_literals` 改为递归 Python CodeType/tuple 字符串常量扫描；`_cn_client_ui_literals` 限制性收集 ClientPage 相关 _add/_build/_create/_refresh/_sync/_update/show 主要 UI 构造函数，同时排除 set_check_status 等状态方法。额外添加 `ichalaunch.ui.widgets.glue_panel_button` 导入目标，尝试对 `GluePanelButton.paintEvent` 的 `text()` 调用使用临时中文；CLIENT 页面扫描跳过对 GluePanelButton 的 setText，以免改变业务路由。Qt paint 路径在真实目标版本**未动态证明**，须实机验证；导入失败诊断现在记录 `adapter-error`。
- `translations/zh_CN.json` 新增截图文案，词条 67→86，仍是每行 `"English":"中文"` 单层 JSON。使用外部旧词库者必须自己加入相应英文→中文键；生成器不会偷改其翻译。
- `tests/test_cn_generator.py` 新增模拟递归 UI helper 与 paint-only GluePanelButton 测试；第一处真实 CI 出错为测试代码合成 Python 时把换行误转成 `\\n` 字符，Run 44052350382 SyntaxError，Commit 43ef06ba 修正后 Run 44052492032 success。最新代码额外将导入适配异常记到本机诊断，Windows Python3.14 CI Run `44052582194` completed/success，合成 tests + 构建 EXE + artifact upload 完成。未测试真实 Windows 生成后的客户端屏幕。
- `Pending: Install Auto-clear WDB cache` 为动态状态；GAME UPDATE 弹窗和 1.14 Cinder 元数据长文仍未实现安全显示层翻译，**不要宣称已修复**。
- 下一步用户重新生成不同文件名的 EXE，检查侧边中文是否显示且页面导航/勾选仍正常；上传最新 `translation-coverage-summary.json` 或截图检查 `paint-adapter-ready` / `adapter-error`，再精准定位自绘 API。官方更新 SHA 对比修复不可删。

## 2026-11-17 B2.4.4 SETTINGS Discord Privacy 用户实机反例及修复
- 用户 Windows 实机截图：Privacy 区域首个隐私开关已中文，`Show status on Discord`、`Show character details (name, race, class, guild, zone, level)` 及 Name/Guild/Faction/Class/Level/Zone 仍英文，尽管用户使用的外部 `zh_CN.json` 中对这些字符串已有非空翻译。CLIENT Advanced 导航也依然英文，虽有 `"Advanced":"高级"`。**不要笼统归因于用户没有写 JSON**。
- 静态真实原版 `/mnt/data/_tmp_original.pyz` 的 `ichalaunch.ui.pages.settings` CodeType 可被 Python3.13 marshal 读取，用于常量元数据而非 3.14 指令解码。模块 co_consts 确认 `Show status on Discord`、`Show character details (name, race, class, guild, zone, level)` 是 **模块级常量**，模块 co_names 引用 `_DISCORD_PARENT_LABEL`、`_DISCORD_CHILD_LABEL`、`BROADCAST_FIELD_LABELS`。SettingsPage.__init__ 不直接含这两个英文常量，因此先前 `eligible_settings` 只从 init + 固定允许列表取值时不会命中。
- 修复：`tools/cn_generator_core.py` 在 SettingsPage adapter 中显式读取 module._DISCORD_PARENT_LABEL / _DISCORD_CHILD_LABEL / BROADCAST_FIELD_LABELS.values()，仅用于 SettingsPage 内 QLabel/QAbstractButton/允许类型，补 showEvent / _sync_discord_character_row 后重新适配。保持输入框、内部状态和 SHA 官方更新逻辑保护。
- `translations/zh_CN.json` 新增 9 条默认翻译，86→95（Show status, Show character details, Name, Guild, Faction, Class, Level, Zone, Show details）。使用用户外部自定义 JSON 时仍以外部内容为准，不自动合并这些默认词条。
- 新增 synthetic test `test_settings_module_global_discord_labels_and_field_refresh` 模拟真实模块字段和 Qt 控件，以及刷新后原文恢复并重新翻译。第一处真实 CI 错误 Run `44054132192` 为 `frozenset` 无 `.add()`（因 `eligible_settings = frozenset | set` 仍为 frozenset），Commit `1eb3bf03` 改为 `set(_CN_SETTINGS_UI_KEYS)` 后 Run `44054340003` success。
- 为了区分 CLIENT Advanced 绘制期是否真的读取 `text()`，`_cn_patch_widget` 仅在真实 paint 期间产生译文时写 `paint-applied` 诊断事件，`tools/translation_diagnostics.py` 把此事件算入命中汇总。**Advanced 视觉未汉化根因尚未在真实版本动态确认，不能声称已修好**。用户重新生成并运行后，可查看 `paint-applied` 是否包含 Advanced；若没有，说明该自绘路径没有调用适配的 text 方法或没有使用匹配的字典。
- 本次仅 Python3.14 Windows CI synthetic Qt tests/EXE 构建；用户真实机器的新版本仍未验证。下阶段根据 `paint-applied` 调查 GluePanelButton 实际绘制字段，避免通过修改路由用的 `text()` 破坏点击切换。

## 2026-11-17 B2.4.5 CatNavButton / Advanced 真正漏汉化定位
- 用户明确反馈 B2.4.4 最新版本里左侧 `Advanced` 仍英文，提供 `translation-coverage-summary(1).json`。实读报告：`session_source_hash_prefix=e54556fa8711`、`event_count=115`、5 个页面 ready、`applied_unique_count=99`、仅 warning `home/TitleLockup`。关键事实：`Advanced`/Presets/Launch/Performance / Fixes/HD Graphics/Visual / QoL 均在 `unobserved_translated_keys` 而非 applied；说明不是未填写译文，而是旧 Hook 没命中这些实际绘制路径。
- 直接读取本地官方 `/mnt/data/_tmp_original.pyz` 并使用 Python 3.13 marshal **只读取可兼容模块的 CodeType 元数据、禁止反汇编 3.14 opcode**：`ichalaunch.ui.widgets.theme_button.ThemeButton` 存在 `paintEvent`，引用 `QStyleOptionButton`、`initStyleOption`、`style.drawControl(CE_PushButtonLabel)`，`_label_flags` 中硬编码 `CatNavButton` 对象名；`ichalaunch.ui.widgets.update_alert_badge.BadgeNavButton` 继承 theme button 并调用 `super().paintEvent`。原版 CLIENT pyz 文件中含 `BadgeNavButton`、`CatNavButton`。**先前错误假设左侧侧边栏是 GluePanelButton**，其实渲染文字走 ThemeButton 的 QStyleOptionButton；仅 Hook GluePanelButton 不足。
- `tools/cn_generator_core.py` 新增仅处理 `objectName()==CatNavButton` 的 `_cn_patch_theme_nav`：在 `ThemeButton.initStyleOption` 执行旧行为后仅替换 `option.text` 为 JSON 的中文，避免对 QWidget 原始 `.text()` 或设置的业务 state 做永久修改；该类 `paintEvent` 期间调用的 `.text()` 也只在 paint depth 返回中文，绘制外仍原样英文；其他 ThemeButton 不处理。新增 import-target `ichalaunch.ui.widgets.theme_button`。日志新增 `style-applied` 以区分样式选项命中；`tools/translation_diagnostics.py` 统计该 event。此方案真实 Qt QStyle super paint 是否会先绘英文、导致重叠**尚未实机验证**，不能保证视觉无重影；需要用户 Windows 截图对照。
- `tests/test_cn_generator.py` 加入合成 ThemeButton 的 StyleOption 译文测试：Advanced 绘制中文但调用前/后 `text()` 保留 Advanced，非 CatNavButton 仍原文；旧业务路由不改。
- 只有生成器 CI + mock Qt 不能验证真实 PySide6 的 QWidget style rendering；旧 `Advanced` 未命中属于用户实机已确认的问题，修复效果需下载新生成器重新生成测试。

## 2026-11-17 B2.4.6 — 用户确认 CatNav 生效，CLIENT 右栏复选框/说明继续修复
- 用户新上传两张 Windows GUI 截图。左侧 Presets/Launch/Performance / Fixes/Client Enhancements/HD Graphics/Visual / QoL/Advanced/Custom **全部显示中文**，证明 B2.4.5 `ThemeButton/CatNavButton` 的实机视觉汉化已成功，且用户能切换到 Performance 和 Launch 子页。右侧列表的模组说明 `Patches WoW.exe (not a DLL)...`、模组状态 `Not installed` 和 Launch 页 8 个英文复选框、Windows DPAPI 说明仍未汉化。
- 目标 `/mnt/data/_tmp_original.pyz` 模块 `ichalaunch.ui.widgets.theme_checkbox`、`theme_radio` 的 CodeType 由本机 Python3.13 marshal 读取兼容的元信息，查到真实 `paintEvent` 均引用 `text()` 和 `QPainter.drawText`（未使用 3.13 dis 解释 3.14 opcode）。据此 `tools/cn_generator_core.py` Import Hook 新增对 `ThemeCheckBox.paintEvent` / `ThemeRadioButton.paintEvent` 的已有 paint-depth 适配，绘制时返回词库中文、函数外 `text()` 仍英文、`isChecked()` 不变。**不知道截图里的全部复选框是否都属于这些具体类，尚未真实 PySide6 回归**。
- GitHub 默认 `translations/zh_CN.json` 缺失截图中 8 个 Launch 选项文字，现增加 8 项 + Nampower DPAPI 说明 + Vanilla Tweaks V2 详细说明，共 105 词条。若用户在 GUI 选择独立外部 JSON，仍以用户自定义词库为准，代码不会自动合并新增译文，不能保证外部 JSON 包含这些条目。
- 模组说明通常源自动态 catalog，不一定在 ClientPage 的 __init__ CodeType 常量里：新增极窄 `_CN_CLIENT_DETAIL_KEYS`，**只允许已确认的两条说明句**在 ClientPage 子树的 QLabel 用用户词库译文替换；其他模块名、安装状态保持原始字符串，不做全局翻译。
- `tests/test_cn_generator.py` 加入 mock ThemeCheckBox/ThemeRadioButton paint-only 与 checked 值保护，及只翻译安全 description QLabel、不能修改原始 `Not installed`、`Vanilla Tweaks V2` 模组 ID 的合成测试。首个真实 CI 错误 Run `44058901250`：模组名称在测试里恰好位于 Page.__init__ 的 eligible 静态常量集合中，被误翻译；**这暴露了真实潜在安全边界**，不是测试笔误。已新增 `_CN_CLIENT_CATALOG_IDENTIFIERS` 的明确模组标识否决集合，禁止这些 package ID 被 ClientPage 通用 QLabel 翻译。列表是已知模组的防护，不能声称覆盖所有未知 catalog ID；对后续可使用控件路径和元数据属性建立更完备隔离。再等最新 CI。
- 仍未解决 CLIENT 下方 `Pending: Install Auto-clear WDB cache` 的动态文字、模组状态 `Not installed`、Cinder 1.14 元数据、GAME UPDATE 动态弹窗。状态不应未经调用链验证就强制 setText。
- 与以往稳定基线一致：原版 EXE 不改，生成器输出新版 EXE；`_running_launcher_sha256` 仍使用原版输入 hash 避免汉化误报官方更新；词库仍为一行一组的单层 JSON。用户 Windows 实机截图/checkbox 点击回归仍待做，CI 不等于实机通过。

## 2026-11-17 B2.4.7 继续处理：Config.wtf / DXVK 编辑弹窗
- 真实 Windows 用户截图：CONFIG.WTF SETTINGS 与 DXVK.CONF SETTINGS 均有大量英文标题、说明、分组与选项。CLIENT 模组 Vanilla Tweaks V2 长说明仍是英文（之前 allowlist QLabel 修复未达到预期）。
- 已核对原版 `/mnt/data/_tmp_original.pyz` 的 Python code metadata：`ichalaunch.ui.widgets.dialogs.ConfigWtfSettingsDialog` / `DxvkConfSettingsDialog` 真实存在，配置字段的真实原始 label/group/hint 在 `ichalaunch.game.config_wtf_edits.CVAR_SPECS`、`ichalaunch.game.dxvk_conf_edits.DXVK_SPECS`；`name` 是业务配置键，严禁改。
- `tools/cn_generator_core.py` 新增导入弹窗模块 `ichalaunch.ui.widgets.dialogs` 专属 adapter：在这两个已知弹窗 __init__ 返回后遍历其子 QLabel，仅对固定弹窗文字 + spec.label/group/hint 且词库有非空译文时 setText。滑块、QComboBox currentData、Spec.name 和输出文件未改。`translations/zh_CN.json` 补充 Config/DXVK 文本（新增约 46 条）。
- `tests/test_cn_generator.py` 新增两种弹窗模拟测试（配置项中文、无关文字不变、保存值不变）。首个真实失败 Run `44061061730` 是代码收集所有 init 字符串把测试中的不相干业务 label 误改，修复 Commit `75f03512` 仅收集显式展示字段；Run `44061378221` Python3.14 tests + PyInstaller Windows EXE build 完整 success。后续 `tools/translation_diagnostics.py` 把 `config-label-applied` 计入命中，Commit `41560763`，CI `44061492965` 为当前后续检查。
- `GENERATOR_README.md` 已写操作边界。当前 Windows 真实 GUI 弹窗汉化、长文本截断、Save/应用实际行为和用户外部独立 zh_CN.json 是否包含新词，**全部未验证**；仅记录 CI 和合成测试，不可声称实机成功。
- 重要后续：定位 Vanilla Tweaks V2 动态描述到底是哪个 Qt 组件类及其创建/更新路径；不要盲目把全 ClientPage 的 JLabel、QComboBox 或模组名称全局翻译。用户此前已确认左侧 CatNavButton 中文生效，保持此稳定基线。官方 EXE SHA 兼容修复不能移除。

## 2026-11-17 B2.4.8：四类确认弹窗显示层汉化
- 用户最终上传 7 张真实 Windows 截图，去重后 4 类：`Addon folder name mismatch`、`Recommended addon forks`、`GAME UPDATE`、`Reset Client Link`。此前按钮部分已经中文，但标题/正文仍英文，包含动态文件数、目录名、插件仓库标识。
- 真实原版 `/mnt/data/_tmp_original.pyz`（来源 `IchaLaunch.exe`，原版 SHA-256 `e54556fa8711fa577d48b38fe2501d0e41f315b973651799d753929ed13c1697`）中可由本地 Python3.13 marshal 正确解析的 `ichalaunch.ui.widgets.metal_framed_dialog.MetalFramedDialog.__init__` CodeType 元数据显示参数 `parent,title,text`，该基类在 Qt 中构建 `ThemedDialogTitle`/`ThemedDialogBody` QLabel。原版 `ichalaunch.ui.main_window`、`ichalaunch.ui.widgets.dialogs` 本地3.13 marshal 不能反汇编，但**直接从其经过解压的 Python3.14 marshal 字节中核对**了 GAME UPDATE / Reset Client Link / RecommendedForkSwapDialog / confirm_addon_toc_renamer 的真实静态英文常量，避免猜测；绝未使用 Python3.13 dis 误解 3.14 opcode。
- `tools/cn_generator_core.py` 中新增 `_cn_patch_metal_prompts` 和 `_cn_patch_dialog_family`，以 import-time Hook 方式在基类、ThemedDialog 和 RecommendedForkSwapDialog 初始化后，对已知标题及其 QLabel 正文进行限定显示翻译；特别处理 recommended fork 子类在基类完成后追加的仓库行。
- 动态模板 `{count}`、`{folder}`、`{toc}`、`{target}` 只插入数字或原始名字，保留 .toc 文件名、插件 ID，绝不改变 DialogResult、文件重命名回调或更新逻辑。模板使用单趟正则替换，防止目录名里包含 `{toc}` 时被连锁替换；占位符缺失时保持英文。
- `_CN_PROMPT_STATIC` 是每个已知弹窗明确的源字符串白名单；**不能把所有子 QLabel 或词库中的任何已翻译模组名称直接改掉**，避免 catalog 信息错误。`translation-coverage.jsonl` 仅记录 `dialog-applied` + 类型 title/body，不泄露动态目录名称。
- `translations/zh_CN.json` 保留用户要求的单层 JSON 格式，加入 19 个四类弹窗标题、说明/静态段落及动态模板（此前151→170词条）。
- `tests/test_cn_generator.py` 新增四类弹窗模拟 Qt QLabel 回归，以及特殊目录 `Super{toc}Raid-saa` + 不完整模板不修改的测试。出现过连续中间 CI failure，首个重要源码问题为 `getattr(cls, "_raven_cn_prompt_wrapper", False)` 错误读取父类标志，导致 RecommendedForkSwapDialog **跳过自己初始化后的二次扫描**；现改为 `vars(cls).get` 仅看自己的 Hook 标记，Commit `31573fc3`，CI Run `44069983000` completed/success。另两个模拟样本使用截断的原版推荐说明或仅按段设置 Reset body 翻译，现已按真实原文及严格分段规则更正。
- 最新模板加固 Commit `64b9e16f`，测试加固 Commit `00803bf9`，最新 Run `44070210169` 待核对。没有 Windows 实机确认四个真实弹窗汉化、按钮响应与布局；**CI success 不等于实机验证**。
- 旧稳定基线：nav / CatNavButton 中文用户已实机确认；生成器仍只生成新 EXE，不改官方原版；原版 SHA 更新比较修复继续保留。
- 下一步：下载最新 Windows generator，使用同一官方 IchaLaunch.exe + 已合并新词条的用户词库，逐一重现四类弹窗；特别确认文件数量与目录/仓库名称保留、长中文不裁切、Yes/No/Apply/Update 按钮实际逻辑正常。
