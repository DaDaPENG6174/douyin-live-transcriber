"""Extract every audio stream, transcribe each one, and merge labeled segments."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "_", value).strip()
    return value or "track"


def audio_streams(video: Path, ffprobe: str) -> list[dict]:
    result = subprocess.run(
        [ffprobe, "-v", "quiet", "-select_streams", "a", "-show_entries", "stream=index:stream_tags=title", "-of", "json", str(video)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout).get("streams", [])


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe all audio streams with speaker labels")
    parser.add_argument("video", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda:0"], default="cpu")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--track-labels", default="主播,连线嘉宾")
    args = parser.parse_args()
    if not args.video.is_file():
        raise SystemExit(f"Video file not found: {args.video}")

    streams = audio_streams(args.video, args.ffprobe)
    if not streams:
        raise SystemExit("No audio stream found in video")
    configured = [item.strip() for item in args.track_labels.split(",") if item.strip()]
    labels = configured or [f"音轨{i + 1}" for i in range(len(streams))]
    if len(streams) == 1:
        labels = ["混合音轨"]
    while len(labels) < len(streams):
        labels.append(f"音轨{len(labels) + 1}")

    tracks_dir = args.out_dir / "tracks"
    tracks_dir.mkdir(parents=True, exist_ok=True)
    merged: list[dict] = []
    track_info: list[dict] = []
    transcriber = Path(__file__).with_name("transcribe_local.py")
    for ordinal, stream in enumerate(streams):
        label = labels[ordinal]
        track_dir = tracks_dir / f"{ordinal + 1:02d}_{safe_name(label)}"
        audio_dir = track_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio = audio_dir / "normalized.wav"
        subprocess.run(
            [args.ffmpeg, "-y", "-i", str(args.video), "-map", f"0:a:{ordinal}", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)],
            check=True,
        )
        subprocess.run(
            [sys.executable, str(transcriber), str(audio), "--out-dir", str(track_dir), "--device", args.device],
            check=True,
        )
        data = json.loads((track_dir / "transcript.json").read_text(encoding="utf-8"))
        segments = data.get("segments", [])
        for item in segments:
            merged.append({
                "start": item.get("start", 0),
                "end": item.get("end", 0),
                "speaker": label,
                "text": item.get("text", ""),
            })
        track_info.append({"label": label, "stream_index": stream.get("index"), "directory": str(track_dir.resolve()), "segments": len(segments)})

    merged.sort(key=lambda item: (float(item.get("start", 0)), float(item.get("end", 0))))
    payload = {
        "video": str(args.video.resolve()),
        "model": "iic/SenseVoiceSmall",
        "device": args.device,
        "speaker_mode": "separate_audio_tracks" if len(streams) > 1 else "mixed_audio_track",
        "tracks": track_info,
        "segments": merged,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "transcript.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "transcript.txt").write_text(
        "\n".join(f"[{item['speaker']}] {item['text']}" for item in merged) + "\n", encoding="utf-8"
    )
    srt_lines = []
    for index, item in enumerate(merged, start=1):
        srt_lines.extend([
            str(index),
            f"{format_srt_time(float(item['start']))} --> {format_srt_time(float(item['end']))}",
            f"[{item['speaker']}] {item['text']}",
            "",
        ])
    (args.out_dir / "transcript.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"Audio streams: {len(streams)}")
    print(f"Segments: {len(merged)}")
    print(f"Output: {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
