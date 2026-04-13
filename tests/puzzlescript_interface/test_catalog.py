import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from puzzlescript_interface.api.catalog import (  # type: ignore[import-not-found]
    build_catalog,
    resolve_game_entry,
)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.games_dir = os.path.join(ROOT, "puzzlescript_interface", "games")

    def test_build_catalog_discovers_folder_scripts_and_uses_arc_safe_ids(self) -> None:
        catalog = build_catalog(self.games_dir)

        sokoban = next(
            entry for entry in catalog if entry.game_id == "ps_sokoban_basic-v1"
        )

        self.assertEqual(sokoban.title, "sokoban-basic")
        self.assertEqual(sokoban.source_name, "ps_sokoban_basic-v1")
        self.assertEqual(
            os.path.normpath(str(sokoban.file_path)),
            os.path.normpath(
                os.path.join(self.games_dir, "ps_sokoban_basic-v1", "script.txt")
            ),
        )

    def test_resolve_game_entry_accepts_public_id_stem_lookup(self) -> None:
        catalog = build_catalog(self.games_dir)

        entry = resolve_game_entry(catalog, "ps_sokoban_basic")

        self.assertEqual(entry.game_id, "ps_sokoban_basic-v1")

    def test_resolve_game_entry_still_accepts_legacy_folder_name_lookup(self) -> None:
        catalog = build_catalog(self.games_dir)

        entry = resolve_game_entry(catalog, "sokoban-basic")

        self.assertEqual(entry.game_id, "ps_sokoban_basic-v1")

    def test_build_catalog_excludes_games_over_visible_symbol_budget(self) -> None:
        catalog = build_catalog(self.games_dir)

        game_ids = {entry.game_id for entry in catalog}

        self.assertNotIn("ps_bouncers-v1", game_ids)


if __name__ == "__main__":
    unittest.main()
