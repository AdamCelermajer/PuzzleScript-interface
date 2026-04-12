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

    def refine_and_complete_rules_and_legend(self) -> None:
        history_log = "\n\n".join(
            (
                f"Step {i + 1}:\nAction: {action.name}\nBoard state before action:\n{format_frames(prev_frame.frame)}\n"
                f"Board state after action:\n{format_frames(next_frame.frame)}"
            )
            for i, (prev_frame, action, next_frame) in enumerate(self.history)
        )
        known_rules_text = self._get_known_rules_text("Rules deduced so far:")
        sys_prompt, user_prompt = prompts.get_refine_rules_prompt(
            known_rules_text, history_log, game_name=self.cfg.game
        )
        response = self.llm_client._call(
            sys_prompt, user_prompt, model_type="pro", json_mode=True
        )

        try:
            data = json.loads(extract_json(response))
            final_rules = data.get("final_rules", {})
            new_legend = data.get("legend", {})
            self.inferred_final_goal = data.get("final_goal", self.inferred_final_goal)

            if isinstance(new_legend, dict):
                self.inferred_legend = {
                    int(k): str(v)
                    for k, v in new_legend.items()
                    if str(k).lstrip("-").isdigit()
                }

            if final_rules and isinstance(final_rules, dict):
                print("\n--- Final Rules and Legend ---")
                print("Legend:", self.inferred_legend)
                if self.inferred_final_goal:
                    print("Final Goal:", self.inferred_final_goal)

                self.known_rules = {}
                for category, rules in final_rules.items():
                    if isinstance(rules, list):
                        valid_rules = [
                            r for r in rules if isinstance(r, str) and r.strip()
                        ]
                        if valid_rules:
                            self.known_rules[category] = valid_rules

                for category, rules in self.known_rules.items():
                    print(f'"{category}":')
                    for rule in rules:
                        print(f"  {rule}")

                self._save_rules(self.known_rules)
                print("-----------------------------")
            else:
                print("Could not deduce final rules.")
        except json.JSONDecodeError:
            print(f"Could not parse final deduction response: {response}")

    def _parse_action(self, text: str) -> GameAction:
        text = text.strip().upper()

        for action in GameAction:
            if action.name in text:
                return action

        if len(text) == 1:
            shorthand = {
                "W": GameAction.ACTION1,
                "S": GameAction.ACTION2,
                "A": GameAction.ACTION3,
                "D": GameAction.ACTION4,
                "X": GameAction.ACTION5,
                "R": GameAction.RESET,
            }
            if text in shorthand:
                return shorthand[text]

        self._log(
            f"Warning: could not parse action from '{text}', defaulting to ACTION5"
        )
        return GameAction.ACTION5

    def _clean_subgoal(self, text: str) -> str:
        source = text.strip()
        lower_source = source.lower()
        markers = ["**subgoal:**", "subgoal:"]

        start_index = -1
        marker_length = 0
        for marker in markers:
            idx = lower_source.rfind(marker)
            if idx > start_index:
                start_index = idx
                marker_length = len(marker)

        if start_index != -1:
            source = source[start_index + marker_length :]
        for symbol in ("*", "#", "_"):
            source = source.replace(symbol, "")

        for line in source.splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned
        fallback = source.strip()
        return fallback if fallback else "Explore a new interaction."

    def plan_subgoal(
        self,
        frame_data: FrameData,
        history: list[tuple[FrameData, GameAction, FrameData]],
    ) -> str:
        recent = "\n".join(
            f"{i + 1}. {action.name}" for i, (_, action, _) in enumerate(history[-5:])
        )
        flat_rules = []
        for cat_rules in self.known_rules.values():
            flat_rules.extend(cat_rules)

        merged_legend = frame_data.legend.copy()
        if self.inferred_legend:
            merged_legend.update(self.inferred_legend)

        sys_prompt, user_prompt = prompts.get_plan_subgoal_prompt(
            format_frames(frame_data.frame),
            recent,
            flat_rules,
            merged_legend,
        )
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="flash")
        return self._clean_subgoal(response)

    def act_learn(
        self,
        frame_data: FrameData,
        local: list[tuple[FrameData, GameAction, FrameData]],
        subgoal: str = "",
    ) -> GameAction:
        hist = "\n".join(
            f"- {action.name} (Board unchanged: {prev_frame.frame == next_frame.frame})"
            for prev_frame, action, next_frame in local[-5:]
        )
        known_rules_text = self._get_known_rules_text("KNOWN RULES:")

        sys_prompt, user_prompt = prompts.get_learning_act_prompt(
            subgoal,
            format_frames(frame_data.frame),
            known_rules_text,
            hist,
        )
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="flash")
        return self._parse_action(response)

    def run_periodic_analysis(self, frame_data: FrameData) -> str:
        history_window = self.history[-5:]
        if history_window and any(
            prev.frame != next_frame.frame for prev, _, next_frame in history_window
        ):
            self._log("Deducing rules from history...")
            added_any = self.deduce_rules_from_history(history_window)
            if added_any:
                self._log("Compressing rules...")
                self.compress_rules()
        else:
            self._log("All recent steps unchanged - skipping deduction")

        self._log("Planning next subgoal...")
        new_subgoal = self.plan_subgoal(frame_data, self.history)
        self._log(f"New subgoal: {new_subgoal}")
        return new_subgoal


