import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from puzzlescript_arc.catalog import build_catalog, resolve_game_entry  # type: ignore[import-not-found]


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.games_dir = os.path.join(ROOT, "games")

    def test_build_catalog_uses_versioned_game_ids_and_human_titles(self) -> None:
        catalog = build_catalog(self.games_dir)

        sokoban = next(
            entry for entry in catalog if entry.game_id == "sokoban-basic-v1"
        )

        self.assertEqual(sokoban.title, "sokoban-basic")
        self.assertEqual(sokoban.source_name, "sokoban-basic")

    def test_resolve_game_entry_accepts_title_aliases(self) -> None:
        catalog = build_catalog(self.games_dir)

        entry = resolve_game_entry(catalog, "sokoban-basic")

        self.assertEqual(entry.game_id, "sokoban-basic-v1")


if __name__ == "__main__":
    unittest.main()
