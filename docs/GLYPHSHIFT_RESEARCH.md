# B2.1 — Glyphshift 辅助词条收集（不作为运行依赖）

**当前阶段：已实现导出导入工具和词库隔离；未验证 Glyphshift 对官方 IchaLaunch.exe 的实际文字捕获率。**

## 上游核对

仓库： https://github.com/glyphshift/glyphshift

- `crates/product/desktop-backend/src/dictionary_transfer/json.rs`: JSON 为词条数组或含 `entries` 数组的对象；每条包含 `source`、`translation`。
- `crates/product/desktop-backend/src/dictionary_transfer/csv.rs`: CSV 使用 `source`、`translation` 列，可有其他列。
- `README.md`: Qt Widgets 只覆盖部分文字路径；是否抓到 IchaLaunch 各页面需在 Windows 实测。
- 上游 GPL-3.0-only。本仓库导入工具为独立实现，只读取导出数据，不包含上游代码或注入组件。

## 操作流程

1. 在 Windows Glyphshift 中为**原版**启动器创建采集工作流，逐页打开 HOME / SETTINGS / CLIENT / ADDONS / 弹窗。不得把它与汉化生成器的原生文字修改引擎混为一谈。
2. Glyphshift 导出 JSON 或 UTF-8 CSV（`source`,`translation`）。
3. 运行：
```powershell
py tools/translation_collector.py .\glyphshift-export.json --out .\translations\glyphshift-candidates.json
```
4. 检查生成的 `review_required: true` 候选项，人工确认来源和场景。
5. **不要**把候选项全部直接导入运行时 Hook。状态标签、包含业务标识的文字可能被 `.text()` 读取。后续 B2.2 对每一类控件指定安全替换策略。

正式运行词库为 `translations/zh_CN.json`，包含仅作用于已确认的两种自绘控件的 `nav` / `launch` 字典；不会进行全局 Qt 文本替换。生成器支持自定义词库路径 `--dictionary`，但必须满足严格 schema 校验。图形生成器附带默认字典。

## 验证范围

- 导入器仅检查数据格式、重复冲突、尺寸和输出覆盖保护。
- B2.1 不改官方原版 EXE；生成器输出依旧是独立新版 EXE。
- 尚无 Glyphshift + IchaLaunch 实机捕获测试；无法声称所有界面文字都可自动收集。
- SETTINGS 自绘之外的 QLabel、QPushButton 与动态状态翻译属 B2.2，**本阶段未实现**。
