import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from frameworks.avo.core import player_view
from frameworks.avo.core.framework import Action, AvoLaboratory, Comparison, Observation
from frameworks.avo.core.profile import TaskEvaluation
from frameworks.avo.core.tool_gateway import AvoToolGateway, FileToolServer, GatewayBudget
from frameworks.avo.evolution.solver_evaluation import evaluate_solver_workspace

PATTERNS = {"0": [[[1, 2, 3, 255]]], "1": [[[4, 5, 6, 255]]]}


class SlideEnvironment:
    """Boards like the game service: a move returns the board before it, then one per engine step."""

    def __init__(self) -> None:
        self.position = 0

    @staticmethod
    def _board(position: int) -> list[list[int]]:
        return [[1 if column == position else 0 for column in range(4)]]

    def reset(self) -> Observation:
        self.position = 0
        return self._observation([self._board(0)])

    def step(self, action: Action) -> Observation:
        frames = [self._board(self.position)]
        if action.id == "A1":  # slides to the far end, one engine step per tile
            while self.position < 3:
                self.position += 1
                frames.append(self._board(self.position))
        else:
            frames.append(self._board(self.position))
        return self._observation(frames)

    def save_state(self) -> str:
        return str(self.position)

    def restore_state(self, token: str) -> Observation:
        self.position = int(token)
        return self._observation([self._board(self.position)])

    def _observation(self, frames: list) -> Observation:
        return Observation(
            payload={"frame": frames},
            status="WIN" if self.position == 3 else "PLAYING",
            progress={"levels_completed": int(self.position == 3), "win_levels": 1},
            available_actions=("A1", "A2"),
            metadata={"projection": {"mode": "visible-cell-v1", "patterns": PATTERNS}},
        )

    def compare(self, expected: Observation, actual: Observation) -> Comparison:
        return Comparison(expected.payload == actual.payload, float(expected.payload == actual.payload), 1, 1)


class SlideProfile:
    profile_id = "slide"
    objective = "Reach the far end."

    def __init__(self, environment: SlideEnvironment) -> None:
        self.environment = environment

    def evaluate(self, history, current) -> TaskEvaluation:
        done = current.status == "WIN"
        return TaskEvaluation(terminal=done, success=done, fitness=float(done),
                              score={"levels_completed": int(done), "environment_actions": len(history)})


def tool(workspace: Path, *arguments: str) -> str:
    return subprocess.run([sys.executable, "avo_tool.py", *arguments], cwd=workspace, capture_output=True,
                          text=True, timeout=10, check=True).stdout


