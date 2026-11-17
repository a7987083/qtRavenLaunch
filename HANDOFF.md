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
