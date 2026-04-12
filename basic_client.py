import time

import arc_agi
from arc_agi import OperationMode
from arcengine import GameAction


arc = arc_agi.Arcade(
    operation_mode=OperationMode.ONLINE,
    arc_base_url="http://127.0.0.1:8000",
    arc_api_key="local-dev",
)

env = arc.make("sokoban-basic-v1", render_mode="terminal")
env.reset()

for _ in range(10):
    time.sleep(1)
    env.step(GameAction.ACTION1)

print(arc.get_scorecard())
