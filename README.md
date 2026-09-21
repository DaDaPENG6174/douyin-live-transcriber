# 直播录屏自动转写与话术分析工具

一个面向 Windows 的本地直播录屏处理工具：监控 OBS 录屏目录，等待视频写入完成后自动提取音频、使用本地 FunASR 转写，并在桌面界面中展示任务进度、预计剩余时间和视频清单。

项目默认使用 NVIDIA CUDA 加速，也支持 CPU。录制连线内容时，如果 OBS 将主播和连线嘉宾分别录到不同音轨，工具会分别转写并输出说话人标签。

## 功能

- 自动监控录屏文件夹及子目录
- 等待文件大小稳定后再开始处理，避免读取尚未写完的录屏
- 使用 FFmpeg 提取音频并读取媒体信息
- 使用 FunASR SenseVoiceSmall 进行本地中文转写
- 支持 GPU（CUDA）和 CPU
- 支持多音轨转写：默认标记为“主播”和“连线嘉宾”
- Tkinter 桌面界面：显示总数、已完成、待处理、失败、当前进度和预计剩余时间
- 输出 TXT、JSON、SRT，便于编辑、检索和字幕制作
- 保留原始 Markdown 工作流文档，并提供 Markdown 转 Word 工具

## 环境要求

- Windows 10/11
- Python 3.12（推荐使用项目虚拟环境）
- FFmpeg 和 FFprobe
- NVIDIA GPU 可选；当前 CUDA 安装方案为 CUDA 11.8 PyTorch
- 首次运行需要下载 FunASR/ModelScope 模型

## 快速开始

### 1. 安装依赖

```powershell
cd "C:\path\to\project"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
```

如果使用 CUDA，请确认显卡可用：

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

### 2. 启动桌面界面

把 `start_dashboard.vbs` 中的录屏目录和 FFmpeg 路径改成自己的路径，然后双击它。该启动器使用 `pythonw.exe`，不会弹出命令行窗口。

默认配置：

```text
录屏目录：D:\直播录屏
设备：cuda:0
音轨标签：主播,连线嘉宾
```

也可以使用备用批处理入口 `start_watcher.bat`。

### 3. 命令行运行

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_recordings.py "D:\直播录屏" --device cuda:0
```

单次处理当前文件后退出：

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_recordings.py "D:\直播录屏" --once --device cuda:0
```

## OBS 连线多音轨

在 OBS 的高级音频属性中，将主播麦克风放到音轨 1，将浏览器/连线声音放到音轨 2，背景音乐建议单独放到音轨 3。工具会把音轨 1、2 默认映射为：

```text
[主播] ...
[连线嘉宾] ...
```

如果视频只有一条混合音轨，工具会标记为 `[混合音轨]`，不会伪造说话人身份。详细说明见 [MULTITRACK_README.md](MULTITRACK_README.md)。

## 输出结构

每个录屏对应一个输出目录：

```text
output/<录屏文件名>/
├── source.json
├── metadata/media.json
├── tracks/                 # 多音轨时每条音轨的独立音频和转写
├── transcript.json         # 带时间戳和 speaker 字段
├── transcript.txt
└── transcript.srt
```

## 项目结构

```text
scripts/
├── watcher_gui.py           # 桌面监控界面
├── watch_recordings.py      # 命令行监控器
├── transcribe_local.py      # 单音频本地转写
├── transcribe_multitrack.py # 多音轨转写与合并
├── md_to_docx.py            # Markdown 转 Word
└── extract_audio.ps1        # 手动提取音频
docs/                        # 直播分析和工作流说明
```

## 设计边界

本项目默认离线处理音频，不调用付费云端转写 API。单一混合音轨无法可靠判断说话人；需要主播/嘉宾身份时，优先在录制阶段使用 OBS 分轨。

## 许可

当前仓库未附加开源许可证，代码和文档的使用权按仓库所有者声明执行。如需公开复用，建议后续选择合适的许可证。
