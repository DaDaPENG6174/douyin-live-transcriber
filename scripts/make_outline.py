import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--step", type=int, default=10)
    args = ap.parse_args()
    data = json.loads(args.transcript.read_text(encoding="utf-8"))
    buckets = {}
    for s in data["segments"]:
        bucket = int(s["start"] // (args.step * 60))
        buckets.setdefault(bucket, []).append(s)
    lines = [f"# Outline ({args.step}-minute buckets)\n"]
    for n in sorted(buckets):
        items = buckets[n]
        text = " ".join(s["text"] for s in items).strip()
        preview = text[:650]
        if len(text) > 950:
            preview += " ... " + text[-300:]
        lines.append(f"## {n * args.step:03d}-{(n + 1) * args.step:03d} min\n")
        lines.append(preview + "\n")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
