from __future__ import annotations


class Progress:
    def __init__(self, total: int, label: str) -> None:
        self.total = max(total, 1)
        self.label = label
        self.current = 0

    def step(self, detail: str) -> None:
        self.current += 1
        width = 24
        filled = int(width * min(self.current, self.total) / self.total)
        bar = "#" * filled + "-" * (width - filled)
        print(
            f"\r{self.label} [{bar}] {self.current}/{self.total} {detail}",
            end="",
            flush=True,
        )
        if self.current >= self.total:
            print()
