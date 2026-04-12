import json
import os
import time
from typing import Callable, Optional
from dataclasses import dataclass, field

from client.engine import prompts
from client.engine.base_env import BaseEnv
from client.engine.llm_client import Config, LlmClient
from client.engine.types import GameAction, GameState, FrameData
from client.engine.utils import format_frames, extract_json


class Agent:
    """LLM-driven agent capable of both learning and solving environments."""

    def __init__(
        self,
        config: Config,
        llm_client: LlmClient,
        event_sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize learner state, rule storage, and inference memory."""
        self.cfg = config
        self.llm_client = llm_client
        self.event_sink = event_sink
        self.history: list[tuple[FrameData, GameAction, FrameData]] = []
        self.inferred_legend: dict[int, str] = {}
        self.inferred_final_goal: str = ""

        os.makedirs(self.cfg.rules_dir, exist_ok=True)
        self.rules_file = os.path.join(self.cfg.rules_dir, f"{self.cfg.game}_rules.txt")
        self.known_rules: dict[str, list[str]] = {}
        self._load_state_from_file()

    def _log(self, message: str) -> None:
        if self.event_sink is not None:
            self.event_sink(message)
            return
        print(message)

    def _unique_rules(self, rules: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for rule in rules:
            if not rule or rule in seen:
                continue
            seen.add(rule)
            unique.append(rule)
        return unique

    def _get_known_rules_text(self, prefix: str = "KNOWN RULES:") -> str:
        if not self.known_rules:
            return ""
        text = f"{prefix}\n"
        for category, rules in self.known_rules.items():
            text += f'"{category}":{{\n'
            for rule in rules:
                text += f"{rule},\n"
            text = text.rstrip(",\n") + "\n}\n\n"
        return text.strip()

    def infer_legend(
        self, history: list[tuple[FrameData, GameAction, FrameData]]
    ) -> None:
        history_log = "\n\n".join(
            (
                f"Step {i + 1}:\nAction: {action.name}\nBefore:\n{format_frames(prev_frame.frame)}\n"
                f"After:\n{format_frames(next_frame.frame)}"
            )
            for i, (prev_frame, action, next_frame) in enumerate(history)
        )
        current_legend_text = (
            f"CURRENT KNOWN LEGEND:\n{json.dumps(self.inferred_legend)}"
            if self.inferred_legend
            else "CURRENT KNOWN LEGEND: none yet"
        )
        sys_prompt, user_prompt = prompts.get_infer_legend_prompt(
            history_log, current_legend_text, game_name=self.cfg.game
        )
        response = self.llm_client._call(
            sys_prompt, user_prompt, model_type="pro", json_mode=True
        )

        try:
            parsed = json.loads(extract_json(response))
            self.inferred_legend = {
                int(k): str(v)
                for k, v in parsed.items()
                if str(k).lstrip("-").isdigit()
            }
            self._log(f"Inferred Legend: {self.inferred_legend}")
        except Exception as e:
            self._log(f"Could not parse inferred legend: {response} ERROR: {e}")

    def _load_state_from_file(self) -> None:
        if not os.path.exists(self.rules_file):
            return

        with open(self.rules_file, "r", encoding="utf-8") as file:
            content = file.read()

        import re

        self.known_rules = {}

        legend_match = re.search(r"legendes:\n({.*?})", content, re.DOTALL)
        if legend_match:
            try:
                parsed = json.loads(legend_match.group(1).strip())
                self.inferred_legend = {
                    int(k): str(v)
                    for k, v in parsed.items()
                    if str(k).lstrip("-").isdigit()
                }
            except json.JSONDecodeError:
                pass

        goal_match = re.search(r"final_goal:\n(.*?)\n\n", content, re.DOTALL)
        if goal_match:
            self.inferred_final_goal = goal_match.group(1).strip()

        for match in re.finditer(r'"([^"]+)":\s*\{\s*(.*?)\s*\}', content, re.DOTALL):
            category = match.group(1)
            rules_text = match.group(2)
            rules = [
                line.strip().rstrip(",")
                for line in rules_text.splitlines()
                if line.strip()
            ]
            if rules:
                self.known_rules[category] = rules

    def _save_rules(self, rules: dict[str, list[str]]) -> None:
        legend_str = (
            json.dumps(self.inferred_legend, indent=2) if self.inferred_legend else "{}"
        )
        with open(self.rules_file, "w", encoding="utf-8") as file:
            file.write("legendes:\n")
            file.write(f"{legend_str}\n\n")

            if self.inferred_final_goal:
                file.write("final_goal:\n")
                file.write(f"{self.inferred_final_goal}\n\n")

            for category, cat_rules in rules.items():
                if not cat_rules:
                    continue
                file.write(f'"{category}":{{\n')
                for i, rule in enumerate(cat_rules):
                    comma = "," if i < len(cat_rules) - 1 else ""
                    file.write(f"{rule}{comma}\n")
                file.write("}\n\n")

        self.known_rules = rules

    def deduce_rules_from_history(
        self,
        history: list[tuple[FrameData, GameAction, FrameData]],
        rule_focus: Optional[str] = None,
    ) -> bool:
        events = ""
        for i, (prev_frame, action, next_frame) in enumerate(history):
            events += (
                f"Event {i + 1}:\nAction: '{action.name}'\n"
                f"Board Before:\n{format_frames(prev_frame.frame)}\n"
                f"Board After:\n{format_frames(next_frame.frame)}\n"
            )

        known_rules_text = self._get_known_rules_text("KNOWN RULES:")
        focus_prompt = (
            f"Focus on deducing rules related to: {rule_focus}\n\n"
            if rule_focus
            else ""
        )

        sys_prompt, user_prompt = prompts.get_deduce_rules_prompt(
            events, known_rules_text, focus_prompt, game_name=self.cfg.game
        )
        response = self.llm_client._call(
            sys_prompt, user_prompt, model_type="pro", json_mode=True
        )

        try:
            data = json.loads(extract_json(response))
            new_rules_dict = data.get("rules", {})
            new_legend = data.get("legend", {})
            new_final_goal = data.get("final_goal", "")

            if not isinstance(new_rules_dict, dict):
                self._log(f"Invalid rules payload: {response}")
                return False

            state_changed = False

            if (
                new_final_goal
                and isinstance(new_final_goal, str)
                and new_final_goal != self.inferred_final_goal
            ):
                self.inferred_final_goal = new_final_goal
                state_changed = True

            if isinstance(new_legend, dict) and new_legend:
                for sym_str, role in new_legend.items():
                    if str(sym_str).lstrip("-").isdigit():
                        sym = int(sym_str)
                        if (
                            sym not in self.inferred_legend
                            or self.inferred_legend[sym] != role
                        ):
                            self.inferred_legend[sym] = role
                            state_changed = True

            added_any_rule = False
            for category, rules_list in new_rules_dict.items():
                if not isinstance(rules_list, list):
                    continue
                if category not in self.known_rules:
                    self.known_rules[category] = []
                for rule in rules_list:
                    if not isinstance(rule, str):
                        continue
                    cleaned_rule = rule.strip()
                    if not cleaned_rule:
                        continue

                    exists = any(
                        cleaned_rule in cat_rules
                        for cat_rules in self.known_rules.values()
                    )
                    if not exists:
                        if not added_any_rule:
                            self._log("--- New Rules Deduced ---")
                        self._log(f"- [{category}] {cleaned_rule}")
                        self.known_rules[category].append(cleaned_rule)
                        added_any_rule = True

            if added_any_rule or state_changed:
                self._save_rules(self.known_rules)
                if added_any_rule:
                    self._log("------------------------")
            return added_any_rule
        except json.JSONDecodeError:
            self._log(f"Could not parse rules from response: {response}")
            return False

    def compress_rules(self) -> bool:
        if not self.known_rules:
            return False

        known_rules_text = self._get_known_rules_text("KNOWN RULES TO COMPRESS:")
        sys_prompt, user_prompt = prompts.get_compress_rules_prompt(known_rules_text)
        response = self.llm_client._call(
            sys_prompt, user_prompt, model_type="pro", json_mode=True
        )

        try:
            data = json.loads(extract_json(response))
            compressed_rules = data.get("compressed_rules", {})
            if not isinstance(compressed_rules, dict) or not compressed_rules:
                self._log("No valid compressed rules returned.")
                return False

            final_rules: dict[str, list[str]] = {}
            for category, rules_list in compressed_rules.items():
                if not isinstance(rules_list, list):
                    continue
                cleaned = [
                    rule.strip()
                    for rule in rules_list
                    if isinstance(rule, str) and rule.strip()
                ]
                cleaned = self._unique_rules(cleaned)
                if cleaned:
                    final_rules[category] = cleaned

            if not final_rules:
                self._log("Compression produced no usable rules.")
                return False

            self._save_rules(final_rules)
            self._log("Rules compressed and saved.")
            return True
        except json.JSONDecodeError:
            self._log(f"Could not parse compressed rules from response: {response}")
            return False


@dataclass
class LearningTurnResult:
    prev_frame: FrameData
    action: GameAction
    next_frame: FrameData
    reached_terminal: bool


def choose_action_for_learning(
    cfg: Config,
    frame_data: FrameData,
    step_number: int,
) -> GameAction:
    available_actions = frame_data.available_actions or []
    if not available_actions:
        raise RuntimeError("No available actions returned by environment")

    non_reset_actions = [
        action for action in available_actions if action != GameAction.RESET
    ]
    candidates = non_reset_actions or available_actions
    return candidates[step_number % len(candidates)]


def run_learning_turn(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    current_frame: FrameData,
    step_number: int,
) -> LearningTurnResult:
    action = choose_action_for_learning(cfg, current_frame, step_number)
    next_frame = env.step(action)
    agent.history.append((current_frame, action, next_frame))
    reached_terminal = next_frame.state in {GameState.WIN, GameState.GAME_OVER}
    return LearningTurnResult(
        prev_frame=current_frame,
        action=action,
        next_frame=next_frame,
        reached_terminal=reached_terminal,
    )


def run_learning_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    def log(message: str) -> None:
        if event_sink is not None:
            event_sink(message)
            return
        print(message)

    current_frame = env.reset()
    for step in range(cfg.max_steps):
        turn = run_learning_turn(cfg, env, agent, current_frame, step)
        current_frame = turn.next_frame

        if (step + 1) % 10 == 0:
            log(f"Step {step + 1}: inferring legend from recent history")
            agent.infer_legend(agent.history[-10:])
            log(f"Step {step + 1}: deducing rules from recent history")
            agent.deduce_rules_from_history(agent.history[-10:])

        if turn.reached_terminal:
            log(f"Reached terminal state: {turn.next_frame.state.name}. Resetting.")
            current_frame = env.reset()

    agent.compress_rules()


def load_rules_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def request_solution_plan(
    agent: Agent,
    rules_text: str,
    current_frame: FrameData,
) -> str:
    prompt = (
        f"KNOWN RULES:\n{rules_text}\n\n"
        f"CURRENT BOARD:\n{format_frames(current_frame.frame)}\n\n"
        "Using the known rules only, provide a short action plan using W/A/S/D."
    )
    return agent.llm_client._call(
        "You solve grid worlds using provided rules.",
        prompt,
        model_type="pro",
    )


def parse_solution_actions(plan_text: str) -> list[GameAction]:
    mapping = {
        "W": GameAction.ACTION1,
        "S": GameAction.ACTION2,
        "A": GameAction.ACTION3,
        "D": GameAction.ACTION4,
    }
    actions: list[GameAction] = []
    for char in plan_text.upper():
        if char in mapping:
            actions.append(mapping[char])
    return actions


def run_solving_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    def log(message: str) -> None:
        if event_sink is not None:
            event_sink(message)
            return
        print(message)

    current_frame = env.reset()
    if not os.path.exists(agent.rules_file):
        raise FileNotFoundError(f"Rules file not found: {agent.rules_file}")

    rules_text = load_rules_text(agent.rules_file)
    plan_text = request_solution_plan(agent, rules_text, current_frame)
    actions = parse_solution_actions(plan_text)

    if not actions:
        raise RuntimeError("Solver returned no executable actions")

    for action in actions[: cfg.max_steps]:
        log(f"Executing planned action: {action.name}")
        current_frame = env.step(action)
        if current_frame.state == GameState.WIN:
            log("Puzzle solved.")
            return
        if current_frame.state == GameState.GAME_OVER:
            log("Game over encountered during solve.")
            return

    log("Stopped after max solve steps.")
