import json
import os
import time
from typing import Optional
from dataclasses import dataclass, field

from .llm_client import Config, LlmClient
from .types import GameAction, GameState, FrameData
from . import prompts
from .utils import format_frames, extract_json
from envs.base_env import BaseEnv


class Agent:
    """LLM-driven agent capable of both learning rules and solving environments."""

    def __init__(self, config: Config, llm_client: LlmClient) -> None:
        """Initialize learner state, rule storage, and inference memory."""
        self.cfg = config
        self.llm_client = llm_client
        self.history: list[tuple[FrameData, GameAction, FrameData]] = []
        self.inferred_legend: dict[int, str] = {}
        self.inferred_final_goal: str = ""

        os.makedirs(self.cfg.rules_dir, exist_ok=True)
        self.rules_file = os.path.join(self.cfg.rules_dir, f"{self.cfg.game}_rules.txt")
        self.known_rules: dict[str, list[str]] = {}
        self._load_state_from_file()

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

    def infer_legend(self, history: list[tuple[FrameData, GameAction, FrameData]]) -> None:
        history_log = "\n\n".join(
            (
                f"Step {i + 1}:\nAction: {action.name}\nBefore:\n{format_frames(prev_frame.frame)}\n"
                f"After:\n{format_frames(next_frame.frame)}"
            )
            for i, (prev_frame, action, next_frame) in enumerate(history)
        )
        current_legend_text = f"CURRENT KNOWN LEGEND:\n{json.dumps(self.inferred_legend)}" if self.inferred_legend else "CURRENT KNOWN LEGEND: none yet"
        sys_prompt, user_prompt = prompts.get_infer_legend_prompt(history_log, current_legend_text, game_name=self.cfg.game)
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="pro", json_mode=True)

        try:
            parsed = json.loads(extract_json(response))
            self.inferred_legend = {int(k): str(v) for k, v in parsed.items() if str(k).lstrip('-').isdigit()}
            print(f"Inferred Legend: {self.inferred_legend}")
        except Exception as e:
            print(f"Could not parse inferred legend: {response} ERROR: {e}")

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
                self.inferred_legend = {int(k): str(v) for k, v in parsed.items() if str(k).lstrip('-').isdigit()}
            except json.JSONDecodeError:
                pass

        goal_match = re.search(r"final_goal:\n(.*?)\n\n", content, re.DOTALL)
        if goal_match:
            self.inferred_final_goal = goal_match.group(1).strip()

        for match in re.finditer(r'"([^"]+)":\s*\{\s*(.*?)\s*\}', content, re.DOTALL):
            category = match.group(1)
            rules_text = match.group(2)
            rules = [line.strip().rstrip(",") for line in rules_text.splitlines() if line.strip()]
            if rules:
                self.known_rules[category] = rules

    def _save_rules(self, rules: dict[str, list[str]]) -> None:
        legend_str = json.dumps(self.inferred_legend, indent=2) if self.inferred_legend else "{}"
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
        focus_prompt = f"Focus on deducing rules related to: {rule_focus}\n\n" if rule_focus else ""

        sys_prompt, user_prompt = prompts.get_deduce_rules_prompt(events, known_rules_text, focus_prompt, game_name=self.cfg.game)
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="pro", json_mode=True)

        try:
            data = json.loads(extract_json(response))
            new_rules_dict = data.get("rules", {})
            new_legend = data.get("legend", {})
            new_final_goal = data.get("final_goal", "")

            if not isinstance(new_rules_dict, dict):
                print(f"Invalid rules payload: {response}")
                return False

            state_changed = False

            if new_final_goal and isinstance(new_final_goal, str) and new_final_goal != self.inferred_final_goal:
                self.inferred_final_goal = new_final_goal
                state_changed = True

            if isinstance(new_legend, dict) and new_legend:
                for sym_str, role in new_legend.items():
                    if str(sym_str).lstrip('-').isdigit():
                        sym = int(sym_str)
                        if sym not in self.inferred_legend or self.inferred_legend[sym] != role:
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
                        
                    exists = any(cleaned_rule in cat_rules for cat_rules in self.known_rules.values())
                    if not exists:
                        if not added_any_rule: print("--- New Rules Deduced ---")
                        print(f'- [{category}] {cleaned_rule}')
                        self.known_rules[category].append(cleaned_rule)
                        added_any_rule = True

            if added_any_rule or state_changed:
                self._save_rules(self.known_rules)
                if added_any_rule: print("------------------------")
            return added_any_rule
        except json.JSONDecodeError:
            print(f"Could not parse rules from response: {response}")
            return False

    def compress_rules(self) -> bool:
        if not self.known_rules: return False
        known_rules_text = self._get_known_rules_text("KNOWN RULES:")
        sys_prompt, user_prompt = prompts.get_compress_rules_prompt(known_rules_text)
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="pro", json_mode=True)

        try:
            data = json.loads(extract_json(response))
            compressed_dict = data.get("compressed_rules", {})
            if not isinstance(compressed_dict, dict): return False

            cleaned_compressed = {}
            for category, rules in compressed_dict.items():
                if isinstance(rules, list):
                    unique_rules = self._unique_rules([r.strip() for r in rules if isinstance(r, str) and r.strip()])
                    if unique_rules: cleaned_compressed[category] = unique_rules

            if cleaned_compressed and cleaned_compressed != self.known_rules:
                print("Applied compressed rule set.")
                self.known_rules = cleaned_compressed
                self._save_rules(self.known_rules)
                return True
            return False
        except json.JSONDecodeError:
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
        sys_prompt, user_prompt = prompts.get_refine_rules_prompt(known_rules_text, history_log, game_name=self.cfg.game)
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="pro", json_mode=True)

        try:
            data = json.loads(extract_json(response))
            final_rules = data.get("final_rules", {})
            new_legend = data.get("legend", {})
            self.inferred_final_goal = data.get("final_goal", self.inferred_final_goal)

            if isinstance(new_legend, dict):
                self.inferred_legend = {int(k): str(v) for k, v in new_legend.items() if str(k).lstrip('-').isdigit()}

            if final_rules and isinstance(final_rules, dict):
                print("\n--- Final Rules and Legend ---")
                print("Legend:", self.inferred_legend)
                if self.inferred_final_goal: print("Final Goal:", self.inferred_final_goal)
                
                self.known_rules = {}
                for category, rules in final_rules.items():
                    if isinstance(rules, list):
                        valid_rules = [r for r in rules if isinstance(r, str) and r.strip()]
                        if valid_rules: self.known_rules[category] = valid_rules
                
                for category, rules in self.known_rules.items():
                    print(f'"{category}":')
                    for r in rules: print(f"  {r}")
                        
                self._save_rules(self.known_rules)
                print("-----------------------------")
            else:
                print("Could not deduce final rules.")
        except json.JSONDecodeError:
            print(f"Could not parse final deduction response: {response}")

    def _parse_action(self, text: str) -> GameAction:
        text = text.strip().upper()

        # Exact action name match (handles multi-word LLM output like "I choose ACTION1")
        for action in GameAction:
            if action.name in text:
                return action

        # Single-character shorthand — only if the entire response is one char
        if len(text) == 1:
            shorthand = {"W": GameAction.ACTION1, "S": GameAction.ACTION2,
                         "A": GameAction.ACTION3, "D": GameAction.ACTION4,
                         "X": GameAction.ACTION5, "R": GameAction.RESET}
            if text in shorthand:
                return shorthand[text]

        print(f"Warning: could not parse action from '{text}', defaulting to ACTION5")
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

        if start_index != -1: source = source[start_index + marker_length :]
        for symbol in ("*", "#", "_"): source = source.replace(symbol, "")

        for line in source.splitlines():
            cleaned = line.strip()
            if cleaned: return cleaned
        fallback = source.strip()
        return fallback if fallback else "Explore a new interaction."

    def plan_subgoal(self, frame_data: FrameData, history: list[tuple[FrameData, GameAction, FrameData]]) -> str:
        recent = "\n".join(f"{i + 1}. {action.name}" for i, (_, action, _) in enumerate(history[-5:]))
        flat_rules = []
        for cat_rules in self.known_rules.values(): flat_rules.extend(cat_rules)

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

    def act_learn(self, frame_data: FrameData, local: list[tuple[FrameData, GameAction, FrameData]], subgoal: str = "") -> GameAction:
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

    def act_solve(self, frame_data: FrameData, legend: dict, local: list) -> GameAction:
        flat_rules = []
        for cat_rules in self.known_rules.values(): flat_rules.extend(cat_rules)

        sys_prompt, user_prompt = prompts.get_solving_act_prompt(
            format_frames(frame_data.frame), 
            legend, 
            flat_rules, 
            self.cfg.show_legend
        )
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="flash")
        return self._parse_action(response)

    def run_periodic_analysis(self, frame_data: FrameData) -> str:
        history_window = self.history[-5:]
        if history_window and any(prev.frame != next_f.frame for prev, _, next_f in history_window):
            print("Deducing rules from history...")
            added_any = self.deduce_rules_from_history(history_window)
            if added_any:
                print("Compressing rules...")
                self.compress_rules()
        else:
            print("All recent steps unchanged — skipping deduction")

        print("Planning next subgoal...")
        new_subgoal = self.plan_subgoal(frame_data, self.history)
        print(f"New subgoal: {new_subgoal}")
        return new_subgoal


