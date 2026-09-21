"""Watch a recording folder and transcribe completed video files locally."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".ts", ".webm"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatically transcribe completed recordings.")
    parser.add_argument("watch_dir", type=Path, help="Folder containing live recordings")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--stable-checks", type=int, default=3)
    parser.add_argument("--device", choices=["cpu", "cuda:0"], default="cpu")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--track-labels", default="主播,连线嘉宾")
    parser.add_argument("--once", action="store_true", help="Process current files and exit")
    parser.add_argument("--retry-failed", action="store_true")
    return parser.parse_args()


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def find_recordings(watch_dir: Path, output_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in watch_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in VIDEO_EXTENSIONS
            and not is_inside(path, output_dir)
        ),
        key=lambda path: path.stat().st_mtime,
    )


def wait_until_stable(path: Path, checks: int, poll_seconds: float) -> bool:
    previous = None
    unchanged = 0
    while path.exists():
        stat = path.stat()
        current = (stat.st_size, stat.st_mtime_ns)
        if current == previous and stat.st_size > 0:
            unchanged += 1
            if unchanged >= checks:
                return True
        else:
            unchanged = 0
            previous = current
        time.sleep(poll_seconds)
    return False


def job_dir_for(video: Path, output_dir: Path) -> Path:
    candidate = output_dir / video.stem
    source_file = candidate / "source.json"
    if not candidate.exists() or not source_file.exists():
        return candidate
    try:
        if json.loads(source_file.read_text(encoding="utf-8")).get("path") == str(video.resolve()):
            return candidate
    except (OSError, json.JSONDecodeError):
        pass
    return output_dir / f"{video.stem}_{video.suffix[1:].lower()}"


def process_recording(video: Path, args: argparse.Namespace) -> None:
    job_dir = job_dir_for(video, args.output_dir)
    metadata_dir = job_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    marker = job_dir / ".failed"
    if (job_dir / "transcript.json").exists():
        logging.info("Skip completed: %s", video)
        return
    if marker.exists() and not args.retry_failed:
        logging.info("Skip failed (use --retry-failed): %s", video)
        return

    source = {"path": str(video.resolve()), "size": video.stat().st_size, "modified": video.stat().st_mtime}
    (job_dir / "source.json").write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Extracting audio tracks: %s", video)
    try:
        with (metadata_dir / "media.json").open("w", encoding="utf-8") as output:
            subprocess.run(
                [args.ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(video)],
                check=True,
                stdout=output,
            )
        subprocess.run(
            [sys.executable, str(Path(__file__).with_name("transcribe_multitrack.py")), str(video), "--out-dir", str(job_dir), "--device", args.device, "--ffmpeg", args.ffmpeg, "--ffprobe", args.ffprobe, "--track-labels", args.track_labels],
            check=True,
        )
        marker.unlink(missing_ok=True)
        logging.info("Finished: %s -> %s", video, job_dir)
    except (OSError, subprocess.CalledProcessError) as exc:
        marker.write_text(str(exc), encoding="utf-8")
        logging.exception("Failed: %s", video)


def main() -> None:
    args = parse_args()
    args.watch_dir = args.watch_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    if not args.watch_dir.is_dir():
        raise SystemExit(f"Watch folder not found: {args.watch_dir}")
    if args.stable_checks < 1 or args.poll_seconds <= 0:
        raise SystemExit("--stable-checks must be >= 1 and --poll-seconds must be > 0")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seen: set[Path] = set()
    logging.info("Watching: %s", args.watch_dir)
    logging.info("Output: %s", args.output_dir)
    while True:
        for video in find_recordings(args.watch_dir, args.output_dir):
            if video in seen and not args.retry_failed:
                continue
            if wait_until_stable(video, args.stable_checks, args.poll_seconds):
                process_recording(video, args)
                seen.add(video)
        if args.once:
            return
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
