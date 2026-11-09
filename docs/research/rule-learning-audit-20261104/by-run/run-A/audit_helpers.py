import json, hashlib
from pathlib import Path
OUT=Path("docs/research/rule-learning-audit-20261104/by-run/run-A")
BASE=Path("docs/research/rule-learning-20261028/grade/run-A")
def checkpoint(cp):
    return next(BASE.glob(f"seg-*/cp-{cp:03}.md"))
def save(cp, changes=None, quotes=None, rationale="Prior beliefs persist after full reading; no adopted replacement.", summary=""):
    rows=json.loads((OUT/"independent-labels.json").read_text(encoding="utf-8"))
    evidence=json.loads((OUT/"evidence.json").read_text(encoding="utf-8"))
    assert cp==len(rows)
    labels={k:{kk:vv for kk,vv in v.items() if kk!="note"} for k,v in rows[-1]["labels"].items()}
    for k,v in (changes or {}).items(): labels[k].update(v)
    path=checkpoint(cp); txt=path.read_text(encoding="utf-8")
    ev={k:{"persisted_from_cp":cp-1,"rationale":rationale} for k in labels}
    for k,q in (quotes or {}).items():
        channel,quote,why=q
        assert quote in txt,(cp,k,quote)
        ev[k]={"quote":quote,"line":txt[:txt.index(quote)].count("\n")+1,"channel":channel,"rationale":why}
        if labels[k]["belief"]!=rows[-1]["labels"][k]["belief"]:
            assert len(quote.split())<=20,(cp,k,"long note")
            labels[k]["note"]=channel+": "+quote
    rows.append({"cp":cp,"labels":labels}); evidence.append({"cp":cp,"path":path.as_posix(),"evidence":ev,"full_read":True,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    for name,value in [("independent-labels.json",rows),("evidence.json",evidence),("progress.json",{"completed":list(range(cp+1)),"frozen":False,"next_cp":cp+1 if cp<23 else None,"total_checkpoints":24,"reviewed_slots":(cp+1)*7,"unreviewed_slots":(23-cp)*7})]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    state="\n".join(f"- {k}: {v['belief']}; notebook {v['notebook']}; source {v['source']}" for k,v in labels.items())
    (OUT/"current-belief.md").write_text(f"# Independent run-A state after checkpoint {cp}\nAll text through this checkpoint read. Originals and curves unopened.\n{state}\n{summary}\nNext checkpoint: {cp+1 if cp<23 else 'none; validate and freeze'}.\n",encoding="utf-8")
    print(f"Saved cp{cp}: {(cp+1)*7}/168 slots")
