import unittest

from client.engine import prompts


class PromptTests(unittest.TestCase):
    def test_deduce_rules_prompt_includes_required_summary_field(self) -> None:
        system, _user = prompts.get_deduce_rules_prompt(
            events="Event 1:\nAction: ACTION4",
            known_rules_text="",
            focus_prompt="",
            game_name="test-grid",
        )

        self.assertIn('"summary"', system)
        self.assertIn("Every rule must include", system)


if __name__ == "__main__":
    unittest.main()
