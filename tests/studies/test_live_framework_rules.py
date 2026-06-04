import tempfile
import unittest
import json
from pathlib import Path

from client.engine.types import GameAction
from studies.LIVE_framework.model import SymbolFrame
from studies.LIVE_framework.rules import LiveRuleModel


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
                    "At(*a,x+1,y)",
                    "NOT At(#,x+2,y)",
                    "NOT At(*b,x+2,y)",
                )
            ]

        self.assertIn(SymbolFrame.from_rows(["..P*"]), predictions)
        self.assertEqual(len(push_rules), 1)
        self.assertEqual(push_rules[0].attributed_action, "ACTION4(P)")
        self.assertEqual(
            push_rules[0].effect_facts,
            (
                "Remove(At(P,x,y))",
                "Add(At(P,x+1,y))",
                "Remove(At(*a,x+1,y))",
                "Add(At(*a,x+2,y))",
            ),
        )

    def test_move_rule_effects_are_real_at_differences(self) -> None:
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
            move_rule = model.active_rules("ACTION4")[0]

        self.assertEqual(
            move_rule.condition_facts,
            ("At(P,x,y)", "NOT At(#,x+1,y)", "NOT At(*a,x+1,y)"),
        )
        self.assertEqual(
            move_rule.effect_facts,
            ("Remove(At(P,x,y))", "Add(At(P,x+1,y))"),
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
                if rule.condition_facts
                == ("At(P,x,y)", "NOT At(#,x+1,y)", "NOT At(*a,x+1,y)")
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
                    "At(*a,x+1,y)",
                    "NOT At(#,x+2,y)",
                    "NOT At(*b,x+2,y)",
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
                    "At(*a,x+1,y)",
                    "At(#,x+2,y)",
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

    def test_reachable_context_selection_does_not_count_as_an_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )
            context = (
                "P",
                "ACTION1(P)",
                0,
                -1,
                ("At(P,x,y)", "At(*a,x,y-1)"),
            )

            model.record_explorer_selection(
                GameAction.ACTION4,
                "reachable_unseen_context",
                context,
            )

        self.assertEqual(model.context_attempts, {})

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
        self.assertIn("ACTION4(P): dx=1, dy=0", text)
        self.assertIn("ACTION4(P)", text)
        self.assertIn("At(P,x,y)", text)
        self.assertIn("NOT At(#,x+1,y)", text)
        self.assertNotIn("EmptyForMotion", text)
        self.assertNotIn("CrateBearing", text)
        self.assertNotIn("Learned Terms", text)
        self.assertNotIn("ActionDelta", text)
        self.assertIn("created", growth)
        self.assertNotIn("Player", text)
        self.assertNotIn("Wall", text)

    def test_rule_markdown_uses_paper_style_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            model = LiveRuleModel(
                output_path=output,
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                SymbolFrame.from_rows(["P."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P"]),
            )
            text = output.read_text(encoding="utf-8")

        self.assertIn("Index:      R001", text)
        self.assertIn(
            "Condition:  At(P,x,y) AND NOT At(#,x+1,y) AND NOT At(*a,x+1,y)",
            text,
        )
        self.assertIn("Action:     ACTION4(P)", text)
        self.assertIn(
            "Prediction: NOT At(P,x,y) AND At(P,x+1,y)",
            text,
        )
        self.assertIn("Sibling:    -", text)
        self.assertNotIn("- raw_action:", text)

    def test_writes_compact_rules_only_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            compact = Path(tmpdir) / "rules_compact.md"
            model = LiveRuleModel(
                output_path=output,
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                SymbolFrame.from_rows(["P."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P"]),
            )
            text = compact.read_text(encoding="utf-8")

        self.assertEqual(
            text.strip(),
            "ACTION4(P): At(P,x,y) & !At(#,x+1,y) & !At(*a,x+1,y) => "
            "!At(P,x,y) & At(P,x+1,y)",
        )
        self.assertNotIn("State is represented", text)
        self.assertNotIn("Current Symbol Frame", text)
        self.assertNotIn("Append-only growth journal", text)
        self.assertNotIn("R001", text)

    def test_compact_rules_file_deduplicates_same_rule_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            compact = Path(tmpdir) / "rules_compact.md"
            model = LiveRuleModel(
                output_path=output,
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            model.observe(
                SymbolFrame.from_rows(["P."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P"]),
            )
            duplicate = model.active_rules("ACTION4")[0]
            model.rules.append(
                type(duplicate)(
                    id="R999",
                    action=duplicate.action,
                    actor_symbol=duplicate.actor_symbol,
                    dx=duplicate.dx,
                    dy=duplicate.dy,
                    conditions=duplicate.conditions,
                    effects=duplicate.effects,
                )
            )
            model.write()
            text = compact.read_text(encoding="utf-8")

        self.assertEqual(len(text.strip().splitlines()), 1)

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

        self.assertEqual(data["version"], 5)
        self.assertNotIn("terms", data)
        self.assertEqual(data["rules"][0]["attributed_action"], "ACTION4(P)")
        self.assertEqual(
            data["rules"][0]["conditions"],
            [
                {"index": 0, "kind": "at", "symbol": "P"},
                {"index": 1, "kind": "crate", "symbol": "*a"},
                {"index": 2, "kind": "clear", "symbol": None},
            ],
        )
        self.assertNotIn("before_symbols", data["rules"][0])
        self.assertNotIn("after_symbols", data["rules"][0])


if __name__ == "__main__":
    unittest.main()
