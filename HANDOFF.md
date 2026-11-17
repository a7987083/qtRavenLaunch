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
