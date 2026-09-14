"""Model-free test of the real ARC surface and isolated fresh-solver protocol."""
import argparse
import json
from pathlib import Path
from avo.core.profile import load_profile
from avo.evolution.solver_evaluation import evaluate_solver_workspace
from avo.isolation import new_workspace

parser = argparse.ArgumentParser()
parser.add_argument('--backend-url', required=True)
parser.add_argument('--game-id', required=True)
args = parser.parse_args()
profile = load_profile('puzzlescript', {'backend_url': args.backend_url, 'game_id': args.game_id})
workspace = new_workspace()
(workspace / 'solver.py').write_text('''import sys,json
for line in sys.stdin:
    observation=json.loads(line)['observation']
    assert observation['metadata']['projection']['mode']=='visible-cell-v1'
    assert observation['metadata']['projection']['max_combinations']==65536
    print(json.dumps({'action':'ACTION1'}),flush=True)
''')
result = evaluate_solver_workspace(loaded_profile=profile, workspace=workspace,
    output_dir=Path('/results/evaluation'), max_environment_steps=2, max_wall_seconds=30)
assert result.score['solver_environment_actions'] == 2, result.score
assert result.score['solver_return_code'] == 0, result.score
Path('/results/smoke.json').write_text(json.dumps({'passed': True, 'game_id': args.game_id,
    'actions': 2, 'model_called': False, 'score': result.score}, indent=2))
print(json.dumps({'passed': True, 'game_id': args.game_id, 'actions': 2}))
