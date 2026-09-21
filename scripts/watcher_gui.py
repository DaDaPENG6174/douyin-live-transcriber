"""Desktop dashboard for the automatic recording transcription watcher."""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from watch_recordings import VIDEO_EXTENSIONS, find_recordings, job_dir_for


@dataclass
class Item:
    path: Path
    status: str = "待处理"
    progress: float = 0.0
    eta: str = "-"
    duration: float = 0.0
    error: str = ""


def fmt_seconds(seconds: float) -> str:
    if seconds <= 0:
        return "计算中"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}小时{minutes:02d}分"
    if minutes:
        return f"{minutes}分{seconds:02d}秒"
    return f"{seconds}秒"


class TranscriptionWorker(threading.Thread):
    def __init__(self, args: argparse.Namespace, events: queue.Queue):
        super().__init__(daemon=True)
        self.args = args
        self.events = events
        self.stop_event = threading.Event()
        self.running_paths: set[Path] = set()

    def emit(self, kind: str, **payload: object) -> None:
        self.events.put((kind, payload))

    def stop(self) -> None:
        self.stop_event.set()

    def duration_of(self, video: Path) -> float:
        try:
            result = subprocess.run(
                [self.args.ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
                check=True,
                capture_output=True,
                text=True,
            )
            return float(result.stdout.strip())
        except (OSError, ValueError, subprocess.CalledProcessError):
            return 0.0

    def process(self, video: Path) -> None:
        job_dir = job_dir_for(video, self.args.output_dir)
        metadata_dir = job_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        marker = job_dir / ".failed"
        if (job_dir / "transcript.json").exists():
            self.emit("status", path=video, status="已完成", progress=100.0, eta="-")
            return
        if marker.exists() and not self.args.retry_failed:
            self.emit("status", path=video, status="失败待重试", progress=0.0, eta="-")
            return

        duration = self.duration_of(video)
        self.emit("status", path=video, status="分析音轨", progress=3.0, eta=fmt_seconds(duration * 0.1), duration=duration)
        source = {"path": str(video.resolve()), "size": video.stat().st_size, "modified": video.stat().st_mtime}
        (job_dir / "source.json").write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            with (metadata_dir / "media.json").open("w", encoding="utf-8") as output:
                subprocess.run(
                    [self.args.ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(video)],
                    check=True,
                    stdout=output,
                )

            self.emit("status", path=video, status="转写音轨", progress=8.0, eta=fmt_seconds(duration * self.args.estimate_ratio))
            started = time.monotonic()
            transcriber = subprocess.Popen(
                [sys.executable, str(Path(__file__).with_name("transcribe_multitrack.py")), str(video), "--out-dir", str(job_dir), "--device", self.args.device, "--ffmpeg", self.args.ffmpeg, "--ffprobe", self.args.ffprobe, "--track-labels", self.args.track_labels],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            while transcriber.poll() is None and not self.stop_event.wait(1):
                elapsed = time.monotonic() - started
                expected = max(30.0, duration * self.args.estimate_ratio)
                progress = min(98.0, 8.0 + elapsed / expected * 92.0)
                self.emit("status", path=video, status="转写音轨", progress=progress, eta=fmt_seconds(max(0, expected - elapsed)))
            if self.stop_event.is_set():
                transcriber.kill()
                return
            if transcriber.returncode:
                raise subprocess.CalledProcessError(transcriber.returncode, str(transcriber.args))
            marker.unlink(missing_ok=True)
            self.emit("status", path=video, status="已完成", progress=100.0, eta="-")
        except (OSError, subprocess.CalledProcessError, PermissionError) as exc:
            marker.write_text(str(exc), encoding="utf-8")
            self.emit("status", path=video, status="失败", progress=0.0, eta="-", error=str(exc))

    def run(self) -> None:
        while not self.stop_event.is_set():
            for video in find_recordings(self.args.watch_dir, self.args.output_dir):
                if self.stop_event.is_set():
                    return
                if video in self.running_paths:
                    continue
                job_dir = job_dir_for(video, self.args.output_dir)
                if (job_dir / "transcript.json").exists():
                    continue
                if (job_dir / ".failed").exists() and not self.args.retry_failed:
                    continue
                self.running_paths.add(video)
                self.process(video)
                self.running_paths.remove(video)
                break
            self.stop_event.wait(self.args.poll_seconds)


class Dashboard(tk.Tk):
    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.args = args
        self.events: queue.Queue = queue.Queue()
        self.items: dict[str, Item] = {}
        self.worker = TranscriptionWorker(args, self.events)
        self.current_path: str | None = None
        self.title("直播录屏转文字中心")
        self.geometry("1120x720")
        self.minsize(900, 600)
        self.configure(bg="#111827")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.build_style()
        self.build_ui()
        self.worker.start()
        self.after(500, self.refresh)

    def build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#111827")
        style.configure("Panel.TFrame", background="#1f2937")
        style.configure("Title.TLabel", background="#111827", foreground="#f9fafb", font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("Sub.TLabel", background="#111827", foreground="#9ca3af", font=("Microsoft YaHei UI", 10))
        style.configure("CardTitle.TLabel", background="#1f2937", foreground="#9ca3af", font=("Microsoft YaHei UI", 10))
        style.configure("CardValue.TLabel", background="#1f2937", foreground="#f9fafb", font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("PanelTitle.TLabel", background="#1f2937", foreground="#f9fafb", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Body.TLabel", background="#1f2937", foreground="#d1d5db", font=("Microsoft YaHei UI", 10))
        style.configure("Accent.Horizontal.TProgressbar", troughcolor="#374151", background="#22c55e", bordercolor="#374151", lightcolor="#22c55e", darkcolor="#22c55e")
        style.configure("Treeview", background="#111827", fieldbackground="#111827", foreground="#d1d5db", rowheight=34, borderwidth=0, font=("Microsoft YaHei UI", 10))
        style.configure("Treeview.Heading", background="#374151", foreground="#f9fafb", relief="flat", font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#1d4ed8")], foreground=[("selected", "#ffffff")])

    def build_ui(self) -> None:
        root = ttk.Frame(self, style="App.TFrame", padding=28)
        root.pack(fill="both", expand=True)
        header = ttk.Frame(root, style="App.TFrame")
        header.pack(fill="x", pady=(0, 22))
        ttk.Label(header, text="直播录屏转文字中心", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text=f"监控目录：{self.args.watch_dir}    ·    设备：{self.args.device}    ·    音轨：{self.args.track_labels}", style="Sub.TLabel").pack(anchor="w", pady=(6, 0))

        cards = ttk.Frame(root, style="App.TFrame")
        cards.pack(fill="x", pady=(0, 18))
        self.card_values = {}
        for key, title in [("total", "视频总数"), ("done", "已转写"), ("pending", "待处理"), ("failed", "失败")]:
            card = ttk.Frame(cards, style="Panel.TFrame", padding=16)
            card.pack(side="left", fill="x", expand=True, padx=(0, 12))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            value = ttk.Label(card, text="0", style="CardValue.TLabel")
            value.pack(anchor="w", pady=(5, 0))
            self.card_values[key] = value

        current = ttk.Frame(root, style="Panel.TFrame", padding=20)
        current.pack(fill="x", pady=(0, 18))
        ttk.Label(current, text="当前任务", style="PanelTitle.TLabel").pack(anchor="w")
        self.current_name = ttk.Label(current, text="暂无转写任务", style="Body.TLabel")
        self.current_name.pack(anchor="w", pady=(12, 8))
        progress_row = ttk.Frame(current, style="Panel.TFrame")
        progress_row.pack(fill="x")
        self.progress = ttk.Progressbar(progress_row, style="Accent.Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress_text = ttk.Label(progress_row, text="0%", style="Body.TLabel", width=8, anchor="e")
        self.progress_text.pack(side="left", padx=(14, 0))
        self.eta = ttk.Label(current, text="预计剩余：-", style="Sub.TLabel")
        self.eta.pack(anchor="w", pady=(8, 0))

        listing = ttk.Frame(root, style="Panel.TFrame", padding=20)
        listing.pack(fill="both", expand=True)
        ttk.Label(listing, text="视频清单", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 12))
        table_frame = ttk.Frame(listing, style="Panel.TFrame")
        table_frame.pack(fill="both", expand=True)
        columns = ("name", "duration", "status", "progress", "eta")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {"name": "视频文件", "duration": "时长", "status": "状态", "progress": "进度", "eta": "预计剩余"}
        widths = {"name": 470, "duration": 100, "status": 120, "progress": 90, "eta": 130}
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(column, width=widths[column], anchor="w" if column == "name" else "center")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def refresh_inventory(self) -> None:
        paths = find_recordings(self.args.watch_dir, self.args.output_dir)
        current = {str(path): path for path in paths}
        for key, path in current.items():
            item = self.items.setdefault(key, Item(path))
            job_dir = job_dir_for(path, self.args.output_dir)
            if (job_dir / "transcript.json").exists() and item.status not in {"转写中", "提取音频"}:
                item.status, item.progress, item.eta = "已完成", 100.0, "-"
            elif (job_dir / ".failed").exists() and item.status not in {"转写中", "提取音频"}:
                item.status, item.progress, item.eta = "失败待重试", 0.0, "-"
        for key in list(self.items):
            if key not in current:
                del self.items[key]

    def apply_event(self, event: tuple[str, dict]) -> None:
        kind, payload = event
        if kind != "status":
            return
        path = payload["path"]
        key = str(path)
        item = self.items.setdefault(key, Item(Path(path)))
        item.status = str(payload.get("status", item.status))
        item.progress = float(payload.get("progress", item.progress))
        item.eta = str(payload.get("eta", item.eta))
        item.duration = float(payload.get("duration", item.duration))
        if item.status in {"转写中", "提取音频"}:
            self.current_path = key
        elif item.status == "已完成" and self.current_path == key:
            self.current_path = None

    def refresh(self) -> None:
        self.refresh_inventory()
        while True:
            try:
                self.apply_event(self.events.get_nowait())
            except queue.Empty:
                break
        self.render()
        if self.winfo_exists():
            self.after(1000, self.refresh)

    def render(self) -> None:
        values = {"total": len(self.items), "done": 0, "pending": 0, "failed": 0}
        for item in self.items.values():
            if item.status == "已完成":
                values["done"] += 1
            elif item.status in {"失败", "失败待重试"}:
                values["failed"] += 1
            else:
                values["pending"] += 1
        for key, value in values.items():
            self.card_values[key].configure(text=str(value))
        for row in self.table.get_children():
            self.table.delete(row)
        for key, item in sorted(self.items.items(), key=lambda pair: pair[1].path.stat().st_mtime if pair[1].path.exists() else 0):
            self.table.insert("", "end", iid=key, values=(item.path.name, fmt_seconds(item.duration), item.status, f"{item.progress:.0f}%", item.eta))
        if self.current_path and self.current_path in self.items:
            item = self.items[self.current_path]
            self.current_name.configure(text=item.path.name)
            self.progress["value"] = item.progress
            self.progress_text.configure(text=f"{item.progress:.0f}%")
            self.eta.configure(text=f"预计剩余：{item.eta}")
        else:
            self.current_name.configure(text="暂无转写任务")
            self.progress["value"] = 0
            self.progress_text.configure(text="0%")
            self.eta.configure(text="预计剩余：-")

    def close(self) -> None:
        if messagebox.askyesno("退出", "退出界面会停止自动监控。确定退出吗？"):
            self.worker.stop()
            self.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcription dashboard")
    parser.add_argument("watch_dir", type=Path, nargs="?", default=Path("D:/直播录屏"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--stable-checks", type=int, default=3)
    parser.add_argument("--device", choices=["cpu", "cuda:0"], default="cuda:0")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--track-labels", default="主播,连线嘉宾")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--estimate-ratio", type=float, default=None)
    args = parser.parse_args()
    args.watch_dir = args.watch_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    if not args.watch_dir.is_dir():
        raise SystemExit(f"Watch folder not found: {args.watch_dir}")
    args.estimate_ratio = args.estimate_ratio or (0.12 if args.device.startswith("cuda") else 0.35)
    return args


if __name__ == "__main__":
    Dashboard(parse_args()).mainloop()
