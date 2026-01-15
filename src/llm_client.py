import os
import requests
import json
import time
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

SERVER_URL = "http://localhost:3000"
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = "gpt-5-mini-2025-08-07"

if not API_KEY:
    print("❌ Error: OPENAI_API_KEY not found in .env file.")
    exit(1)

client = OpenAI(api_key=API_KEY)

def init_game(game_name="sokoban-basic"):
    try:
        response = requests.post(f"{SERVER_URL}/init", json={"gameName": game_name})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to connect to server: {e}")
        return None

def send_action(session_id, action):
    try:
        response = requests.post(f"{SERVER_URL}/action", json={
            "sessionId": session_id,
            "action": action
        })
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send action: {e}")
        return None

def get_llm_action(board_str, level, legend, history):
    print(board_str)
    
    history_str = ""
    if history:
        history_str = "**Game History (Past Moves):**\n"
        for i, (b, a) in enumerate(history):
            history_str += f"--- Step {i+1} ---\nBoard:\n{b}\nAction Taken: {a}\n\n"
    else:
        history_str = "**Game History:** None (Start of Game)\n"

    prompt = f"""
You are an AI agent playing a PuzzleScript game.
Your goal is to solve the level by choosing the right set of action.

**Level {level}**
**Legend:**
{json.dumps(legend, indent=2)}

{history_str}
**Current Board:**
{board_str}

**Controls:**
- W / UP
- A / LEFT
- S / DOWN
- D / RIGHT
- X / ACTION
- Z / UNDO
- R / RESTART

Output ONLY the command button (e.g., "W", "A", "S", "D", "X"). Do not output any other text.
"""
    try:
        print(f"⏳ Sending request to OpenAI model: {MODEL_NAME}...")
        start_time = time.time()
        
        response = client.responses.create(
            model=MODEL_NAME,
            reasoning={"effort": "low"},
            instructions="You are a PuzzleScript expert player. Output only valid single-key commands.",
            input=prompt
        )
        
        print(f"✅ OpenAI response received in {time.time() - start_time:.2f}s")
        return response.output_text.strip()
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        return "wait"

def main():
    game_name = "sokoban-basic" # Could make this an arg
    print(f"🚀 Starting LLM Client for {game_name} using {MODEL_NAME}...")
    
    data = init_game(game_name)
    if not data:
        return

    session_id = data['sessionId']
    current_board = data['board']
    current_legend = data['legend']
    current_level = data['level']
    
    # History list to store (board, action) tuples
    history = []

    print(f"✅ Session {session_id} started.")
    print(" Check server console for visuals.")

    while True:
        # Get Move from LLM
        print("🤖 Thinking...")
        
        action = get_llm_action(current_board, current_level, current_legend, history)
        print(f"💡 LLM Action: {action}")
        
        if action.lower() == "wait":
            time.sleep(2)
            continue

        # Send Action
        result = send_action(session_id, action)
        if not result:
            break
        
        # Add to history BEFORE updating current_board to new state
        history.append((current_board, action))
        
        # Update State
        current_board = result['board']
        current_level = result['level'] # Might change if level up
        
        if result.get('message'):
            print(f"📣 Server: {result['message']}")
            
        if result.get('status') == 'game_complete':
            print("🎉 Game Complete!")
            break

        # Safety sleep to not spam server/api
        time.sleep(1)

if __name__ == "__main__":
    main()