class PlayerViewTests(unittest.TestCase):
    def test_a_move_shows_only_the_current_board_and_history_keeps_every_board(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace, evidence = Path(root) / "workspace", Path(root) / "evidence"
            environment = SlideEnvironment()
            gateway = AvoToolGateway(AvoLaboratory(environment, [], evidence), SlideProfile(environment),
                                     budget=GatewayBudget(max_environment_steps=5))
            server = FileToolServer(gateway, workspace)
            server.start()
            try:
                observed = tool(workspace, "observe")
                moved = tool(workspace, "probe", "A1", "--rationale", "slide")
                boards = tool(workspace, "history", "--move", "1")
                listed = tool(workspace, "history")
            finally:
                server.stop()

            self.assertIn("board (visible-cell-v1):\n1 0 0 0", observed)
            self.assertIn("A1 (move 1, episode 1): LEVEL COMPLETED (1/1). The board below is the next level.", moved)
            self.assertIn("engine steps this move: 3; every board of it: python avo_tool.py history --move 1", moved)
            self.assertIn("board (visible-cell-v1):\n0 0 0 1", moved)
            for hidden in ("1 0 0 0", "0 1 0 0", "0 0 1 0", "255", "patterns"):
                self.assertNotIn(hidden, moved)
            self.assertIn("board 1/4, the board before the move:\n1 0 0 0", boards)
            self.assertIn("board 2/4, engine step 1:\n0 1 0 0", boards)
            self.assertIn("board 4/4, engine step 3, the final board:\n0 0 0 1", boards)
            self.assertIn("move 1 episode 1 A1: 2 cells changed, 3 engine steps, levels 0/1->1/1, state WIN", listed)
            # The run record keeps every board.
            records = [json.loads(line) for line in (evidence / "evidence.jsonl").read_text().splitlines()]
            transition = next(record for record in records if record["type"] == "transition")
            self.assertEqual(len(transition["payload"]["after"]["payload"]["frame"]), 4)

    def test_probe_lists_changed_cells_and_history_pages(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            environment = SlideEnvironment()
            gateway = AvoToolGateway(AvoLaboratory(environment, [], Path(root)), SlideProfile(environment),
                                     budget=GatewayBudget(max_environment_steps=30))
            gateway.handle("observe")
            for _ in range(3):
                result = gateway.handle("probe", {"action_id": "A2"})
            self.assertIn("A2 (move 3, episode 1): nothing changed", player_view.render("probe", result))
            page = gateway.handle("history", {"offset": 1, "limit": 1})
            self.assertEqual([move["move"] for move in page["moves"]], [2])
            self.assertIn("move 2 episode 1 A2: nothing changed, 1 engine step,", player_view.render("history", page))
            gateway.handle("acknowledge_supervisor", {"response": "try A1"})
            saved = gateway.handle("checkpoint", {"label": "start"})
            reset = player_view.render("reset", gateway.handle("reset", {"reason": "fresh start"}))
            self.assertIn("Episode 2 started from a fresh reset.\nstate=PLAYING levels=0/1", reset)
            restored = player_view.render("restore", gateway.handle("restore", {"checkpoint_id": saved["checkpoint_id"]}))
            self.assertIn("Restored cp_001; episode 3 started.", restored)
            self.assertIn("board (visible-cell-v1):\n1 0 0 0", restored)
            self.assertEqual(gateway.handle("history", {})["count"], 3)
            with self.assertRaisesRegex(ValueError, "No move 9"):
                gateway.handle("history", {"move": 9})

    def test_the_solver_reads_the_current_board_only(self) -> None:
        observation = {"payload": {"frame": [[[1]], [[2]], [[3]]]}, "status": "PLAYING",
                       "metadata": {"projection": {"mode": "visible-cell-v1", "patterns": PATTERNS}}}
        current = player_view.current_only(observation)
        self.assertEqual(current["payload"]["frame"], [[[3]]])
        self.assertEqual(current["metadata"]["projection"], {"mode": "visible-cell-v1"})
        self.assertEqual(len(observation["payload"]["frame"]), 3)  # the record is untouched

        solver = r'''import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--play", action="store_true")
parser.add_argument("--max-steps", type=int)
parser.parse_args()
for number, line in enumerate(sys.stdin):
    print(line.strip(), file=sys.stderr, flush=True)
    print(json.dumps({"action": "A2" if number == 0 else "A1"}), flush=True)
'''
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            (workspace / "solver.py").write_text(solver, encoding="utf-8")
            result = evaluate_solver_workspace(
                loaded_profile=SimpleNamespace(implementation=SlideProfile(SlideEnvironment())),
                workspace=workspace, output_dir=Path(root) / "evaluation",
                max_environment_steps=3, max_wall_seconds=30)
            seen = [json.loads(line)["observation"] for line in
                    (Path(root) / "evaluation" / "solver_stderr.txt").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(result.success)
        # After A2 the record holds 2 boards; the solver sees only the current one.
        self.assertEqual([observation["payload"]["frame"] for observation in seen],
                         [[[[1, 0, 0, 0]]], [[[1, 0, 0, 0]]]])
        self.assertNotIn("patterns", json.dumps(seen))


if __name__ == "__main__":
    unittest.main()
