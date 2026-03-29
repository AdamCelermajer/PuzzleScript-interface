import time
from argparse import ArgumentParser

from llm_client import LlmClient, Config
from env_adapter import PuzzleScriptEnv, GameAction, GameState, FrameData
from utils import format_frames
import prompts

class Agent:
    def __init__(self, config: Config, llm_client: LlmClient):
        self.cfg = config
        self.llm_client = llm_client

    def _parse_action(self, text: str) -> GameAction:
        """Extract the action from LLM output (e.g. ACTION1)."""
        text = text.strip().upper()
        if "ACTION1" in text or "W" in text: return GameAction.ACTION1
        if "ACTION2" in text or "S" in text: return GameAction.ACTION2
        if "ACTION3" in text or "A" in text: return GameAction.ACTION3
        if "ACTION4" in text or "D" in text: return GameAction.ACTION4
        if "ACTION5" in text or "X" in text: return GameAction.ACTION5
        if "RESET" in text or "R" in text: return GameAction.RESET
        return GameAction.ACTION5

    def act(self, frame_data: FrameData, legend: dict, local: list) -> GameAction:
        # Pass an empty list for known_rules for now, as solving_mode doesn't load them yet
        sys_prompt, user_prompt = prompts.get_solving_act_prompt(
            format_frames(frame_data.frame), 
            legend, 
            [], 
            self.cfg.show_legend
        )
        response = self.llm_client._call(sys_prompt, user_prompt, model_type="flash")
        return self._parse_action(response)

def run_solving_mode(cfg: Config):
    env = PuzzleScriptEnv(cfg.game, cfg.server_url)
    llm_client = LlmClient(cfg)
    agent = Agent(cfg, llm_client)
    
    frame_data = env.reset()
    
    state = {
        'frame_data': frame_data,
        'steps': 0,
        'local': []
    }
    
    print(f"Started session {env.session_id} in {cfg.mode.upper()} mode")
    
    while True:
        action = agent.act(state['frame_data'], state['frame_data'].legend, state['local'])
        print(f"Action: {action.name}")
        
        next_frame = env.step(action)
        
        state['local'].append((state['frame_data'], action, next_frame))
        state['steps'] += 1
        state['frame_data'] = next_frame
        
        if next_frame.state == GameState.WIN or next_frame.levels_completed != frame_data.levels_completed:
            print("Level complete!")
            state['local'] = []
            if next_frame.state == GameState.WIN:
                print("Game completed successfully!")
                break
        
        time.sleep(1)

if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("--game", type=str, default="sokoban-basic")
    args = p.parse_args()
    
    cfg = Config(game=args.game, mode='win')
    run_solving_mode(cfg)
