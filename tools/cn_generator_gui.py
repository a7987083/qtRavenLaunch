"""Self-contained Windows GUI for producing an independently runnable CN launcher."""
from __future__ import annotations
import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from cn_generator_core import generate


def main():
    app = tk.Tk()
    app.title('RavenLaunch 汉化生成器 · B 版')
    app.geometry('730x340')
    app.minsize(650, 320)
    frame = ttk.Frame(app, padding=18)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='将官方启动器生成为独立中文版', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w', pady=(0, 10))
    ttk.Label(frame, text='原版保持不变；新程序由 Qt 自行绘制中文，不创建外部覆盖窗口。').pack(anchor='w')
    src = tk.StringVar()
    dest = tk.StringVar()

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

    for label, var, callback, button_name in (
        ('官方 EXE', src, browse_src, '选择'),
        ('输出文件', dest, browse_dst, '保存到'),
    ):
        ttk.Label(frame, text=label).pack(anchor='w', pady=(13, 2))
        line = ttk.Frame(frame)
        line.pack(fill='x')
        ttk.Entry(line, textvariable=var).pack(side='left', fill='x', expand=True)
        ttk.Button(line, text=button_name, command=callback, width=9).pack(side='left', padx=(8, 0))

    status = tk.StringVar(value='请选择原版 IchaLaunch.exe。')
    ttk.Label(frame, textvariable=status, wraplength=660).pack(anchor='w', pady=12)
    button = ttk.Button(frame, text='生成中文版 EXE')
    button.pack(anchor='w')

    def finish(result, err):
        button.configure(state='normal')
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
        if b.exists():
            messagebox.showerror('文件已存在', '为保护已有文件，生成器不会覆盖输出文件。请换一个文件名。')
            return
        button.configure(state='disabled')
        status.set('正在解析、翻译接入和重新封装（不修改原版）...')

        def work():
            try:
                res = generate(a, b)
                app.after(0, finish, res, None)
            except Exception as ex:
                app.after(0, finish, None, f'{type(ex).__name__}: {ex}')
        threading.Thread(target=work, daemon=True).start()

    button.configure(command=start)
    app.mainloop()


if __name__ == '__main__':
    main()