@dataclass
class RunState:
    frame_data: FrameData
    steps: int = 0
    local: list[tuple[FrameData, GameAction, FrameData]] = field(default_factory=list)


def _emit(message: str, event_sink: Optional[Callable[[str], None]] = None) -> None:
    if event_sink is not None:
        event_sink(message)
        return
    print(message)


def _choose_placeholder_action(frame_data: FrameData, step_number: int) -> GameAction:
    available_actions = frame_data.available_actions or []
    non_reset_actions = [
        action for action in available_actions if action != GameAction.RESET
    ]
    if not non_reset_actions:
        raise RuntimeError("No non-reset actions available for solve placeholder")
    return non_reset_actions[step_number % len(non_reset_actions)]


def run_learning_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    try:
        frame_data = env.reset()
    except Exception as e:
        _emit(f"Failed to initialize environment: {e}", event_sink)
        return

    state = RunState(frame_data=frame_data)
    _emit(
        f"Started session {getattr(env, 'session_id', 'unknown')} in LEARN mode",
        event_sink,
    )
    _emit(f"Legend mapping from env: {frame_data.legend}", event_sink)
    if dashboard is not None:
        dashboard.set_status("Learning rules from live board transitions.")
        dashboard.set_detail("Waiting for the next action.")

    subgoal = ""
    consecutive_unchanged = 0
    legend_inferred = False
    last_periodic_step = 0

    while True:
        if state.steps >= cfg.max_steps:
            _emit("Max steps reached. Performing final analysis...", event_sink)
            if dashboard is not None:
                dashboard.close()
                agent.event_sink = None
                agent.llm_client.event_sink = None
            agent.refine_and_complete_rules_and_legend()
            break

        if (
            state.steps > 0
            and state.steps % 5 == 0
            and state.steps != last_periodic_step
        ):
            try:
                subgoal = agent.run_periodic_analysis(state.frame_data)
                if dashboard is not None:
                    dashboard.set_detail(f"Subgoal: {subgoal}")
            except RuntimeError as e:
                _emit(f"LLM failure during analysis, skipping: {e}", event_sink)
            last_periodic_step = state.steps

        try:
            action = agent.act_learn(state.frame_data, state.local, subgoal)
        except RuntimeError as e:
            _emit(f"LLM failure, skipping turn: {e}", event_sink)
            time.sleep(2)
            continue
        _emit(f"Action: {action.name}", event_sink)

        prev_frame = state.frame_data
        next_frame = env.step(action)

        agent.history.append((prev_frame, action, next_frame))
        if len(agent.history) > 200:
            agent.history = agent.history[-200:]

        state.local.append((prev_frame, action, next_frame))
        state.frame_data = next_frame

        if prev_frame.frame == next_frame.frame:
            _emit("Warning: Board state unchanged", event_sink)
            consecutive_unchanged += 1
            if consecutive_unchanged >= 3:
                _emit("Stuck - forcing reset", event_sink)
                state.frame_data = env.reset()
                state.local = []
                subgoal = ""
                consecutive_unchanged = 0
                if dashboard is not None:
                    dashboard.set_detail("Board reset after repeated unchanged moves.")
            time.sleep(1)
            continue

        consecutive_unchanged = 0
        state.steps += 1

        if not legend_inferred and state.steps >= 10 and len(agent.history) >= 10:
            _emit("Inferring symbol roles from first 10 steps...", event_sink)
            agent.infer_legend(agent.history[:10])
            legend_inferred = True

        if (
            next_frame.state in [GameState.WIN, GameState.GAME_OVER]
            or next_frame.levels_completed != prev_frame.levels_completed
        ):
            _emit("Level complete!", event_sink)
            state.local = []
            subgoal = ""
            if cfg.mode == "win" and next_frame.state == GameState.WIN:
                _emit("World completed successfully!", event_sink)
                break
            if next_frame.state == GameState.GAME_OVER:
                _emit("Game Over... Resetting", event_sink)
                state.frame_data = env.reset()
                if dashboard is not None:
                    dashboard.set_detail("Board reset after GAME_OVER.")

        time.sleep(1)


def run_solving_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    frame_data = env.reset()
    state = RunState(frame_data=frame_data)

    _emit(
        f"Started session {getattr(env, 'session_id', 'unknown')} in SOLVE mode",
        event_sink,
    )
    if dashboard is not None:
        dashboard.set_status("Running simple solve placeholder.")
        dashboard.set_detail("Using non-reset moves only.")

    while state.steps < cfg.max_steps:
        action = _choose_placeholder_action(state.frame_data, state.steps)
        _emit(f"Action: {action.name}", event_sink)

        next_frame = env.step(action)
        agent.history.append((state.frame_data, action, next_frame))
        if len(agent.history) > 200:
            agent.history = agent.history[-200:]

        state.local.append((state.frame_data, action, next_frame))
        state.steps += 1
        state.frame_data = next_frame

        if next_frame.state == GameState.WIN:
            _emit("Game completed successfully!", event_sink)
            return

        if next_frame.state == GameState.GAME_OVER:
            _emit("Game Over encountered during solve.", event_sink)
            return

        time.sleep(1)

    _emit("Stopped after max solve steps.", event_sink)