@dataclass
class RunState:
    frame_data: FrameData
    steps: int = 0
    local: list[tuple[FrameData, GameAction, FrameData]] = field(default_factory=list)


def run_learning_loop(cfg: Config, env: BaseEnv, agent: Agent) -> None:
    try:
        frame_data = env.reset()
    except Exception as e:
        print(f"Failed to initialize environment: {e}")
        return

    state = RunState(frame_data=frame_data)
    print(f"Started session {getattr(env, 'session_id', 'unknown')} in LEARN mode")
    print(f"Legend mapping from env: {frame_data.legend}")

    subgoal = ""
    consecutive_unchanged = 0
    legend_inferred = False
    last_periodic_step = 0

    while True:
        if state.steps >= cfg.max_steps:
            print("\nMax steps reached. Performing final analysis...")
            agent.refine_and_complete_rules_and_legend()
            break

        if state.steps > 0 and state.steps % 5 == 0 and state.steps != last_periodic_step:
            try:
                subgoal = agent.run_periodic_analysis(state.frame_data)
            except RuntimeError as e:
                print(f"LLM failure during analysis, skipping: {e}")
            last_periodic_step = state.steps

        try:
            action = agent.act_learn(state.frame_data, state.local, subgoal)
        except RuntimeError as e:
            print(f"LLM failure, skipping turn: {e}")
            time.sleep(2)
            continue
        print(f"Action: {action.name}")

        prev_frame = state.frame_data
        next_frame = env.step(action)

        agent.history.append((prev_frame, action, next_frame))
        if len(agent.history) > 200:
            agent.history = agent.history[-200:]
            
        state.local.append((prev_frame, action, next_frame))
        state.frame_data = next_frame

        if prev_frame.frame == next_frame.frame:
            print("Warning: Board state unchanged")
            consecutive_unchanged += 1
            if consecutive_unchanged >= 3:
                print("Stuck — forcing reset")
                state.frame_data = env.step(GameAction.RESET)
                state.local = []
                subgoal = ""
                consecutive_unchanged = 0
            time.sleep(1)
            continue

        consecutive_unchanged = 0
        state.steps += 1

        if not legend_inferred and state.steps >= 10 and len(agent.history) >= 10:
            print("Inferring symbol roles from first 10 steps...")
            agent.infer_legend(agent.history[:10])
            legend_inferred = True

        if next_frame.state in [GameState.WIN, GameState.GAME_OVER] or next_frame.levels_completed != prev_frame.levels_completed:
            print("Level complete!")
            state.local = []
            subgoal = ""
            if cfg.mode == "win" and next_frame.state == GameState.WIN:
                print("World completed successfully!")
                break
            if next_frame.state == GameState.GAME_OVER:
                print("Game Over... Resetting")
                state.frame_data = env.step(GameAction.RESET)

        time.sleep(1)


