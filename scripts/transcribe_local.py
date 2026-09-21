import argparse
import json
import re
from pathlib import Path


def clean_text(text: str) -> str:
    text = re.sub(r"<\|[^>]+\|>", "", text or "")
    return text.strip()


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def build_segments(result: dict) -> list[dict]:
    segments = []
    for item in result.get("sentence_info", []) or []:
        text = clean_text(item.get("text", ""))
        if not text:
            continue
        segments.append(
            {
                "start": round(float(item.get("start", 0)) / 1000, 3),
                "end": round(float(item.get("end", 0)) / 1000, 3),
                "text": text,
            }
        )

    if segments:
        return segments

    text = clean_text(result.get("text", ""))
    if text:
        return [{"start": 0.0, "end": 0.0, "text": text}]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Chinese transcription with FunASR SenseVoiceSmall")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda:0"])
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--vad-dir", type=Path, default=None)
    args = parser.parse_args()

    if not args.audio.is_file():
        raise SystemExit(f"Audio file not found: {args.audio}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    from funasr import AutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess

    model = AutoModel(
        model=str(args.model_dir) if args.model_dir else "iic/SenseVoiceSmall",
        vad_model=str(args.vad_dir) if args.vad_dir else "fsmn-vad",
        vad_kwargs={"max_single_segment_time": 30000},
        device=args.device,
        disable_update=True,
    )
    raw = model.generate(
        input=str(args.audio),
        language="zh",
        use_itn=True,
        batch_size_s=300,
        sentence_timestamp=True,
    )
    result = raw[0] if isinstance(raw, list) else raw
    if not isinstance(result, dict):
        result = {"text": str(result)}

    if result.get("text"):
        result["text"] = rich_transcription_postprocess(result["text"])
    segments = build_segments(result)
    for segment in segments:
        segment["text"] = rich_transcription_postprocess(segment["text"])

    payload = {
        "audio": str(args.audio.resolve()),
        "model": "iic/SenseVoiceSmall",
        "device": args.device,
        "segments": segments,
        "raw": result,
    }
    (args.out_dir / "transcript.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out_dir / "transcript.txt").write_text(
        "\n".join(segment["text"] for segment in segments) + "\n", encoding="utf-8"
    )
    srt_lines = []
    for index, segment in enumerate(segments, start=1):
        srt_lines.extend(
            [
                str(index),
                f"{format_srt_time(segment['start'])} --> {format_srt_time(segment['end'])}",
                segment["text"],
                "",
            ]
        )
    (args.out_dir / "transcript.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"Segments: {len(segments)}")
    print(f"Output: {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
