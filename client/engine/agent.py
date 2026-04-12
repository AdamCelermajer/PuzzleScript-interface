import json
import os
import re
import time
from typing import Callable, Optional

from client.engine import prompts
from client.engine.base_env import BaseEnv
from client.engine.llm_client import Config, LlmClient
from client.engine.types import FrameData, GameAction, GameState
from client.engine.utils import extract_json, format_frames


HistoryEntry = tuple[FrameData, GameAction, FrameData]


def _emit(message: str, event_sink: Optional[Callable[[str], None]] = None) -> None:
    (event_sink or print)(message)


def _parse_legend(data: object) -> dict[int, str]:
    return (
        {}
        if not isinstance(data, dict)
        else {int(k): str(v) for k, v in data.items() if str(k).lstrip("-").isdigit()}
    )


def _clean_rules(
    rules_by_category: object, *, unique: bool = False
) -> dict[str, list[str]]:
    if not isinstance(rules_by_category, dict):
        return {}
    return {
        category: list(dict.fromkeys(cleaned)) if unique else cleaned
        for category, rules in rules_by_category.items()
        if isinstance(rules, list)
        and (
            cleaned := [
                rule.strip() for rule in rules if isinstance(rule, str) and rule.strip()
            ]
        )
    }


def _format_history(
    history: list[HistoryEntry],
    *,
    label: str,
    before: str,
    after: str,
    quoted_action: bool = False,
) -> str:
    return "\n\n".join(
        f"{label} {i}:\nAction: {repr(action.name) if quoted_action else action.name}\n"
        f"{before}:\n{format_frames(prev_frame.frame)}\n{after}:\n{format_frames(next_frame.frame)}"
        for i, (prev_frame, action, next_frame) in enumerate(history, start=1)
    )


def _remember(history: list[HistoryEntry], entry: HistoryEntry) -> None:
    history.append(entry)
    del history[:-200]


