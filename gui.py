#!/usr/bin/env python3
"""Tkinter GUI for the Japanese audio filename converter.

The GUI uses the same conversion engine as rename_audio.py.  It scans a
folder, shows a dry-run preview, and only renames files after confirmation.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from rename_audio import (
    DEFAULT_EXTENSIONS,
    Converter,
    iter_audio_files,
    safe_filename,
    unique_target,
)


@dataclass
class PreviewRow:
    source: Path
    new_name: str
    target: Path
    status: str
    action: str
    note: str = ""

    @property
    def tag(self) -> str:
        if self.action == "rename" and self.note:
            return "collision"
        return self.action


def parse_extensions(text: str) -> set[str]:
    extensions: set[str] = set()
    for part in text.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if not part.startswith("."):
            part = "." + part
        extensions.add(part)
    return extensions


def build_preview_rows(
    folder: Path,
    recursive: bool,
    extensions: set[str],
    converter: Converter,
) -> list[PreviewRow]:
    rows: list[PreviewRow] = []
    for source in iter_audio_files(folder, recursive, extensions):
        try:
            new_name = safe_filename(converter.convert_filename(source.name))
            if new_name == source.name:
                rows.append(
                    PreviewRow(source, new_name, source, "跳过（无需转换）", "skip")
                )
                continue

            target = source.with_name(new_name)
            note = ""
            if target.exists() and target != source:
                target = unique_target(target)
                note = "目标已存在，自动加序号"

            status = "可重命名" + (f"（{note}）" if note else "")
            rows.append(
                PreviewRow(source, new_name, target, status, "rename", note)
            )
        except Exception as exc:  # keep scanning the remaining files
            rows.append(
                PreviewRow(
                    source,
                    source.name,
                    source,
                    f"转换失败：{exc}",
                    "error",
                    str(exc),
                )
            )
    return rows


class AudioRenamerApp:
    def __init__(self, root: tk.Tk, initial_folder: str | None = None) -> None:
        self.root = root
        self.root.title("日语音频文件名转换器")
        self.root.geometry("1080x680")
        self.root.minsize(820, 520)

        self.rows: list[PreviewRow] = []
        self.busy = False
        self.stale = True
        self.closing = False
        self.queue: queue.Queue = queue.Queue()

        self.converter: Converter | None = None
        self.converter_key = ""

        self.folder_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)
        self.no_loanwords_var = tk.BooleanVar(value=False)
        self.extensions_var = tk.StringVar(value=",".join(DEFAULT_EXTENSIONS))
        self.overrides_var = tk.StringVar()
        self.status_var = tk.StringVar(value="请选择音频文件夹，然后点击「扫描预览」。")

        if initial_folder:
            self.folder_var.set(initial_folder)

        self._configure_style()
        self._build_ui()
        self._bind_changes()
        self._update_buttons()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._report_callback_exception
        self.root.after(100, self._poll_queue)

    # -- UI construction ----------------------------------------------------

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        for theme in ("vista", "clam"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:
                continue
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            default_font.configure(family="Microsoft YaHei UI", size=10)
            text_font = tkfont.nametofont("TkTextFont")
            text_font.configure(family="Microsoft YaHei UI", size=10)
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=25)
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(4, weight=1)

        # Folder row.
        ttk.Label(outer, text="音频文件夹").grid(row=0, column=0, sticky="w")
        self.folder_entry = ttk.Entry(outer, textvariable=self.folder_var)
        self.folder_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.folder_button = ttk.Button(
            outer, text="浏览...", command=self._choose_folder
        )
        self.folder_button.grid(row=0, column=2, sticky="e")

        # Options.
        options = ttk.LabelFrame(outer, text="选项", padding=10)
        options.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        options.columnconfigure(1, weight=1)

        self.recursive_check = ttk.Checkbutton(
            options,
            text="包含子文件夹",
            variable=self.recursive_var,
        )
        self.recursive_check.grid(row=0, column=0, columnspan=2, sticky="w")

        self.no_loanwords_check = ttk.Checkbutton(
            options,
            text="片假名只转罗马音（不还原为英语）",
            variable=self.no_loanwords_var,
        )
        self.no_loanwords_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ttk.Label(options, text="扩展名").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        self.extensions_entry = ttk.Entry(options, textvariable=self.extensions_var)
        self.extensions_entry.grid(
            row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(options, text="覆盖表").grid(
            row=3, column=0, sticky="w", pady=(4, 0)
        )
        self.overrides_entry = ttk.Entry(options, textvariable=self.overrides_var)
        self.overrides_entry.grid(
            row=3, column=1, sticky="ew", padx=(8, 0), pady=(4, 0)
        )
        overrides_buttons = ttk.Frame(options)
        overrides_buttons.grid(row=3, column=2, sticky="e", padx=(8, 0), pady=(4, 0))
        self.overrides_browse = ttk.Button(
            overrides_buttons, text="选择...", command=self._choose_overrides
        )
        self.overrides_browse.pack(side="left")
        self.overrides_clear = ttk.Button(
            overrides_buttons, text="清除", command=lambda: self.overrides_var.set("")
        )
        self.overrides_clear.pack(side="left", padx=(4, 0))

        ttk.Label(
            options,
            text="覆盖表是可选的 JSON，例如 {\"チルノ\": \"Cirno\"}；留空则使用内置表。",
            foreground="#666666",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # Action buttons.
        actions = ttk.Frame(outer)
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.preview_button = ttk.Button(
            actions,
            text="扫描预览",
            style="Accent.TButton",
            command=self.start_scan,
        )
        self.preview_button.pack(side="left")
        self.apply_button = ttk.Button(
            actions,
            text="开始重命名",
            command=self.start_rename,
        )
        self.apply_button.pack(side="left", padx=(8, 0))
        self.clear_button = ttk.Button(
            actions, text="清空列表", command=self._clear_rows
        )
        self.clear_button.pack(side="left", padx=(8, 0))
        ttk.Label(
            actions,
            text="默认只预览；重命名前会再次确认。",
            foreground="#666666",
        ).pack(side="right")

        self.input_widgets = [
            self.folder_entry,
            self.folder_button,
            self.recursive_check,
            self.no_loanwords_check,
            self.extensions_entry,
            self.overrides_entry,
            self.overrides_browse,
            self.overrides_clear,
            self.clear_button,
        ]

        # Preview table.
        table_frame = ttk.Frame(outer)
        table_frame.grid(row=4, column=0, columnspan=3, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("source", "target", "status")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("source", text="原文件名")
        self.tree.heading("target", text="新文件名")
        self.tree.heading("status", text="状态")
        self.tree.column("source", width=380, minwidth=180, anchor="w")
        self.tree.column("target", width=380, minwidth=180, anchor="w")
        self.tree.column("status", width=170, minwidth=110, anchor="w")
        self.tree.tag_configure("skip", foreground="#777777")
        self.tree.tag_configure("collision", foreground="#b36b00")
        self.tree.tag_configure("error", foreground="#b00020")
        self.tree.grid(row=0, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(
            table_frame, orient="horizontal", command=self.tree.xview
        )
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        # Status bar.
        status_frame = ttk.Frame(outer)
        status_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        status_frame.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(
            status_frame, textvariable=self.status_var, anchor="w"
        )
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.progress = ttk.Progressbar(
            status_frame, mode="indeterminate", length=180
        )
        self.progress.grid(row=0, column=1, padx=(8, 0), sticky="e")
        self.progress.grid_remove()

    def _bind_changes(self) -> None:
        for var in (
            self.folder_var,
            self.recursive_var,
            self.no_loanwords_var,
            self.extensions_var,
            self.overrides_var,
        ):
            var.trace_add("write", lambda *_: self._mark_stale())

    # -- state helpers ------------------------------------------------------

    def _mark_stale(self) -> None:
        self.stale = True
        if not self.busy:
            self._update_buttons()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in self.input_widgets:
            widget.configure(state=state)
        if busy:
            self.progress.grid()
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()
        self._update_buttons()

    def _update_buttons(self) -> None:
        if self.busy:
            self.preview_button.configure(state="disabled")
            self.apply_button.configure(state="disabled")
            return
        self.preview_button.configure(state="normal")
        can_apply = (
            not self.stale
            and any(row.action == "rename" for row in self.rows)
        )
        self.apply_button.configure(state="normal" if can_apply else "disabled")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _clear_rows(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.rows = []
        self.stale = True
        self._update_buttons()

    # -- file pickers -------------------------------------------------------

    def _choose_folder(self) -> None:
        initial = self.folder_var.get().strip()
        kwargs = {}
        if initial and Path(initial).is_dir():
            kwargs["initialdir"] = initial
        selected = filedialog.askdirectory(title="选择音频文件夹", **kwargs)
        if selected:
            self.folder_var.set(selected)
            self._clear_rows()
            self._set_status("已选择文件夹，点击「扫描预览」。")

    def _choose_overrides(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择名称覆盖表",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if selected:
            self.overrides_var.set(selected)

    # -- scanning -----------------------------------------------------------

    def start_scan(self) -> None:
        if self.busy:
            return
        folder_text = self.folder_var.get().strip()
        if not folder_text:
            messagebox.showwarning("缺少文件夹", "请先选择要处理的音频文件夹。")
            return
        folder = Path(folder_text)
        if not folder.is_dir():
            messagebox.showerror("文件夹无效", f"文件夹不存在或不是目录：\n{folder}")
            return

        extensions = parse_extensions(self.extensions_var.get())
        if not extensions:
            messagebox.showerror("扩展名无效", "请至少填写一个扩展名，例如 mp3,flac。")
            return

        overrides_text = self.overrides_var.get().strip()
        if overrides_text and not Path(overrides_text).is_file():
            messagebox.showerror("覆盖表无效", f"覆盖表不存在：\n{overrides_text}")
            return

        self._clear_rows()
        self._set_busy(True)
        self._set_status("正在扫描并转换文件名……首次运行需要加载词典，请稍候。")

        args = (
            folder,
            self.recursive_var.get(),
            extensions,
            self.no_loanwords_var.get(),
            overrides_text,
        )
        threading.Thread(target=self._scan_worker, args=args, daemon=True).start()

    def _scan_worker(
        self,
        folder: Path,
        recursive: bool,
        extensions: set[str],
        no_loanwords: bool,
        overrides_text: str,
    ) -> None:
        try:
            converter = self._get_converter(overrides_text, no_loanwords)
            rows = build_preview_rows(folder, recursive, extensions, converter)
            self.queue.put(("scan_done", (rows, None)))
        except Exception as exc:
            self.queue.put(("scan_done", ([], str(exc))))

    def _get_converter(self, overrides_text: str, no_loanwords: bool) -> Converter:
        key = ""
        if overrides_text:
            path = Path(overrides_text)
            key = f"{path.resolve()}|{path.stat().st_mtime_ns}"
        if self.converter is None or key != self.converter_key:
            extra: dict[str, str] = {}
            if overrides_text:
                with Path(overrides_text).open("r", encoding="utf-8-sig") as fh:
                    loaded = json.load(fh)
                if not isinstance(loaded, dict) or not all(
                    isinstance(k, str) and isinstance(v, str)
                    for k, v in loaded.items()
                ):
                    raise ValueError("覆盖表必须是 JSON 对象，例如 {\"チルノ\": \"Cirno\"}")
                extra = loaded
            self.converter = Converter(extra_overrides=extra)
            self.converter_key = key
        self.converter.use_loanwords = not no_loanwords
        return self.converter

    # -- renaming -----------------------------------------------------------

    def start_rename(self) -> None:
        if self.busy:
            return
        if self.stale:
            messagebox.showinfo("请先预览", "选项或文件夹已更改，请重新扫描预览。")
            return
        rows = [row for row in self.rows if row.action == "rename"]
        if not rows:
            messagebox.showinfo("没有需要重命名的文件", "当前列表中没有可重命名的文件。")
            return
        if not messagebox.askyesno(
            "确认重命名",
            f"将重命名 {len(rows)} 个文件。\n\n"
            "这会直接修改文件名，确定继续吗？",
        ):
            return

        self._set_busy(True)
        self._set_status(f"正在重命名 {len(rows)} 个文件……")
        threading.Thread(
            target=self._rename_worker, args=(rows,), daemon=True
        ).start()

    def _rename_worker(self, rows: list[PreviewRow]) -> None:
        renamed = 0
        failed = 0
        errors: list[str] = []
        for row in rows:
            try:
                target = row.target
                if target.exists() and target != row.source:
                    target = unique_target(target)
                row.source.rename(target)
                renamed += 1
            except OSError as exc:
                failed += 1
                errors.append(f"{row.source.name}: {exc}")
        self.queue.put(("rename_done", (renamed, failed, errors)))

    # -- queue / callbacks --------------------------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "scan_done":
                    rows, error = payload
                    self._on_scan_done(rows, error)
                elif kind == "rename_done":
                    renamed, failed, errors = payload
                    self._on_rename_done(renamed, failed, errors)
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(100, self._poll_queue)

    def _populate_rows(self, rows: list[PreviewRow]) -> None:
        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(row.source.name, row.new_name, row.status),
                tags=(row.tag,),
            )

    def _on_scan_done(self, rows: list[PreviewRow], error: str | None) -> None:
        self._set_busy(False)
        if error:
            self._set_status("扫描失败。")
            messagebox.showerror("扫描失败", error)
            return

        self.rows = rows
        self.stale = False
        self._populate_rows(rows)
        self._update_buttons()

        total = len(rows)
        rename_count = sum(1 for row in rows if row.action == "rename")
        skip_count = sum(1 for row in rows if row.action == "skip")
        error_count = sum(1 for row in rows if row.action == "error")
        if total == 0:
            self._set_status("没有找到符合条件的音频文件。")
        else:
            self._set_status(
                f"共 {total} 个文件：可重命名 {rename_count} 个，"
                f"跳过 {skip_count} 个，失败 {error_count} 个。"
            )

    def _on_rename_done(
        self, renamed: int, failed: int, errors: list[str]
    ) -> None:
        self._set_busy(False)
        self._set_status(f"重命名完成：成功 {renamed} 个，失败 {failed} 个。")
        if failed:
            detail = "\n".join(errors[:10])
            if len(errors) > 10:
                detail += f"\n……另有 {len(errors) - 10} 个错误"
            messagebox.showwarning(
                "重命名完成",
                f"成功 {renamed} 个，失败 {failed} 个。\n\n{detail}",
            )
        else:
            messagebox.showinfo("重命名完成", f"成功重命名 {renamed} 个文件。")
        self.start_scan()

    def _report_callback_exception(self, exc, value, tb) -> None:
        messagebox.showerror("程序错误", f"{value}")

    def _on_close(self) -> None:
        if self.busy and not messagebox.askyesno(
            "任务进行中", "当前任务尚未完成，确定退出吗？"
        ):
            return
        self.closing = True
        self.root.destroy()


def self_test() -> int:
    """Used by the CI build to verify the packaged GUI executable."""
    try:
        converter = Converter()
        result = converter.convert_filename("マインドブランド.mp3")
        ok = result == "Mind Brand.mp3" and tk.TkVersion >= 8.0
        if sys.stdout is not None:
            print(result)
        return 0 if ok else 1
    except Exception as exc:
        if sys.stderr is not None:
            print(f"self-test failed: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="日语音频文件名转换器的 Tkinter 图形界面",
        add_help=True,
    )
    parser.add_argument("folder", nargs="?", help="可选的初始音频文件夹")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="只做一次转换自检，不打开窗口（用于 CI）",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    root = tk.Tk()
    AudioRenamerApp(root, initial_folder=args.folder)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
