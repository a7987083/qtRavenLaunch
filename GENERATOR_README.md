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