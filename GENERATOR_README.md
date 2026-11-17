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

