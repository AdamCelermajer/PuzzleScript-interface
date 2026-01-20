import os
import time
from argparse import ArgumentParser
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from google import genai

load_dotenv()


@dataclass
class Config:
    server_url: str = "http://localhost:3000"
    model: str = "gemini-2.0-flash-lite-preview-02-05"
    game: str = "sokoban-basic"
    mode: str = "learn"
    max_steps: int = 50
    show_legend: bool = False
    api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found")


class Server:
    def __init__(self, url: str):
        self.url = url

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        try:
            r = requests.post(f"{self.url}/{endpoint}", json=data, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"Error: {e}")
            return None

    def init(self, game: str) -> Optional[dict]:
        return self._post("init", {"gameName": game})

    def action(self, session: str, action: str) -> Optional[dict]:
        return self._post("action", {"sessionId": session, "action": action})


class Agent:
    def __init__(self, config: Config):
        self.cfg = config
        self.llm = genai.Client(api_key=config.api_key)
        self.history: list[tuple[str, str]] = []

    def _parse_action(self, text: str) -> str:
        """Extract first valid action letter from LLM output."""
        valid = {'W', 'A', 'S', 'D', 'X', 'Z', 'R', 'w', 'a', 's', 'd', 'x', 'z', 'r'}
        for char in text:
            if char in valid:
                return char.upper()
        return "wait"

    def _call(self, system: str, prompt: str) -> str:
        try:
            t = time.time()
            r = self.llm.models.generate_content(
                model=self.cfg.model,
                contents=f"{system}\n\n{prompt}"
            )
            print(f"Response time: {time.time()-t:.1f}s")
            return r.text.strip() if r.text else "wait"
        except Exception as e:
            print(f"Error: {e}")
            return "wait"

    def plan_subgoal(self, board: str, level: int, history: list) -> str:
        recent = "\n".join(f"{i+1}. {a}" for i, (b, a) in enumerate(history[-5:]))
        sys = "You are planning the next subgoal in a puzzle game."
        prompt = f"Board:\n{board}\n\nRecent actions:\n{recent}\n\nWhat should be your NEXT immediate subgoal? (1 sentence)"
        return self._call(sys, prompt)

    def act(self, board: str, level: int, legend: dict, local: list, subgoal: str = "", board_changed: bool = True) -> str:
        hist = "\n".join(f"{i+1}. {a}\n{b}" for i, (b, a) in enumerate(local[-3:]))
        
        if self.cfg.show_legend:
            sys = "Output ONLY a single letter. No explanations. No reasoning. Just the letter."
            leg = f"Legend: {legend}\n"
        else:
            sys = "Output ONLY a single letter. No explanations. No reasoning. Just the letter."
            leg = ""

        goal_section = f"SUBGOAL: {subgoal}\n\n" if subgoal else ""
        feedback = "WARNING: Last action did not change the board state!\n" if not board_changed else ""
        
        prompt = f"{leg}{goal_section}{feedback}Board:\n{board}\n\nPick ONE: W/A/S/D/X/Z/R"
        response = self._call(sys, prompt)
        return self._parse_action(response)

    def learn(self) -> str:
        log = "\n\n".join(f"{i}. {b}\nAction: {a}" for i, (b, a) in enumerate(self.history[:50]))
        sys = "Analyze this puzzle game log and deduce the rules."
        prompt = f"Gameplay:\n{log}\n\nDeduce:\n- Movement rules\n- Collision behavior\n- Win condition"
        return self._call(sys, prompt)


def run(cfg: Config):
    srv = Server(cfg.server_url)
    agent = Agent(cfg)
    
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
    
    print(f"Started session {state['id']} in {cfg.mode.upper()} mode")
    
    subgoal = ""
    board_changed = True
    
    while True:
        if cfg.mode == 'learn' and state['steps'] >= cfg.max_steps:
            print(f"\n Final rules:\n{agent.learn()}")
            break
        
        # Plan subgoal every 5 moves
        if state['steps'] % 5 == 0 and state['steps'] > 0:
            print("Planning next subgoal...")
            subgoal = agent.plan_subgoal(state['board'], state['level'], state['local'])
            print(f"Subgoal: {subgoal}\n")
        
        action = agent.act(state['board'], state['level'], state['legend'], state['local'], subgoal, board_changed)
        print(f"Action: {action}")
        
        if action.lower() == "wait":
            time.sleep(2)
            continue
        
        prev_board = state['board']
        res = srv.action(state['id'], action)
        if not res:
            break
        
        agent.history.append((state['board'], action))
        state['local'].append((state['board'], action))
        state['steps'] += 1
        state['board'] = res['board']
        
        # Track if board changed
        board_changed = (prev_board != state['board'])
        if not board_changed:
            print("Warning: Board state unchanged")
        
        if res.get('status') == 'game_complete' or res['level'] != state['level']:
            print("Level complete!")
            state['local'] = []
            state['level'] = res['level']
            board_changed = True
            subgoal = ""  # Reset subgoal for new level
            if cfg.mode == 'win' and res.get('status') == 'game_complete':
                print("Game completed successfully!")
                break
        
        time.sleep(1)


def main():
    p = ArgumentParser()
    p.add_argument("--mode", choices=['win', 'learn'], default='learn')
    cfg = Config(mode=p.parse_args().mode)
    run(cfg)


if __name__ == "__main__":
    main()
