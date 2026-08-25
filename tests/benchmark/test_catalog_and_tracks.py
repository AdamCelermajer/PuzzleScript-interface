import unittest
from pathlib import Path

from benchmark.catalog import GAMES_ROOT, load_catalog, sample_games
from benchmark.tracks import score_rule_predictions


class CatalogAndTrackTests(unittest.TestCase):
    def test_catalog_loads_clean_per_game_artifact_folders(self):
        catalog = load_catalog()

        self.assertEqual(catalog["version"], "0.4.0")
        self.assertEqual(len(catalog["games"]), 21)
        self.assertTrue(
            all(
                game["artifact_status"] == "replay_verified"
                and game["reference"]["replay_verified"]
                and game["levels"]
                for game in catalog["games"]
            )
        )
        for game in catalog["games"]:
            game_root = GAMES_ROOT / game["game_id"]
            self.assertTrue((game_root / "game.json").is_file())
            level_root = (
                game_root
                / "levels"
                / f"level-{game['reference']['level_index']:03d}"
            )
            self.assertTrue((level_root / "solution.json").is_file())
            self.assertTrue((level_root / "rule-probes.json").is_file())
            self.assertTrue((level_root / "closeness.json").is_file())

    def test_sampling_is_seeded_and_track_filtered(self):
        catalog = load_catalog()
        first = sample_games(
            catalog,
            track="rule_learning",
            sample_size=5,
            seed=3838,
        )
        second = sample_games(
            catalog,
            track="rule_learning",
            sample_size=5,
            seed=3838,
        )

        self.assertEqual(
            [game["game_id"] for game in first],
            [game["game_id"] for game in second],
        )
        self.assertEqual(len(first), 5)
        self.assertTrue(
            all(game["tracks"]["rule_learning"]["enabled"] for game in first)
        )

    def test_every_rule_probe_has_a_rule_family_and_no_duplicates(self):
        catalog = load_catalog()
        probes = [
            probe
            for game in catalog["games"]
            for level in game["levels"]
            for probe in level["rule_probes_artifact"]["probes"]
        ]

        self.assertEqual(len(probes), 210)
        self.assertTrue(all(probe["fired_rule_ids"] for probe in probes))
        keys = {
            (
                str(probe["before_frame"]),
                probe["action"],
                str(probe["expected_frame"]),
            )
            for probe in probes
        }
        self.assertEqual(len(keys), len(probes))

        rule_ready = [
            game
            for game in catalog["games"]
            if game["tracks"]["rule_learning"]["enabled"]
        ]
        self.assertEqual(len(rule_ready), 21)
        self.assertTrue(
            all(
                len(
                    game["levels"][0]["rule_probes_artifact"]["probes"]
                )
                == 10
                for game in rule_ready
            )
        )

    def test_rule_score_uses_hidden_next_frame_and_transition_edits(self):
        probes = [
            {
                "probe_id": "p1",
                "game_alias": "env-0001",
                "before_frame": [[0, 1]],
                "expected_frame": [[1, 0]],
                "fired_rule_ids": ["push"],
            }
        ]
        result = score_rule_predictions(
            probes,
            [{"probe_id": "p1", "predicted_frame": [[1, 0]]}],
        )

        self.assertEqual(
            result["primary_metric"], "macro_exact_frame_accuracy"
        )
        self.assertEqual(result["summary"]["exact_frame"], 1.0)
        self.assertEqual(result["summary"]["transition_edit_f1"], 1.0)
        self.assertEqual(result["games"][0]["rule_families_correct"], 1)


if __name__ == "__main__":
    unittest.main()
