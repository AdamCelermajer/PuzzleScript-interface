import os
import requests
from dotenv import load_dotenv

if os.name == 'nt':
    os.system('')

from engine.types import FrameData, GameState, GameAction, ActionInput
from .base_env import BaseEnv

load_dotenv()

# Official ARC-AGI color palette (24-bit true-color)
ARC_PALETTE = {
    0: (0, 0, 0),       # Black     #000000
    1: (0, 116, 217),    # Blue      #0074D9
    2: (255, 65, 54),    # Red       #FF4136
    3: (46, 204, 64),    # Green     #2ECC40
    4: (255, 220, 0),    # Yellow    #FFDC00
    5: (170, 170, 170),  # Grey      #AAAAAA
    6: (240, 18, 190),   # Magenta   #F012BE
    7: (255, 133, 27),   # Orange    #FF851B
    8: (127, 219, 255),  # Sky/Azure #7FDBFF
    9: (135, 12, 37),    # Brown     #870C25
}
RESET = '\033[0m'

def _color_bg(r, g, b):
    return f'\033[48;2;{r};{g};{b}m'

class ArcAgiEnv(BaseEnv):
    """Adapter for the official ARC-AGI-3 REST API (three.arcprize.org)."""

    def __init__(self, task_name: str):
        self.task_name = task_name
        self.session_id = f"arc_{task_name}"
        
        self.api_key = os.environ.get("ARC_API_KEY")
        if not self.api_key:
            raise ValueError("ARC_API_KEY environment variable is missing. Please add it to .env")
            
        self.base_url = "https://three.arcprize.org/api"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        })
        
        # 1. Resolve task_name to real game_id
        games_res = self.session.get(f"{self.base_url}/games")
        if games_res.status_code != 200:
            raise Exception(f"Failed to fetch games list: {games_res.text}")
            
        games = games_res.json()
        resolved_id = None
        for g in games:
            if g.get("game_id") == self.task_name or g.get("title", "").lower() == self.task_name.lower():
                resolved_id = g.get("game_id")
                break
                
        if not resolved_id:
            available = [g.get("title") for g in games[:15]]
            raise ValueError(f"Game '{self.task_name}' not found. Valid examples: {available}")
            
        self.game_id = resolved_id
        
        # 2. Open a Scorecard to track this session
        res = self.session.post(f"{self.base_url}/scorecard/open", json={})
        if res.status_code != 200:
            raise Exception(f"Failed to open scorecard: {res.text}")
            
        self.card_id = res.json().get("card_id")
        self.guid = None
    
    def render(self, frame_data: FrameData) -> None:
        """Visualizes the 2D grid using half-block chars (2 rows per terminal line)."""
        if not frame_data.frame or not frame_data.frame[0]:
            print("Empty ARC frame")
            return
        
        # Color legend: colored squares with numbers
        ARC_NAMES = ['Blk','Blu','Red','Grn','Yel','Gry','Mag','Org','Sky','Brn']
        legend = " ".join(f"\033[48;2;{ARC_PALETTE[i][0]};{ARC_PALETTE[i][1]};{ARC_PALETTE[i][2]}m {i} \033[0m{ARC_NAMES[i]}" for i in range(10))
        print(f"\n{legend}")
        print("Actions: 1=Up 2=Down 3=Left 4=Right 5=Action R=Reset")
        print(f"--- {self.task_name} ---")
        grid = frame_data.frame[0]
        rows = len(grid)
        
        # Process 2 rows at a time using ▄ (lower half block)
        # Background color = top row, foreground color = bottom row
        for y in range(0, rows, 2):
            line = ""
            top_row = grid[y]
            bot_row = grid[y + 1] if y + 1 < rows else None
            for x in range(len(top_row)):
                tr, tg, tb = ARC_PALETTE.get(top_row[x], (0, 0, 0))
                if bot_row:
                    br, bg, bb = ARC_PALETTE.get(bot_row[x], (0, 0, 0))
                    line += f"\033[48;2;{tr};{tg};{tb}m\033[38;2;{br};{bg};{bb}m▄\033[0m"
                else:
                    line += f"\033[48;2;{tr};{tg};{tb}m▀\033[0m"
            print(line)

    def _parse_frame_data(self, data: dict) -> FrameData:
        state_str = data.get("state", "PLAYING")
        if state_str == "NOT_FINISHED": state = GameState.PLAYING
        elif state_str == "NOT_STARTED": state = GameState.GAME_OVER
        elif state_str == "WIN": state = GameState.WIN
        elif state_str == "GAME_OVER": state = GameState.GAME_OVER
        else: state = GameState.PLAYING
        
        avail_dict = {
            1: GameAction.ACTION1,
            2: GameAction.ACTION2,
            3: GameAction.ACTION3,
            4: GameAction.ACTION4,
            5: GameAction.ACTION5,
            6: GameAction.ACTION6,
            7: GameAction.RESET
        }
        
        available_actions = [avail_dict.get(a) for a in data.get("available_actions", []) if a in avail_dict]
        
        action_input_data = data.get("action_input", {})
        action_id = action_input_data.get("id", 0)
        action_input = ActionInput(action=avail_dict.get(action_id, GameAction.RESET), data=action_input_data.get("data", {}))
        
        return FrameData(
            frame=data.get("frame", []),
            state=state,
            levels_completed=data.get("levels_completed", 0),
            game_id=data.get("game_id", self.task_name),
            win_levels=data.get("win_levels", 1),
            guid=data.get("guid", ""),
            full_reset=False,
            available_actions=available_actions,
            action_input=action_input,
            legend={0: 'Black', 1: 'Blue', 2: 'Red', 3: 'Green', 4: 'Yellow', 5: 'Grey', 6: 'Fuchsia', 7: 'Orange', 8: 'Teal', 9: 'Brown'}
        )

    def reset(self) -> FrameData:
        print(f"ARC-AGI-3: requesting reset for {self.task_name}")
        payload = {
            "game_id": self.game_id,
            "card_id": self.card_id
        }
        if self.guid:
            payload["guid"] = self.guid
            
        res = self.session.post(f"{self.base_url}/cmd/RESET", json=payload)
        if res.status_code != 200:
            raise Exception(f"Failed to start/reset game: {res.text}")
            
        data = res.json()
        self.guid = data.get("guid")
        fd = self._parse_frame_data(data)
        self.render(fd)
        return fd

    def step(self, action: GameAction) -> FrameData:
        print(f"ARC-AGI-3: executing {action.name}")
        action_endpoint = f"/cmd/{action.name}"
        if action == GameAction.RESET:
            action_endpoint = "/cmd/RESET"
            
        payload = {
            "game_id": self.game_id,
            "guid": self.guid
        }
        res = self.session.post(f"{self.base_url}{action_endpoint}", json=payload)
        
        if res.status_code != 200:
            raise Exception(f"Failed action {action.name}: {res.text}")
            
        fd = self._parse_frame_data(res.json())
        self.render(fd)
        return fd
