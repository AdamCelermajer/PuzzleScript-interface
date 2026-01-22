import time
from argparse import ArgumentParser

from llm_client import LlmClient, Server, Config

class Agent:
    def __init__(self, config: Config, llm_client: LlmClient):
        self.cfg = config
        self.llm_client = llm_client

    def _parse_action(self, text: str) -> str:
        """Extract first valid action letter from LLM output."""
        valid = {'W', 'A', 'S', 'D', 'X', 'Z', 'R', 'w', 'a', 's', 'd', 'x', 'z', 'r'}
        for char in text:
            if char in valid:
                return char.upper()
        return "wait"

    def act(self, board: str, level: int, legend: dict, local: list) -> str:
        hist = "\n".join(f"{i+1}. {a}\n{b}" for i, (b, a) in enumerate(local[-3:]))
        
        if self.cfg.show_legend:
            sys = "Output ONLY a single letter. No explanations. No reasoning. Just the letter."
            leg = f"Legend: {legend}\n"
        else:
            sys = "Output ONLY a single letter. No explanations. No reasoning. Just the letter."
            leg = ""

        prompt = f"{leg}Board:\n{board}\n\nPick ONE: W/A/S/D/X/Z/R"
        response = self.llm_client._call(sys, prompt)
        return self._parse_action(response)

def run_solving_mode(cfg: Config):
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
    
    print(f"Started session {state['id']} in {cfg.mode.upper()} mode")
    
    while True:
        action = agent.act(state['board'], state['level'], state['legend'], state['local'])
        print(f"Action: {action}")
        
        if action.lower() == "wait":
            time.sleep(2)
            continue
        
        res = srv.action(state['id'], action)
        if not res:
            break
        
        state['local'].append((state['board'], action))
        state['steps'] += 1
        state['board'] = res['board']
        
        if res.get('status') == 'game_complete' or res['level'] != state['level']:
            print("Level complete!")
            state['local'] = []
            state['level'] = res['level']
            if res.get('status') == 'game_complete':
                print("Game completed successfully!")
                break
        
        time.sleep(1)

if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("--game", type=str, default="sokoban-basic")
    args = p.parse_args()
    
    cfg = Config(game=args.game, mode='win')
    run_solving_mode(cfg)

