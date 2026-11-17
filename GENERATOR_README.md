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

## B2.1 — 独立词库与 Glyphshift 导入（2026-11-17）

已添加 `translations/zh_CN.json`，包含被隔离的 `nav` / `launch` 两组安全自绘汉化词条。生成器把它编译进新的 EXE 启动脚本；既有 `status_lbl.text()` 业务判断和已修复的官方更新 SHA 比较逻辑不变。Windows 单文件生成器构建时经 PyInstaller `--add-data` 内置该 JSON。修改 JSON 后，需要**重新构建生成器**，或开发者用 `--dictionary` 指定磁盘上的新词库：

```powershell
py tools/cn_generator_core.py IchaLaunch.exe --out IchaLaunch-CN.exe --dictionary translations/zh_CN.json
```

Glyphshift 作为可选外部工具，不捆绑、不运行在生成的 EXE 中。它可以导出 JSON 或 CSV；导入候选项：

```powershell
py tools/translation_collector.py glyphshift-export.json --out translations/glyphshift-candidates.json
```

候选文件 `review_required=true`，只供人工校对，**不会被自动插入生成器运行时或全局替换 Qt 文本**。请参阅 `docs/GLYPHSHIFT_RESEARCH.md`。

限制：目前仅加载 `nav` / `launch` 已知自绘路径；SETTINGS 页面普通 QLabel/QPushButton 全面翻译是 B2.2，未完成。尚无真实 Glyphshift + IchaLaunch 采集验证；单元测试和 Windows 构建不能替代真实 GUI 回归。
