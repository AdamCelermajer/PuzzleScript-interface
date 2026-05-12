from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


LABELS = ["correct", "partial", "wrong", "skipped"]
COLORS = {
    "correct": "#2f9e44",
    "partial": "#f59f00",
    "wrong": "#e03131",
    "skipped": "#868e96",
}


def load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def count_labels(rows: list[dict]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {label: 0 for label in LABELS}
    )
    for row in rows:
        setup = str(row.get("setup") or "unknown")
        verification = row.get("manual_verification") or {}
        label = str(verification.get("label") or "skipped")
        if label not in LABELS:
            label = "skipped"
        counts[setup][label] += 1
    return dict(counts)


def write_csv(path: Path, counts: dict[str, dict[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["setup", *LABELS, "verified_total"])
        for setup, labels in sorted(counts.items()):
            verified_total = labels["correct"] + labels["partial"] + labels["wrong"]
            writer.writerow(
                [setup, *[labels[label] for label in LABELS], verified_total]
            )


def svg_bar_chart(counts: dict[str, dict[str, int]]) -> str:
    setups = sorted(counts)
    width = 760
    height = 120 + 70 * max(1, len(setups))
    left = 160
    bar_width = 420
    row_height = 55
    max_total = max((sum(counts[setup].values()) for setup in setups), default=1)
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        (
            '<text x="20" y="32" font-family="Arial" font-size="20" '
            'font-weight="700">Goal Recognition Verification</text>'
        ),
    ]
    for row_index, setup in enumerate(setups):
        y = 70 + row_index * row_height
        x = left
        labels = counts[setup]
        total = sum(labels.values()) or 1
        lines.append(
            f'<text x="20" y="{y + 18}" font-family="Arial" '
            f'font-size="14">{setup}</text>'
        )
        for label in LABELS:
            value = labels[label]
            segment = int((value / max_total) * bar_width)
            if value:
                lines.append(
                    f'<rect x="{x}" y="{y}" width="{segment}" '
                    f'height="24" fill="{COLORS[label]}"/>'
                )
                lines.append(
                    f'<text x="{x + 4}" y="{y + 17}" font-family="Arial" '
                    f'font-size="12" fill="white">{value}</text>'
                )
            x += segment
        lines.append(
            f'<text x="{left + bar_width + 20}" y="{y + 18}" '
            f'font-family="Arial" font-size="13">total {total}</text>'
        )
    legend_x = 20
    legend_y = height - 30
    for label in LABELS:
        lines.append(
            f'<rect x="{legend_x}" y="{legend_y - 12}" width="12" '
            f'height="12" fill="{COLORS[label]}"/>'
        )
        lines.append(
            f'<text x="{legend_x + 18}" y="{legend_y - 2}" '
            f'font-family="Arial" font-size="12">{label}</text>'
        )
        legend_x += 100
    lines.append("</svg>")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report goal-recognition verification results."
    )
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--out", type=Path, default=Path("side_quests/goal_recognition_review/report")
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = load_rows(args.runs)
    counts = count_labels(rows)
    csv_path = args.out.with_suffix(".csv")
    svg_path = args.out.with_suffix(".svg")
    write_csv(csv_path, counts)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg_bar_chart(counts), encoding="utf-8")
    print(f"csv: {csv_path}")
    print(f"svg: {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
