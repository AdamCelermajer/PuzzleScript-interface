"""Build evidence from the independently read checkpoints; never reads original grades."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
if (OUT/'freeze-manifest.json').exists():
    raise SystemExit('Independent artifacts are frozen. Use validate_independent.py; do not regenerate labels.')
INV = [x for x in json.loads((ROOT/'docs/research/rule-learning-audit-20261104/inventory.json').read_text()) if x['run']=='run-D']
CP = {x['cp']: x for x in INV}
TEXT = {n:(ROOT/x['path']).read_text(encoding='utf-8') for n,x in CP.items()}
rows = json.loads((OUT/'independent-labels.json').read_text())

def set_label(n, r, **kw):
    rows[n]['labels'][r].update(kw)

# Final pre-freeze rubric check after full sequential reading. Preserve the progress
# history, including earlier provisional judgments, rather than concealing revisions.
for n in (3,4):
    set_label(n,'K4',belief='partial',source='thinking',evidence_cp=3,
              note='T: Bright ring: an object; the player cannot step on it (it blocks).')
for n in range(13,25):
    set_label(n,'K4',belief='partial',source='thinking' if n<20 else 'both',
              evidence_cp=13,note='T: both endpoints must be in range')
for n in range(20,25):
    set_label(n,'K4',notebook='partial')
set_label(24,'K4',note='T: else: self.dark,self.dashed=None,None',evidence_cp=24)
for n in (8,9,10):
    set_label(n,'K4',note='T: a fused tile cannot receive another ring.',evidence_cp=8)
for n in range(20,25):
    e = min(n,23)
    set_label(n,'K3',note='N: Bar center C = R + 2\u00b7D',evidence_cp=e)
    if n>=21:
        q = '`do ACTION5` \u2014 interact/commit (1 action).' if n==21 else '`do ACTION5` \u2014 commit (1 action).'
        set_label(n,'K1',note='N: '+q,evidence_cp=e)

absence_quote = {
 'K1':'Mapping of ACTION1..5,7 to movement/interactions.',
 'K2':'Level 1: grass field (tile 1) in rows 1-5, cols 1-7; border tiles are 0.',
 'K3':'The player likely moves with some of the actions; others may interact/teleport/etc.',
 'K4':'Level 1: grass field (tile 1) in rows 1-5, cols 1-7; border tiles are 0.',
 'K5':'Mapping of ACTION1..5,7 to movement/interactions.',
 'K6':'Mapping of ACTION1..5,7 to movement/interactions.',
 'K7':'Goal unknown: maybe push/bring dark square to frame, or align items.'}
for r,q in absence_quote.items():
    set_label(0,r,note='N: '+q,evidence_cp=0)
for n in range(1,25):
    for r,x in rows[n]['labels'].items():
        if x['belief']=='absent':
            x['note']=''
            x['evidence_cp']=0

def quote(cp, origin, q):
    t=TEXT[cp]
    split=t.index('## Thinking written since the previous checkpoint')
    lo,hi=(0,split) if origin=='notebook' else (split,len(t))
    pos=t.find(q,lo,hi)
    assert pos>=0,(cp,origin,q)
    assert len(q.split())<=20,(cp,q)
    return dict(cp=cp,path=CP[cp]['path'],origin=origin,
                line_start=t.count('\n',0,pos)+1,
                line_end=t.count('\n',0,pos+len(q))+1,quote=q)

def ev(cp,origin,q):return quote(cp,origin,q)

# Supplemental evidence explicitly supports all parts, both sources, and errors;
# every extract is verbatim and limited to twenty whitespace-delimited words.
supp={
 (1,'K1'):[ev(1,'notebook','ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right'),ev(1,'thinking','So ACTION5 = "pick up" / "confirm"')],
 (1,'K3'):[ev(1,'thinking','Character steps on the bright ring (3)'),ev(1,'notebook','appear directly above and below the socket at (2,6)/(4,6).')],
 (1,'K5'):[ev(1,'notebook','Player is then FROZEN (cannot move).'),ev(1,'thinking','arrow keys rotate the dark ring N/S around the socket')],
 (1,'K6'):[ev(1,'notebook','ACTION5 (while frozen): removes dashed ring, dark ring (6) -> bright ring (3) at same spot.'),ev(1,'thinking','the ring turns bright (3) again, the dashed line disappears, and the character thaws.')],
 (4,'K3'):[ev(4,'thinking','the bar appears centered 2 tiles ahead in the direction of travel.')],
 (11,'K4'):[ev(11,'thinking','Brick centers are valid!!'),ev(11,'thinking','Ring (3), cage (8), brick (0), player\u2026 all suppressed.')],
 (13,'K4'):[ev(13,'thinking','both endpoints must be in range'),ev(13,'thinking','If neither is renderable: no bar')],
 (24,'K4'):[ev(24,'thinking','if basev(*e1) is None or basev(*e2) is None: continue'),ev(24,'thinking','self.frozen=True; self.player=R; self.barD=D; self.barC=C')]
}

rationale={
 'K1':'Four directional controls and ACTION5 confirmation are adopted from cp001 onward.',
 'K2':'Only wall blocking is known from cp004 onward. No adopted orange/normal-crate push rule appears in this fully read run.',
 'K3':'cp001-003 know one relocation/entry case but misattribute it to a fixed socket/pad; cp004 generalizes center two ahead and perpendicular endpoints.',
 'K4':'cp003-004 know refusal effects but explain them as a blocking/one-way ring. cp005-010 learn endpoint constraints with false center/endpoint restrictions. cp011-012 adopt free endpoints regardless of intervening center obstacles. cp013 onward retain false both-endpoints-in-grid restriction; cp024 also explicitly models freeze/removal with zero endpoints. New notebooks omit the no-free-end cancellation and say entry freezes unconditionally.',
 'K5':'The dark/dashed choice and frozen player are explicit from cp001. The one observed axis is sufficient to express the selection mechanism; later text generalizes axes.',
 'K6':'Commit changes the selected dark ring into the placed bright ring and releases the player, explicit from cp001.',
 'K7':'cp005 adopts landing a red ring on a socket as the goal; later all-rings-caged is adopted. This omits either-kind coverage and reverses the source quantifier (all targets versus all rings). Correct substantial red-crate case, therefore partial.'}

ledger=[]
for row in rows:
    n=row['cp']
    notebook_cp=0 if n==0 else 1 if n<20 else min(n,23)
    for r,x in row['labels'].items():
        refs=[]
        if x['note']:
            refs.append(ev(x['evidence_cp'],'notebook' if x['note'].startswith('N:') else 'thinking',x['note'][3:]))
        # Add first/continued thinking support and current-notebook support.
        if x['belief']!='absent':
            first={'K1':1,'K2':4,'K3':1 if n<4 else 4,'K4':3 if n<5 else 5 if n<11 else 11 if n<13 else 13,'K5':1,'K6':1,'K7':5 if n<9 else 9}[r]
            primary=rows[first]['labels'][r]
            if primary['note']:
                refs.append(ev(primary['evidence_cp'],'notebook' if primary['note'].startswith('N:') else 'thinking',primary['note'][3:]))
            refs.extend(supp.get((first,r),[]))
            refs.extend(supp.get((n,r),[]))
            if n>=20:
                qs={
                  'K1':['ACTION1/2/3/4' if n==20 else 'up / down / left / right'],
                  'K2':['brick (impassable)'],
                  'K3':['Player freezes at R.','Ends: e1 = C + rot90cw(D), e2 = C \u2212 rot90cw(D)'] if n==20 else ['Player freezes at R; arrows no longer move it.','ends e1 = C + rot90cw(D) and e2 = C \u2212 rot90cw(D)'],
                  'K4':['An end on brick / ring / cage is **suppressed**','Player freezes at R.'] if n==20 else ['A renderable end must be grass/socket **and not currently occupied** by a ring or cage','Player freezes at R; arrows no longer move it.'],
                  'K5':['While frozen: arrow toward an end swaps dark\u2194dashed'] if n==20 else ['An arrow pointing toward one end swaps dark and dashed'],
                  'K6':['player released at R.'] if n==20 else ['the player is released'],
                  'K7':['No bright rings remain (all caged).'] if n==20 else ['A level completes exactly when **no bright rings remain**']}
                refs.extend(ev(notebook_cp,'notebook',q) for q in qs[r])
        refs=list({(e['cp'],e['origin'],e['quote']):e for e in refs}.values())
        prior = None if n==0 else {'cp':n-1,'rule':r,
                 'same_combined_grade':x['belief']==rows[n-1]['labels'][r]['belief']}
        ledger.append(dict(cp=n,rule=r,belief=x['belief'],notebook=x['notebook'],source=x['source'],
                     notebook_version_cp=notebook_cp,previous=prior,evidence=refs,
                     explanation=rationale[r] if x['belief']!='absent' else
                     'Full notebook and all thinking read. No adopted rule belief; descriptions, proposed tests, and unresolved alternatives do not count. Any quoted uncertainty/context is not itself proof of absence.',
                     review_status='full_text_read'))

source_path='puzzlescript_interface/games/ps_knightoban-v1/script.txt'
sl=(ROOT/source_path).read_text(encoding='utf-8').splitlines()
source=[]
for r,ls in {'K1':[136,141,142,143,144],'K2':[117,125],'K3':[127,129,130],
             'K4':[96,129,130,132,133],'K5':[139,141,142,143,144,146],
             'K6':[135,136],'K7':[97,154]}.items():
    source.append(dict(rule=r,path=source_path,sha256=hashlib.sha256((ROOT/source_path).read_bytes()).hexdigest(),
                  evidence=[dict(line=i,quote=sl[i-1]) for i in ls],
                  status='independently reviewed static source; no gameplay',
                  limitation='Current local source, not a runtime test or independent historical-version provenance audit.'))

def save(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
save('independent-labels.json',rows)
save('evidence.json',ledger)
save('source-verification.json',source)
save('reading-coverage.json',[dict(**x,review_status='full_text_read',order=i,
     notebook_version_cp=0 if x['cp']==0 else 1 if x['cp']<20 else min(x['cp'],23)) for i,x in enumerate(INV)])
with (OUT/'independent-progress.md').open('a',encoding='utf-8') as f:
    f.write('\nPre-freeze rubric/evidence review: K4 cp003-004 revised absent -> partial because adopted ring-blocking conclusion correctly describes refusal effects with a wrong cause (rubric explicit example). K4 cp013-023 revised correct -> partial for adopted both-endpoints-in-range restriction. cp020-024 notebook K4 revised correct -> partial because unconditional freezing omits cancellation when neither endpoint is free. cp024 remains partial, now both. cp011-012 retain correct: essential occupancy criterion adopted, invalid transitions skipped; strict demand for explicit cancellation wording remains an adjudication ambiguity. All 25 checkpoints were fully read before this review; no original labels/curves opened.\n')
print('Prepared 25 checkpoints, 175 slots and exact evidence ledger. Not frozen until validation passes.')
