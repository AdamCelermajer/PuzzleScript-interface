import os
import time
from typing import Optional
from argparse import ArgumentParser

from llm_client import LlmClient, Server, Config

class Agent:
    def __init__(self, config: Config, llm_client: LlmClient):
        self.cfg = config
        self.llm_client = llm_client
        self.history: list[tuple[str, str]] = []
        self.inferred_legend: dict = {}
        
        os.makedirs(self.cfg.rules_dir, exist_ok=True)
        self.rules_file = os.path.join(self.cfg.rules_dir, f"{self.cfg.game}_rules.txt")
        self.known_rules = self._load_rules()

    def _extract_json(self, text: str) -> str:
        """Extracts JSON from a string that might be wrapped in markdown."""
        if text.startswith("```json"):
            text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
        return text.strip()

    def infer_legend(self, history: list[tuple[str, str]]):
        sys = "You are a world analyst. Your task is to infer the meaning of the symbols on the board from a history of world states. Provide the output as a JSON object where the key is the symbol and the value is its name (e.g., {\"P\": \"Player\", \"#\": \"Wall\"})."
        
        history_log = "\n\n".join(f"Step {i+1}:\n{b}" for i, (b, a) in enumerate(history))

        prompt = f"WORLD HISTORY (first 50 states):\n{history_log}\n\nInfer the legend for this world based on the object movements and interactions you observe."
        
        response = self.llm_client._call(sys, prompt)
        
        try:
            import json
            cleaned_response = self._extract_json(response)
            self.inferred_legend = json.loads(cleaned_response)
            print(f"Inferred Legend: {self.inferred_legend}")
        except json.JSONDecodeError:
            print(f"Could not parse inferred legend: {response}")

    def _load_rules(self) -> list[str]:
        if os.path.exists(self.rules_file):
            with open(self.rules_file, "r") as f:
                return [line.strip() for line in f.readlines()]
        return []

    def _save_rules(self, rules: list[str]):
        with open(self.rules_file, "w") as f:
            for rule in rules:
                f.write(f"{rule}\n")
        self.known_rules = rules

    def deduce_rules_from_history(self, history: list[tuple[str, str]], rule_focus: Optional[str] = None):
        sys = (
            "You are a world dynamics modeler. Your task is to deduce the fundamental physics of a 2D grid world from a sequence of events. "
            "Your goal is to create a model of the world by defining: "
            "1. The directional meaning of actions (W, A, S, D). "
            "2. The properties of each object symbol (#, O, P, etc.). "
            "Your rules should be concise statements about these meanings and properties. "
            "Output your response as a JSON object with a single key 'rules' which contains a list of rule strings. "
            "Do not suggest rules that are already known."
        )
        
        events = ""
        for i, (prev_board, action) in enumerate(history):
            events += f"Event {i+1}:\nAction: '{action}'\nBoard:\n{prev_board}\n"

        known_rules_text = "KNOWN RULES:\n" + "\n".join(f"- {rule}" for rule in self.known_rules) if self.known_rules else ""
        
        focus_prompt = f"Focus on deducing rules related to: {rule_focus}\n\n" if rule_focus else ""

        prompt = (
            f"{known_rules_text}\n\n"
            f"SEQUENCE OF EVENTS:\n{events}\n\n"
            f"{focus_prompt}"
            "DEDUCE the world model based on the events. For example:\n"
            "- 'P' is an entity that can move .\n"
            "- '#' is an impassable object (blocks movement).\n"
            "- 'O' is a passable object.\n"
        )
        
        response = self.llm_client._call(sys, prompt)
        
        try:
            import json
            data = json.loads(self._extract_json(response))
            new_rules = data.get("rules", [])

            added_any = False
            if new_rules:
                print("--- New Rules Deduced ---")
            for rule in new_rules:
                if rule and rule not in self.known_rules:
                    print(f"- {rule}")
                    self.known_rules.append(rule)
                    added_any = True
            
            if added_any:
                self._save_rules(self.known_rules)
                print("------------------------")
            
        except json.JSONDecodeError:
            print(f"Could not parse rules from response: {response}")

    def refine_and_complete_rules_and_legend(self):
        """
        Analyzes the full game history and the currently known rules to deduce a final,
        comprehensive set of rules and infer the object legend.
        """
        sys = (
            "You are a world analyst. Your task is to produce a final, comprehensive "
            "set of rules and a complete object legend for a world. You will be given "
            "the rules deduced so far and a recent history of world events."
            "Provide the output as a single JSON object with two keys: "
            "'final_rules' (a list of strings) and 'legend' (a dictionary)."
        )

        history_log = "\n\n".join(f"Step {i+1}:\nAction: {a}\nBoard state before action:\n{b}" for i, (b, a) in enumerate(self.history[-20:]))
        
        known_rules_text = "Rules deduced so far:\n" + "\n".join(f"- {rule}" for rule in self.known_rules)

        prompt = (
            f"GIVEN:\n\n{known_rules_text}\n\n"
            f"RECENT GAMEPLAY HISTORY:\n{history_log}\n\n"
            "TASK:\n"
            "1. Analyze the known rules and the recent history.\n"
            "2. Refine, consolidate, and add any missing rules to create a final, comprehensive rule set.\n"
            "3. Infer the complete object legend based on the world events.\n"
            "4. Output a single JSON object containing the 'final_rules' and 'legend'."
        )

        response = self.llm_client._call(sys, prompt)
        
        try:
            import json
            cleaned_response = self._extract_json(response)
            data = json.loads(cleaned_response)
            
            final_rules = data.get("final_rules", [])
            self.inferred_legend = data.get("legend", {})
            
            if final_rules:
                print("\n--- Final Rules and Legend ---")
                print("Legend:", self.inferred_legend)
                print("Rules:")
                for rule in final_rules:
                    print(f"- {rule}")
                self._save_rules(final_rules)
                print("-----------------------------")
            else:
                print("Could not deduce final rules.")

        except json.JSONDecodeError:
            print(f"Could not parse final deduction response: {response}")

    def _parse_action(self, text: str) -> str:
        """Extract first valid action letter from LLM output."""
        valid = {'W', 'A', 'S', 'D', 'X', 'Z', 'R', 'w', 'a', 's', 'd', 'x', 'z', 'r'}
        for char in text:
            if char in valid:
                return char.upper()
        return "wait"

    def plan_subgoal(self, board: str, level: int, history: list) -> str:
        recent = "\n".join(f"{i+1}. {a}" for i, (b, a) in enumerate(history[-5:]))
        sys = (
            "You are an explorer. "
            "Your goal is to find new and interesting interactions to learn from."
        )
        prompt = (
            f"Board:\n{board}\n\n"
            f"Recent actions:\n{recent}\n\n"
            f"Known Rules:\n{self.known_rules}\n\n"
            "Based on the known rules and recent actions, what is a good subgoal "
            "to encounter new interactions and learn new rules? (1 sentence)"
        )
        return self.llm_client._call(sys, prompt)

    def act(self, board: str, level: int, legend: dict, local: list, subgoal: str = "", board_changed: bool = True) -> str:
        hist = "\n".join(f"- {a} (Board unchanged: {prev_b == board})" for i, (prev_b, a) in enumerate(local[-5:]))
        
        sys = (
            "You are an agent in a 2D grid world. Your task is to select the single best action to take next. "
            "Output ONLY a single character for your action. No explanations."
        )
        
        known_rules_text = "KNOWN RULES:\n" + "\n".join(f"- {rule}" for rule in self.known_rules) if self.known_rules else ""

        prompt = (
            f"CURRENT SUBGOAL: {subgoal}\n\n"
            f"BOARD:\n{board}\n\n"
            f"{known_rules_text}\n\n"
            f"RECENT HISTORY (last 5 actions):\n{hist}\n\n"
            "Analyze the board, rules, and recent history. "
            "Your action MUST be a single character: W, A, S, D, or X. "
            "CRITICAL: Do not repeat actions from the RECENT HISTORY if they resulted in the board being unchanged."
        )
        response = self.llm_client._call(sys, prompt)
        return self._parse_action(response)

    def learn(self, legend: dict) -> str:
        log = "\n\n".join(f"{i}. {b}\nAction: {a}" for i, (b, a) in enumerate(self.history[:50]))
        sys = "Analyze this world log and deduce the rules based on the provided legend."
        
        legend_text = "LEGEND:\n" + "\n".join(f"{key}: {value}" for key, value in legend.items()) + "\n"

        prompt = f"{legend_text}\nWorld Actions:\n{log}\n\nDeduce:\n- Movement rules.\n- Collision behavior.\n- Win condition."
        return self.llm_client._call(sys, prompt)