def run_solving_loop(cfg: Config, env: BaseEnv, agent: Agent) -> None:
    frame_data = env.reset()
    state = RunState(frame_data=frame_data)
    
    print(f"Started session {getattr(env, 'session_id', 'unknown')} in SOLVE mode")
    last_periodic_step = 0
    
    while True:
        if state.steps > 0 and state.steps % 5 == 0 and state.steps != last_periodic_step:
            try:
                # Use analysis to update rules mid-solve, but discard returned subgoal
                agent.run_periodic_analysis(state.frame_data)
            except RuntimeError as e:
                print(f"LLM failure during rules refinement, skipping: {e}")
            last_periodic_step = state.steps

        prev_frame = state.frame_data
        try:
            action = agent.act_solve(state.frame_data, state.frame_data.legend, state.local)
        except RuntimeError as e:
            print(f"LLM failure, skipping turn: {e}")
            time.sleep(2)
            continue
        print(f"Action: {action.name}")
        
        next_frame = env.step(action)
        agent.history.append((state.frame_data, action, next_frame))
        if len(agent.history) > 200:
            agent.history = agent.history[-200:]
            
        state.local.append((state.frame_data, action, next_frame))
        state.steps += 1
        state.frame_data = next_frame
        
        if next_frame.state == GameState.WIN or next_frame.levels_completed != prev_frame.levels_completed:
            print("Level complete!")
            state.local = []
            if next_frame.state == GameState.WIN:
                print("Game completed successfully!")
                break
        
        time.sleep(1)
