from pathlib import Path
from unittest.mock import patch
from avo.docker.launch import stage_controller


def test_staging_excludes_game_sources_rules_credentials_and_histories(tmp_path):
    root=tmp_path/'repo'
    files=['avo/run.py','client/arc/types.py','studies/codex_agent/session.py',
           'avo/output/history.txt','client/rules/game/rules.py','avo/tests/test_secret.py',
           'puzzlescript_interface/games/game/script.txt','.env','auth.json']
    for name in files:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
    destination=tmp_path/'staged';destination.mkdir()
    with patch('avo.docker.launch.ROOT',root):stage_controller(destination)
    staged={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
    assert staged=={'avo/run.py','client/arc/types.py','studies/codex_agent/session.py','AGENTS.md'}
