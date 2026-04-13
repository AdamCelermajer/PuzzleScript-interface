import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import re
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _visible_symbol_count(file_path: Path) -> int:
    in_legend = False
    visible_symbols = 0
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "LEGEND":
            in_legend = True
            continue
        if in_legend and line == "COLLISIONLAYERS":
            break
        if in_legend and re.match(r"^[A-Za-z0-9.\-]\s*=\s*", line):
            visible_symbols += 1
    return visible_symbols


def _budget_violation(game_dir: str) -> tuple[str, int] | None:
    script_path = Path(game_dir) / "script.txt"
    count = _visible_symbol_count(script_path)
    if count > 15:
        return (Path(game_dir).name, count)
    return None


class CatalogBudgetTests(unittest.TestCase):
    def test_all_remaining_games_fit_arc_visible_symbol_budget(self) -> None:
        games_root = Path(ROOT) / "puzzlescript_interface" / "games"
        game_dirs = [
            str(path)
            for path in games_root.iterdir()
            if path.is_dir() and (path / "script.txt").exists()
        ]

        with ProcessPoolExecutor() as executor:
            violations = [
                result
                for result in executor.map(_budget_violation, game_dirs)
                if result is not None
            ]

        self.assertEqual([], sorted(violations))


if __name__ == "__main__":
    unittest.main()
