import os
import requests
import json
import time
import argparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from google import genai

# --- Configuration & Setup ---
load_dotenv()

@dataclass
class Config:
    server_url: str = "http://localhost:3000"
    api_key: str = os.getenv("GOOGLE_API_KEY")
    model_name: str = "gemini-2.0-flash-lite-preview-02-05"
    game_name: str = "sokoban-basic"
    mode: str = "win" # 'win' or 'learn'
    learning_games_limit: int = 5
    learning_steps_limit: int = 10

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("❌ Error: GOOGLE_API_KEY not found in .env file.")

# --- API Interaction ---
class GameServer:
    def __init__(self, url: str):
        self.url = url

    def init_game(self, game_name: str) -> Optional[Dict[str, Any]]:
        try:
            res = requests.post(f"{self.url}/init", json={"gameName": game_name})
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"❌ Connection Error: {e}")
            return None

    def send_action(self, session_id: str, action: str) -> Optional[Dict[str, Any]]:
        try:
            res = requests.post(f"{self.url}/action", json={"sessionId": session_id, "action": action})
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"❌ Action Error: {e}")
            return None

# --- LLM Agent ---
class LLMAgent:
    def __init__(self, config: Config):
        self.client = genai.Client(api_key=config.api_key)
        self.model = config.model_name
        self.history: List[tuple] = [] # Stores (board_state, action_taken)

    def _call_llm(self, prompt: str, instructions: str) -> str:
        try:
            print(f"⏳ Calling {self.model}...")
            start = time.time()
            
            # Combine instructions and prompt since generate_content suggests a single 'contents' or separate system instruction if supported
            # The snippet provided uses 'contents'. We can prepend instructions to content or check SDK for system_instruction.
            # Assuming simple content usage for now based on snippet "contents=".
            
            full_prompt = f"{instructions}\n\n{prompt}"
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
            )
            
            print(f"✅ Response in {time.time() - start:.2f}s")
            return response.text.strip() if response.text else ""
        except Exception as e:
            print(f"❌ LLM Error: {e}")
            return "wait"

    def get_action(self, board: str, level: int, legend: Dict, game_history: List) -> str:
        history_str = "\n".join([f"Step {i+1}: Action {a}\n{b}" for i, (b, a) in enumerate(game_history[-5:])]) # Keep context short?
        
        prompt = f"""
            **Level {level}**
            **Legend**: {json.dumps(legend, indent=2)}
            **History (Last 5 moves)**:
            {history_str}

            **Current Board**:
            {board}

            **Controls**: W/A/S/D (Move), X (Action), Z (Undo), R (Restart)
            Output ONLY the single-letter command.
            """
        return self._call_llm(prompt, "You are a PuzzleScript expert. Solve the level.")

    def induce_rules(self) -> str:
        print("🧠 Inducing rules from observed gameplay...")
        # Compile all history into a summary (sampling to avoid context limit if needed)
        combined_history = ""
        for i, (board, action) in enumerate(self.history[:50]): # First 50 steps as sample
            combined_history += f"State {i}:\n{board}\nAction: {action}\n\n"
        
        prompt = f"""
            Below is a log of gameplay from a 2D grid puzzle game.
            Based ONLY on these observations, deduce the mechanics and rules of the game.
            - How do objects move?
            - What happens when objects collide?
            - What is the win condition?

            Gameplay Log:
            {combined_history}
            """
        return self._call_llm(prompt, "You are a game mechanics researcher. specific rules.")

# --- Game Loops ---
def run_game_loop(config: Config, server: GameServer, agent: LLMAgent):
    data = server.init_game(config.game_name)
    if not data: return
    
    session_id = data['sessionId']
    board = data['board']
    level = data['level']
    legend = data['legend']
    
    games_played = 0
    total_steps = 0
    local_history = [] 

    print(f"🚀 Started Session: {session_id} | Mode: {config.mode.upper()}")

    while True:
        # Check termination for learning mode
        if config.mode == 'learn' and total_steps >= config.learning_steps_limit:
            print("🛑 Step limit reached.")
            rules = agent.induce_rules()
            print("\n📜 **INDUCED RULES:**")
            print(rules)
            break

        action = agent.get_action(board, level, legend, local_history)
        print(f"💡 Action: {action}")

        if action.lower() == "wait":
            time.sleep(2)
            continue

        res = server.send_action(session_id, action)
        if not res: break

        # Record Global History for Learning
        agent.history.append((board, action))
        local_history.append((board, action))
        
        total_steps += 1

        # Update State
        board = res['board']
        level_new = res['level']
        
        if res.get('status') == 'game_complete' or level_new != level:
            print("🎉 Level Complete / Game Over")
            games_played += 1
            local_history = [] # Reset local history for new level
            level = level_new
            if config.mode == 'win' and res.get('status') == 'game_complete':
                print("🏆 Victory!")
                break
        
        time.sleep(1)

# --- Entry Point ---
def main():
    parser = argparse.ArgumentParser(description="PuzzleScript LLM Client")
    parser.add_argument("--mode", choices=['win', 'learn'], default='win', help="Mode: 'win' to play, 'learn' to induce rules")
    args = parser.parse_args()

    config = Config(mode=args.mode)
    server = GameServer(config.server_url)
    agent = LLMAgent(config)
    
    run_game_loop(config, server, agent)

if __name__ == "__main__":
    main()
