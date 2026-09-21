# 自动监控录屏转文字

`scripts/watch_recordings.py` 会监控直播录屏文件夹。新视频出现后，脚本会等待文件大小连续稳定，再自动：

1. 用 ffmpeg 提取单声道 16kHz WAV。
2. 调用现有的 FunASR 本地转写脚本。
3. 在 `output/<录屏名>/` 生成 `transcript.txt`、`transcript.json`、`transcript.srt`。

## 启动

最快方式：直接双击项目目录中的 `start_watcher.bat`。它会打开可视化监控界面，默认监控 `D:\直播录屏`。

如果录屏目录不是这个位置，用记事本打开 `start_watcher.bat`，修改 `set "WATCH_DIR=..."` 这一行。

在项目目录运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_recordings.py "D:\直播录屏"
```

默认每 15 秒检查一次，连续 3 次检查不变后开始处理。CPU 较慢时可以使用已配置好的 CUDA：

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_recordings.py "D:\直播录屏" --device cuda:0
```

如果 ffmpeg 不在 PATH 中：

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_recordings.py "D:\直播录屏" `
  --ffmpeg "D:\ffmpeg\bin\ffmpeg.exe" `
  --ffprobe "D:\ffmpeg\bin\ffprobe.exe"
```

## 常用参数

`--once` 处理当前已有文件后退出，适合先测试。

`--poll-seconds 30 --stable-checks 4` 适合写入速度慢或文件很大的录屏。

失败任务会在对应输出目录留下 `.failed`。修复 ffmpeg、模型或显存问题后，用 `--retry-failed` 重试。