def _set_dashboard(
    dashboard, *, status: str | None = None, detail: str | None = None
) -> None:
    if dashboard is None:
        return
    if status is not None:
        dashboard.set_status(status)
    if detail is not None:
        dashboard.set_detail(detail)


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
        self.history: list[HistoryEntry] = []
        self.inferred_legend: dict[int, str] = {}
        self.inferred_final_goal: str = ""

        os.makedirs(self.cfg.rules_dir, exist_ok=True)
        self.rules_file = os.path.join(self.cfg.rules_dir, f"{self.cfg.game}_rules.txt")
        self.known_rules: dict[str, list[str]] = {}
        self._load_state_from_file()

    def _log(self, message: str) -> None:
        _emit(message, self.event_sink)

    def _call_json(
        self, sys_prompt: str, user_prompt: str, *, model_type: str = "pro"
    ) -> tuple[str, object | None]:
        response = self.llm_client._call(
            sys_prompt, user_prompt, model_type=model_type, json_mode=True
        )
        try:
            return response, json.loads(extract_json(response))
        except json.JSONDecodeError:
            return response, None

    def _get_known_rules_text(self, prefix: str = "KNOWN RULES:") -> str:
        if not self.known_rules:
            return ""
        return "\n\n".join(
            [prefix]
            + [
                f'"{category}":{{\n' + ",\n".join(rules) + "\n}"
                for category, rules in self.known_rules.items()
            ]
        )

    def infer_legend(self, history: list[HistoryEntry]) -> None:
        history_log = _format_history(
            history, label="Step", before="Before", after="After"
        )
        current_legend_text = (
            f"CURRENT KNOWN LEGEND:\n{json.dumps(self.inferred_legend)}"
            if self.inferred_legend
            else "CURRENT KNOWN LEGEND: none yet"
        )
        sys_prompt, user_prompt = prompts.get_infer_legend_prompt(
            history_log, current_legend_text, game_name=self.cfg.game
        )
        response, data = self._call_json(sys_prompt, user_prompt)
        if not isinstance(data, dict):
            self._log(
                f"Could not parse inferred legend: {response} ERROR: Legend payload must be a JSON object"
            )
            return
        self.inferred_legend = _parse_legend(data)
        self._log(f"Inferred Legend: {self.inferred_legend}")

    def _load_state_from_file(self) -> None:
        if not os.path.exists(self.rules_file):
            return

        with open(self.rules_file, "r", encoding="utf-8") as file:
            content = file.read()

        if legend_match := re.search(r"legendes:\n({.*?})", content, re.DOTALL):
            try:
                self.inferred_legend = _parse_legend(
                    json.loads(legend_match.group(1).strip())
                )
            except json.JSONDecodeError:
                pass
        if goal_match := re.search(r"final_goal:\n(.*?)\n\n", content, re.DOTALL):
            self.inferred_final_goal = goal_match.group(1).strip()
        self.known_rules = {
            match.group(1): rules
            for match in re.finditer(
                r'"([^"]+)":\s*\{\s*(.*?)\s*\}', content, re.DOTALL
            )
            if (
                rules := [
                    line.strip().rstrip(",")
                    for line in match.group(2).splitlines()
                    if line.strip()
                ]
            )
        }

    def _save_rules(self, rules: dict[str, list[str]]) -> None:
        parts = [
            "legendes:\n",
            f"{json.dumps(self.inferred_legend, indent=2) if self.inferred_legend else '{}'}\n\n",
        ]
        if self.inferred_final_goal:
            parts.append(f"final_goal:\n{self.inferred_final_goal}\n\n")
        parts.extend(
            f'"{category}":{{\n' + ",\n".join(cat_rules) + "\n}\n\n"
            for category, cat_rules in rules.items()
            if cat_rules
        )
        with open(self.rules_file, "w", encoding="utf-8") as file:
            file.write("".join(parts))
        self.known_rules = rules

    def deduce_rules_from_history(
        self, history: list[HistoryEntry], rule_focus: Optional[str] = None
    ) -> bool:
        events = _format_history(
            history,
            label="Event",
            before="Board Before",
            after="Board After",
            quoted_action=True,
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
        response, data = self._call_json(sys_prompt, user_prompt)
        if data is None:
            self._log(f"Could not parse rules from response: {response}")
            return False

        new_rules_dict = data.get("rules", {})
        if not isinstance(new_rules_dict, dict):
            self._log(f"Invalid rules payload: {response}")
            return False

        new_final_goal = data.get("final_goal", "")
        state_changed = False
        if (
            new_final_goal
            and isinstance(new_final_goal, str)
            and new_final_goal != self.inferred_final_goal
        ):
            self.inferred_final_goal = new_final_goal
            state_changed = True
        for sym, role in _parse_legend(data.get("legend", {})).items():
            if self.inferred_legend.get(sym) != role:
                self.inferred_legend[sym] = role
                state_changed = True

        added_any_rule = False
        existing_rules = {rule for rules in self.known_rules.values() for rule in rules}
        for category, rules in _clean_rules(new_rules_dict).items():
            for rule in rules:
                if rule in existing_rules:
                    continue
                if not added_any_rule:
                    self._log("--- New Rules Deduced ---")
                self._log(f"- [{category}] {rule}")
                self.known_rules.setdefault(category, []).append(rule)
                existing_rules.add(rule)
                added_any_rule = True

        if added_any_rule or state_changed:
            self._save_rules(self.known_rules)
            if added_any_rule:
                self._log("------------------------")
        return added_any_rule

    def compress_rules(self) -> bool:
        if not self.known_rules:
            return False

        known_rules_text = self._get_known_rules_text("KNOWN RULES TO COMPRESS:")
        sys_prompt, user_prompt = prompts.get_compress_rules_prompt(known_rules_text)
        response, data = self._call_json(sys_prompt, user_prompt)
        if data is None:
            self._log(f"Could not parse compressed rules from response: {response}")
            return False

        compressed_rules = data.get("compressed_rules", {})
        if not isinstance(compressed_rules, dict) or not compressed_rules:
            self._log("No valid compressed rules returned.")
            return False
        final_rules = _clean_rules(compressed_rules, unique=True)
        if not final_rules:
            self._log("Compression produced no usable rules.")
            return False

        self._save_rules(final_rules)
        self._log("Rules compressed and saved.")
        return True

    def refine_and_complete_rules_and_legend(self) -> None:
        history_log = _format_history(
            self.history,
            label="Step",
            before="Board state before action",
            after="Board state after action",
        )
        known_rules_text = self._get_known_rules_text("Rules deduced so far:")
        sys_prompt, user_prompt = prompts.get_refine_rules_prompt(
            known_rules_text, history_log, game_name=self.cfg.game
        )
        response, data = self._call_json(sys_prompt, user_prompt)
        if data is None:
            print(f"Could not parse final deduction response: {response}")
            return

        final_rules = data.get("final_rules", {})
        new_legend = data.get("legend", {})
        self.inferred_final_goal = data.get("final_goal", self.inferred_final_goal)
        if isinstance(new_legend, dict):
            self.inferred_legend = _parse_legend(new_legend)
        self.known_rules = _clean_rules(final_rules)
        if not self.known_rules:
            print("Could not deduce final rules.")
            return

        print("\n--- Final Rules and Legend ---")
        print("Legend:", self.inferred_legend)
        if self.inferred_final_goal:
            print("Final Goal:", self.inferred_final_goal)
        for category, rules in self.known_rules.items():
            print(f'"{category}":')
            for rule in rules:
                print(f"  {rule}")
        self._save_rules(self.known_rules)
        print("-----------------------------")

    def _parse_action(self, text: str) -> GameAction:
        text = text.strip().upper()
        if action := next(
            (action for action in GameAction if action.name in text), None
        ):
            return action
        if len(text) == 1 and (
            action := {
                "W": GameAction.ACTION1,
                "S": GameAction.ACTION2,
                "A": GameAction.ACTION3,
                "D": GameAction.ACTION4,
                "X": GameAction.ACTION5,
                "R": GameAction.RESET,
            }.get(text)
        ):
            return action
        self._log(
            f"Warning: could not parse action from '{text}', defaulting to ACTION5"
        )
        return GameAction.ACTION5

    def _clean_subgoal(self, text: str) -> str:
        source = text.strip()
        lower_source = source.lower()
        marker = max(("**subgoal:**", "subgoal:"), key=lower_source.rfind)
        if (start := lower_source.rfind(marker)) != -1:
            source = source[start + len(marker) :]
        source = source.translate(str.maketrans("", "", "*#_"))
        return next(
            (line.strip() for line in source.splitlines() if line.strip()),
            source.strip() or "Explore a new interaction.",
        )

    def plan_subgoal(self, frame_data: FrameData, history: list[HistoryEntry]) -> str:
        recent = "\n".join(
            f"{i + 1}. {action.name}" for i, (_, action, _) in enumerate(history[-5:])
        )
        sys_prompt, user_prompt = prompts.get_plan_subgoal_prompt(
            format_frames(frame_data.frame),
            recent,
            [rule for rules in self.known_rules.values() for rule in rules],
            {**frame_data.legend, **self.inferred_legend},
        )
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="flash")
        return self._clean_subgoal(response)

    def act_learn(
        self, frame_data: FrameData, local: list[HistoryEntry], subgoal: str = ""
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
            if self.deduce_rules_from_history(history_window):
                self._log("Compressing rules...")
                self.compress_rules()
        else:
            self._log("All recent steps unchanged - skipping deduction")
        self._log("Planning next subgoal...")
        new_subgoal = self.plan_subgoal(frame_data, self.history)
        self._log(f"New subgoal: {new_subgoal}")
        return new_subgoal


def _choose_placeholder_action(frame_data: FrameData, step_number: int) -> GameAction:
    actions = [
        action
        for action in frame_data.available_actions or []
        if action != GameAction.RESET
    ]
    if not actions:
        raise RuntimeError("No non-reset actions available for solve placeholder")
    return actions[step_number % len(actions)]


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

    steps = unchanged = last_periodic_step = 0
    local: list[HistoryEntry] = []
    subgoal = ""
    legend_inferred = False
    _emit(
        f"Started session {getattr(env, 'session_id', 'unknown')} in LEARN mode",
        event_sink,
    )
    _emit(f"Legend mapping from env: {frame_data.legend}", event_sink)
    _set_dashboard(
        dashboard,
        status="Learning rules from live board transitions.",
        detail="Waiting for the next action.",
    )

    while True:
        if steps >= cfg.max_steps:
            _emit("Max steps reached. Performing final analysis...", event_sink)
            if dashboard is not None:
                dashboard.close()
                agent.event_sink = agent.llm_client.event_sink = None
            agent.refine_and_complete_rules_and_legend()
            return

        if steps and steps % 5 == 0 and steps != last_periodic_step:
            try:
                subgoal = agent.run_periodic_analysis(frame_data)
                _set_dashboard(dashboard, detail=f"Subgoal: {subgoal}")
            except RuntimeError as e:
                _emit(f"LLM failure during analysis, skipping: {e}", event_sink)
            last_periodic_step = steps

        try:
            action = agent.act_learn(frame_data, local, subgoal)
        except RuntimeError as e:
            _emit(f"LLM failure, skipping turn: {e}", event_sink)
            time.sleep(2)
            continue
        _emit(f"Action: {action.name}", event_sink)

        prev_frame, next_frame = frame_data, env.step(action)
        frame_data = next_frame
        entry = (prev_frame, action, next_frame)
        _remember(agent.history, entry)
        local.append(entry)

        if prev_frame.frame == next_frame.frame:
            _emit("Warning: Board state unchanged", event_sink)
            unchanged += 1
            if unchanged >= 3:
                _emit("Stuck - forcing reset", event_sink)
                frame_data = env.reset()
                local.clear()
                subgoal = ""
                unchanged = 0
                _set_dashboard(
                    dashboard, detail="Board reset after repeated unchanged moves."
                )
            time.sleep(1)
            continue

        unchanged = 0
        steps += 1
        if not legend_inferred and steps >= 10 and len(agent.history) >= 10:
            _emit("Inferring symbol roles from first 10 steps...", event_sink)
            agent.infer_legend(agent.history[:10])
            legend_inferred = True

        if (
            next_frame.state in {GameState.WIN, GameState.GAME_OVER}
            or next_frame.levels_completed != prev_frame.levels_completed
        ):
            _emit("Level complete!", event_sink)
            local.clear()
            subgoal = ""
            if cfg.mode == "win" and next_frame.state == GameState.WIN:
                _emit("World completed successfully!", event_sink)
                return
            if next_frame.state == GameState.GAME_OVER:
                _emit("Game Over... Resetting", event_sink)
                frame_data = env.reset()
                _set_dashboard(dashboard, detail="Board reset after GAME_OVER.")

        time.sleep(1)


def run_solving_loop(
    cfg: Config,
    env: BaseEnv,
    agent: Agent,
    dashboard=None,
    event_sink: Optional[Callable[[str], None]] = None,
) -> None:
    frame_data = env.reset()
    steps = 0
    _emit(
        f"Started session {getattr(env, 'session_id', 'unknown')} in SOLVE mode",
        event_sink,
    )
    _set_dashboard(
        dashboard,
        status="Running simple solve placeholder.",
        detail="Using non-reset moves only.",
    )

    while steps < cfg.max_steps:
        action = _choose_placeholder_action(frame_data, steps)
        _emit(f"Action: {action.name}", event_sink)

        next_frame = env.step(action)
        _remember(agent.history, (frame_data, action, next_frame))
        steps += 1
        frame_data = next_frame

        if next_frame.state == GameState.WIN:
            _emit("Game completed successfully!", event_sink)
            return
        if next_frame.state == GameState.GAME_OVER:
            _emit("Game Over encountered during solve.", event_sink)
            return
        time.sleep(1)

    _emit("Stopped after max solve steps.", event_sink)
