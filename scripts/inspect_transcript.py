import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--keywords", nargs="+", default=[
        "换个地方", "换地方", "下播", "关注", "点赞", "评论", "微信", "私信",
        "连麦", "咨询", "直播间", "公屏", "主页", "预约", "加入", "付费",
        "报名", "服务", "问题", "明天", "下次", "群", "课程", "资料",
    ])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    data = json.loads(args.transcript.read_text(encoding="utf-8"))
    segments = data["segments"]
    lines = [f"# Transcript index\n\nSegments: {len(segments)}\n"]

    lines.append("## Keyword hits\n")
    for item in segments:
        hits = [word for word in args.keywords if word in item["text"]]
        if hits:
            lines.append(
                f"- `{item['start'] / 60:.2f} min` "
                f"({item['start']:.2f}-{item['end']:.2f}s) "
                f"[{', '.join(hits)}] {item['text']}"
            )

    lines.append("\n## Minute buckets\n")
    buckets = {}
    for item in segments:
        minute = int(item["start"] // 60)
        buckets.setdefault(minute, []).append(item["text"])
    for minute, texts in buckets.items():
        lines.append(f"### {minute:03d}-{minute + 1:03d} min")
        lines.append(" ".join(texts))
        lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"Minutes: {len(buckets)}")
    print(f"Keyword hits: {sum(1 for item in segments if any(word in item['text'] for word in args.keywords))}")


if __name__ == "__main__":
    main()
