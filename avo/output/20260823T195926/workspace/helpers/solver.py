"""Reusable parser/predictor. Will fill once mechanics known."""
import json, sys

def load(path='current_state.json'):
    return json.load(open(path))

def show(g):
    for r,row in enumerate(g):
        print(r,' '.join(str(x) for x in row))

if __name__ == '__main__':
    s = load()
    show(s['grid'])
    print('actions_used', s['actions_used'], 'state', s['state'], 'levels', s['levels_completed'])