def run_learning_mode(cfg: Config):
    srv = Server(cfg.server_url)
    llm_client = LlmClient(cfg)
    agent = Agent(cfg, llm_client)
    
    data = srv.init(cfg.game)
    if not data:
        return
    
    
    state = {
        'id': data['sessionId'],
        'board': data['board'],
        'level': data['level'],
        'legend': data['legend'],
        'steps': 0,
        'local': []
    }
    
    print(f"Started session {state['id']} in LEARN mode")
    
    subgoal = ""
    board_changed = True
    
    while True:
        if state['steps'] >= cfg.max_steps:
            print("\nMax steps reached. Performing final analysis...")
            
            # 1. Infer legend from the first 50 states
            print("Inferring legend from history...")
            agent.infer_legend(agent.history[:50])
            
            # 2. Learn rules using the inferred legend
            if agent.inferred_legend:
                print("Learning final rules with inferred legend...")
                final_rules = agent.learn(agent.inferred_legend)
                print(f"\nFinal rules:\n{final_rules}")
                if final_rules:
                    agent._save_rules([f"--- FINAL RULES SUMMARY ---\n{final_rules}"])
            else:
                print("Could not infer legend, skipping final rule learning.")
            break
        
        if state['steps'] > 0 and state['steps'] % 5 == 0:
            print("Deducing rules from history...")
            history_for_deduction = agent.history[-5:]
            agent.deduce_rules_from_history(history_for_deduction)

            print("Planning next subgoal...")
            subgoal = agent.plan_subgoal(state['board'], state['level'], agent.history)
            print(f"New subgoal: {subgoal}")
        
        action = agent.act(state['board'], state['level'], state['legend'], state['local'], subgoal, board_changed)
        print(f"Action: {action}")
        
        if action.lower() == "wait":
            time.sleep(2)
            continue
        
        prev_board = state['board']
        res = srv.action(state['id'], action)
        if not res:
            break
        
        agent.history.append((prev_board, action))

        state['local'].append((state['board'], action))
        state['steps'] += 1
        state['board'] = res['board']
        
        board_changed = (prev_board != state['board'])
        if not board_changed:
            print("Warning: Board state unchanged")
        
        if res.get('status') == 'game_complete' or res['level'] != state['level']:
            print("Level complete!")
            state['local'] = []
            state['level'] = res['level']
            board_changed = True
            subgoal = ""
            if cfg.mode == 'win' and res.get('status') == 'game_complete':
                print("World completed successfully!")
                break
        
        time.sleep(1)

if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("--game", type=str, default="sokoban-basic")
    p.add_argument("--max_steps", type=int, default=50)
    args = p.parse_args()
    
    cfg = Config(game=args.game, max_steps=args.max_steps, mode='learn')
    run_learning_mode(cfg)
