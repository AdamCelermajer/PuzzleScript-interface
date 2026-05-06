import tempfile
import unittest
from pathlib import Path

from client.engine.types import GameAction
from client.percept_live_sokoban.model import SymbolFrame
from client.percept_live_sokoban.rules import PerceptRuleModel


class PerceptRuleTests(unittest.TestCase):
    def test_learns_action_delta_from_observed_symbol_motion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = PerceptRuleModel(
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

    def test_generalizes_blocked_line_rule_to_new_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = PerceptRuleModel(
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

    def test_generalizes_three_cell_symbol_interaction_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = PerceptRuleModel(
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

        self.assertIn(SymbolFrame.from_rows(["..P*"]), predictions)

    def test_rule_files_persist_and_show_growth_without_object_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            store = Path(tmpdir) / "rules.json"
            journal = Path(tmpdir) / "journal.md"
            model = PerceptRuleModel(
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

            loaded = PerceptRuleModel(
                output_path=output,
                store_path=store,
                journal_path=journal,
            )
            text = output.read_text(encoding="utf-8")
            growth = journal.read_text(encoding="utf-8")

        self.assertEqual(loaded.action_deltas[("ACTION4", "P")], (1, 0))
        self.assertIn("ActionDelta(ACTION4,P,1,0)", text)
        self.assertIn("created", growth)
        self.assertNotIn("Player", text)
        self.assertNotIn("Crate", text)
        self.assertNotIn("Wall", text)


if __name__ == "__main__":
    unittest.main()
