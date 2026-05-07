import tempfile
import unittest
import json
from pathlib import Path

from client.engine.types import GameAction
from client.live_sokoban.model import SymbolFrame
from client.live_sokoban.rules import LiveRuleModel


class LiveRuleTests(unittest.TestCase):
    def test_learns_action_delta_from_observed_symbol_motion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                SymbolFrame.from_rows(["P.."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P."]),
            )

        self.assertEqual(model.action_deltas[("ACTION4", "P")], (1, 0))

    def test_generalizes_blocked_percept_rule_to_new_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            model.observe(
                SymbolFrame.from_rows(["P.."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P."]),
            )
            model.observe(
                SymbolFrame.from_rows(["P#."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows(["P#."]),
            )

            predictions = model.predict(
                SymbolFrame.from_rows([".P#"]),
                GameAction.ACTION4,
            )

        self.assertIn(SymbolFrame.from_rows([".P#"]), predictions)

    def test_generalizes_three_cell_percept_interaction_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            model.observe(
                SymbolFrame.from_rows(["P.."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P."]),
            )
            model.observe(
                SymbolFrame.from_rows(["P*."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P*"]),
            )

            predictions = model.predict(
                SymbolFrame.from_rows([".P*."]),
                GameAction.ACTION4,
            )
            push_rules = [
                rule
                for rule in model.active_rules("ACTION4")
                if rule.condition_facts == (
                    "At(P,x,y)",
                    "CrateBearing(x+1,y)",
                    "EmptyForMotion(x+2,y)",
                )
            ]

        self.assertIn(SymbolFrame.from_rows(["..P*"]), predictions)
        self.assertEqual(len(push_rules), 1)
        self.assertEqual(push_rules[0].attributed_action, "ACTION4(P)")
        self.assertEqual(
            push_rules[0].effect_facts,
            (
                "Clear(P,x,y)",
                "Set(P,x+1,y)",
                "Clear(CrateBearing,x+1,y)",
                "Set(CrateBearing,x+2,y)",
            ),
        )

    def test_target_floor_variants_collapse_into_one_move_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            model.observe(
                SymbolFrame.from_rows(["P."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P"]),
            )
            model.observe(
                SymbolFrame.from_rows(["..", "P."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows(["..", "OP"]),
            )

            predictions = model.predict(
                SymbolFrame.from_rows(["..", "P."]),
                GameAction.ACTION4,
            )
            move_rules = [
                rule
                for rule in model.active_rules("ACTION4")
                if rule.condition_facts == ("At(P,x,y)", "EmptyForMotion(x+1,y)")
            ]

        self.assertEqual(len(move_rules), 1)
        self.assertEqual(move_rules[0].observations, 2)
        self.assertIn(SymbolFrame.from_rows(["..", "OP"]), predictions)

    def test_target_crate_variants_collapse_into_one_push_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            model.observe(
                SymbolFrame.from_rows(["P*."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P*"]),
            )
            model.observe(
                SymbolFrame.from_rows(["P*O"]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P@"]),
            )
            model.observe(
                SymbolFrame.from_rows(["P@."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P*"]),
            )

            predictions = model.predict(
                SymbolFrame.from_rows(["P*O"]),
                GameAction.ACTION4,
            )
            push_rules = [
                rule
                for rule in model.active_rules("ACTION4")
                if rule.condition_facts == (
                    "At(P,x,y)",
                    "CrateBearing(x+1,y)",
                    "EmptyForMotion(x+2,y)",
                )
            ]

        self.assertEqual(len(push_rules), 1)
        self.assertEqual(push_rules[0].observations, 3)
        self.assertIn(SymbolFrame.from_rows([".P@"]), predictions)

    def test_push_learning_does_not_create_direct_crate_action_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                SymbolFrame.from_rows(["P*."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P*"]),
            )
            text = (Path(tmpdir) / "rules.md").read_text(encoding="utf-8")

        self.assertEqual(model.action_deltas, {("ACTION4", "P"): (1, 0)})
        self.assertNotIn("ActionDelta(ACTION4,*,1,0)", text)

    def test_blocked_push_is_actor_anchored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            model.observe(
                SymbolFrame.from_rows(["P.."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P."]),
            )
            model.observe(
                SymbolFrame.from_rows(["P*#"]),
                GameAction.ACTION4,
                SymbolFrame.from_rows(["P*#"]),
            )

            predictions = model.predict(
                SymbolFrame.from_rows([".P*#"]),
                GameAction.ACTION4,
            )
            blocked_rules = [
                rule
                for rule in model.active_rules("ACTION4")
                if rule.condition_facts == (
                    "At(P,x,y)",
                    "CrateBearing(x+1,y)",
                    "Solid(x+2,y)",
                )
            ]

        self.assertIn(SymbolFrame.from_rows([".P*#"]), predictions)
        self.assertEqual(len(blocked_rules), 1)
        self.assertEqual(blocked_rules[0].attributed_action, "ACTION4(P)")
        self.assertEqual(blocked_rules[0].effect_facts, ())

    def test_prediction_failure_creates_complementary_sibling_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            journal = Path(tmpdir) / "journal.md"
            model = LiveRuleModel(
                output_path=output,
                store_path=Path(tmpdir) / "rules.json",
                journal_path=journal,
                load_existing=False,
            )
            parent_before = SymbolFrame.from_rows(["P.."])
            parent_after = SymbolFrame.from_rows([".P."])
            model.observe(parent_before, GameAction.ACTION4, parent_after)
            predictions = model.predict(
                SymbolFrame.from_rows(["P.#"]),
                GameAction.ACTION4,
            )

            model.record_prediction_result(
                SymbolFrame.from_rows(["P.#"]),
                GameAction.ACTION4,
                SymbolFrame.from_rows(["P.#"]),
                predictions,
            )
            sibling_predictions = model.predict(
                SymbolFrame.from_rows(["P.#"]),
                GameAction.ACTION4,
            )
            rules_text = output.read_text(encoding="utf-8")
            journal_text = journal.read_text(encoding="utf-8")

        siblings = [rule for rule in model.rules if rule.parent_id is not None]
        self.assertGreaterEqual(len(siblings), 2)
        self.assertIn(SymbolFrame.from_rows(["P.#"]), sibling_predictions)
        self.assertIn("Sibling Rule Families", rules_text)
        self.assertIn("created sibling family", journal_text)

    def test_rule_files_persist_and_show_growth_without_object_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            store = Path(tmpdir) / "rules.json"
            journal = Path(tmpdir) / "journal.md"
            model = LiveRuleModel(
                output_path=output,
                store_path=store,
                journal_path=journal,
                load_existing=False,
            )
            model.observe(
                SymbolFrame.from_rows(["P.."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P."]),
            )

            loaded = LiveRuleModel(
                output_path=output,
                store_path=store,
                journal_path=journal,
            )
            text = output.read_text(encoding="utf-8")
            growth = journal.read_text(encoding="utf-8")

        self.assertEqual(loaded.action_deltas[("ACTION4", "P")], (1, 0))
        self.assertIn("ActionDelta(ACTION4,P,1,0)", text)
        self.assertIn("ACTION4(P)", text)
        self.assertIn("At(P,x,y)", text)
        self.assertIn("EmptyForMotion(x+1,y)", text)
        self.assertIn("CrateBearing", text)
        self.assertIn("created", growth)
        self.assertNotIn("Player", text)
        self.assertNotIn("Wall", text)

    def test_load_skips_old_symbol_line_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Path(tmpdir) / "rules.json"
            store.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "next_id": 3,
                        "context_attempts": [],
                        "action_deltas": [
                            {"action": "ACTION4", "symbol": "P", "dx": 1, "dy": 0},
                            {"action": "ACTION4", "symbol": "*", "dx": 1, "dy": 0},
                        ],
                        "rules": [
                            {
                                "id": "R001",
                                "action": "ACTION4",
                                "anchor_symbol": "P",
                                "dx": 1,
                                "dy": 0,
                                "before_symbols": ["P", "*", "."],
                                "after_symbols": [".", "P", "*"],
                                "status": "active",
                            },
                            {
                                "id": "R002",
                                "action": "ACTION4",
                                "anchor_symbol": "*",
                                "dx": 1,
                                "dy": 0,
                                "before_symbols": ["*", "."],
                                "after_symbols": [".", "*"],
                                "status": "active",
                            },
                        ],
                        "failures": [],
                    }
                ),
                encoding="utf-8",
            )

            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=store,
                journal_path=Path(tmpdir) / "journal.md",
            )

        self.assertEqual(model.action_deltas, {("ACTION4", "P"): (1, 0)})
        self.assertEqual(model.rules, [])

    def test_store_uses_attributed_percept_rules_not_symbol_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Path(tmpdir) / "rules.json"
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=store,
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                SymbolFrame.from_rows(["P*."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P*"]),
            )
            data = json.loads(store.read_text(encoding="utf-8"))

        self.assertEqual(data["version"], 4)
        self.assertEqual(
            data["terms"],
            [
                {
                    "name": "EmptyForMotion",
                    "kind": "symbol_class",
                    "symbols": [".", "O"],
                },
                {
                    "name": "CrateBearing",
                    "kind": "symbol_class",
                    "symbols": ["*", "@"],
                },
                {
                    "name": "TargetBase",
                    "kind": "symbol_class",
                    "symbols": ["O", "@"],
                },
                {
                    "name": "Solid",
                    "kind": "symbol_class",
                    "symbols": ["#"],
                },
            ],
        )
        self.assertEqual(data["rules"][0]["attributed_action"], "ACTION4(P)")
        self.assertEqual(
            data["rules"][0]["conditions"],
            [
                {"index": 0, "kind": "at", "symbol": "P", "term": None},
                {
                    "index": 1,
                    "kind": "term",
                    "symbol": None,
                    "term": "CrateBearing",
                },
                {
                    "index": 2,
                    "kind": "term",
                    "symbol": None,
                    "term": "EmptyForMotion",
                },
            ],
        )
        self.assertNotIn("before_symbols", data["rules"][0])
        self.assertNotIn("after_symbols", data["rules"][0])


if __name__ == "__main__":
    unittest.main()
