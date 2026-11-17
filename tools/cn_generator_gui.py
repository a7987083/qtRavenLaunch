"""Self-contained Windows GUI for producing an independently runnable CN launcher."""
from __future__ import annotations
import json
import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from cn_generator_core import generate, load_translations
from extract_strings import export_strings
from translation_diagnostics import diagnostic_path, summarize


def main():
    app = tk.Tk()
    app.title('RavenLaunch 汉化生成器 · B 版')
    app.geometry('730x460')
    app.minsize(650, 420)
    frame = ttk.Frame(app, padding=18)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='将官方启动器生成为独立中文版', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w', pady=(0, 10))
    ttk.Label(frame, text='原版保持不变；新程序由 Qt 自行绘制中文，不创建外部覆盖窗口。').pack(anchor='w')
    src = tk.StringVar()
    dest = tk.StringVar()
    dictionary = tk.StringVar()

    def browse_src():
        p = filedialog.askopenfilename(title='选择 IchaLaunch.exe', filetypes=[('EXE', '*.exe')])
        if p:
            src.set(p)
            dest.set(str(Path(p).with_name('IchaLaunch-CN.exe')))

    def browse_dst():
        p = filedialog.asksaveasfilename(title='输出中文版', defaultextension='.exe',
                                         initialfile='IchaLaunch-CN.exe',
                                         filetypes=[('EXE', '*.exe')])
        if p:
            dest.set(p)

    def browse_dictionary():
        p = filedialog.askopenfilename(title='选择自定义中文词库（可选）',
                                       filetypes=[('JSON', '*.json')])
        if p:
            dictionary.set(p)

    for label, var, callback, button_name in (
        ('官方 EXE', src, browse_src, '选择'),
        ('输出文件', dest, browse_dst, '保存到'),
        ('自定义词库（可选）', dictionary, browse_dictionary, '选择'),
    ):
        ttk.Label(frame, text=label).pack(anchor='w', pady=(13, 2))
        line = ttk.Frame(frame)
        line.pack(fill='x')
        ttk.Entry(line, textvariable=var).pack(side='left', fill='x', expand=True)
        ttk.Button(line, text=button_name, command=callback, width=9).pack(side='left', padx=(8, 0))

    status = tk.StringVar(value='请选择原版 IchaLaunch.exe。')
    ttk.Label(frame, textvariable=status, wraplength=660).pack(anchor='w', pady=12)
    actions = ttk.Frame(frame)
    actions.pack(anchor='w')
    export_button = ttk.Button(actions, text='导出原始字符串')
    export_button.pack(side='left', padx=(0, 12))
    button = ttk.Button(actions, text='生成中文版 EXE')
    button.pack(side='left')
    diagnostics_button = ttk.Button(actions, text='查看翻译诊断')
    diagnostics_button.pack(side='left', padx=(12, 0))

    def finish(result, err):
        button.configure(state='normal')
        export_button.configure(state='normal')
        if err:
            status.set('生成失败：' + str(err))
            messagebox.showerror('生成失败', str(err))
        else:
            status.set('静态封装检查已通过：' + dest.get() + '。Windows 运行和游戏启动仍需实机验证。')
            report = Path(dest.get()).with_suffix('.cn-report.json')
            try:
                report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            except OSError:
                pass
            messagebox.showinfo('已生成', f"中文版已生成：\n{dest.get()}\n\n请先验证界面和游戏启动功能。")

    def start():
        a, b = Path(src.get().strip()), Path(dest.get().strip())
        if not a.is_file() or not str(dest.get()).strip():
            messagebox.showerror('参数不完整', '请选择有效的原版 EXE 和输出路径')
            return
        if dictionary.get().strip() and not Path(dictionary.get().strip()).is_file():
            messagebox.showerror('词库不存在', '自定义 JSON 词库路径无效。')
            return
        if b.exists():
            messagebox.showerror('文件已存在', '为保护已有文件，生成器不会覆盖输出文件。请换一个文件名。')
            return
        button.configure(state='disabled')
        status.set('正在解析、翻译接入和重新封装（不修改原版）...')

        def work():
            try:
                translation_path = Path(dictionary.get().strip()) if dictionary.get().strip() else None
                res = generate(a, b, translation_path)
                app.after(0, finish, res, None)
            except Exception as ex:
                app.after(0, finish, None, f'{type(ex).__name__}: {ex}')
        threading.Thread(target=work, daemon=True).start()

    def export_original_strings():
        original = Path(src.get().strip())
        if not src.get().strip() or not original.is_file():
            messagebox.showerror('未选择原版', '请先选择官方 IchaLaunch.exe。')
            return
        destination = filedialog.asksaveasfilename(
            title='导出原始文字到 zh_CN.json',
            initialdir=str(original.parent),
            initialfile='zh_CN.json',
            defaultextension='.json',
            filetypes=[('JSON', '*.json')])
        if not destination:
            return
        output = Path(destination)
        if output.exists() and not messagebox.askyesno(
                '合并翻译',
                '文件已存在。是否保留现有译文，仅追加新发现的英文？\\n'
                '导出过程中不会删除原有翻译。'):
            return
        button.configure(state='disabled')
        export_button.configure(state='disabled')
        status.set('正在静态扫描原版 PYZ，收集真实英文常量（不执行目标 EXE）...')

        def done(summary, error):
            button.configure(state='normal')
            export_button.configure(state='normal')
            if error is not None:
                status.set('导出失败：' + str(error))
                messagebox.showerror('导出失败', str(error))
                return
            dictionary.set(str(output))
            status.set('已导出：' + str(output))
            messagebox.showinfo(
                '字符串导出完成',
                f"扫描模块：{summary['ui_modules_examined']}\\n"
                f"候选词条：{summary['total_entries']}\\n"
                f"新词条：{summary['new_empty_entries']}\\n\\n"
                '导出的是真实 Python 字符串候选，不保证全部是界面文字；'
                '添加中文也不代表该控件已经有翻译适配器。')

        def work():
            try:
                summary = export_strings(original, output)
                app.after(0, done, summary, None)
            except Exception as exc:
                app.after(0, done, None, f'{type(exc).__name__}: {exc}')

        threading.Thread(target=work, daemon=True).start()

    def view_translation_diagnostics():
        report = diagnostic_path()
        if not report.is_file():
            messagebox.showinfo(
                '尚无诊断报告',
                '请先运行新生成的 IchaLaunch-CN.exe，并进入需要翻译的页面。'
                '运行时日志将保存到 LOCALAPPDATA/RavenLaunch-CN。')
            return
        try:
            custom = Path(dictionary.get().strip()) if dictionary.get().strip() else None
            translated = load_translations(custom)
            summary = summarize(report, translated)
            outfile = report.with_name('translation-coverage-summary.json')
            outfile.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
            messagebox.showinfo(
                '翻译诊断',
                f"已就绪页面：{', '.join(summary['ready_pages']) or '无'}\\n"
                f"命中词条：{summary['applied_unique_count']}\\n"
                f"尚未观察到的已翻译词条：{len(summary['unobserved_translated_keys'])}\\n"
                f"适配器警告：{len(summary['adapter_warnings'])}\\n\\n"
                '未观察到不等于翻译失败，可能尚未进入对应页面。'
                '点击确定打开完整 JSON 报告。')
            os.startfile(str(outfile))
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror('生成诊断失败', str(exc))

    diagnostics_button.configure(command=view_translation_diagnostics)
    export_button.configure(command=export_original_strings)
    button.configure(command=start)
    app.mainloop()


if __name__ == '__main__':
    main()
