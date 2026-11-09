import csv, hashlib, json, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
BASE=ROOT/"docs/research/rule-learning-20261028"
def read(p):return json.loads(p.read_text(encoding="utf-8"))
def write(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csvwrite(name,rows):
    with (OUT/name).open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    freeze=read(OUT/"freeze.json")
    for name,h in freeze["files"].items():assert digest(OUT/name)==h
    independent=read(OUT/"independent-labels.json");evidence=read(OUT/"evidence.json");inv=read(OUT/"inventory.json")
    paths={r["cp"]:ROOT/r["path"] for r in inv}
    key=read(BASE/"grade/key.json")["A"]
    published=read(BASE/"curves-combined.json")[key["run"]]
    assert published["blind_id"]=="A" and published["game"]=="ps_knightoban-v1"
    raw=[];locations={};inputs={}
    for f in sorted((BASE/"grade/run-A").glob("seg-*/labels.json")):
        inputs[f.relative_to(ROOT).as_posix()]=digest(f)
        for r in read(f):raw.append(r);locations[r["cp"]]=f.relative_to(ROOT).as_posix()
    for f in [BASE/"curves-combined.json",BASE/"grade/key.json",BASE/"combine.py"]:inputs[f.relative_to(ROOT).as_posix()]=digest(f)
    raw.sort(key=lambda r:r["cp"])
    assert [r["cp"] for r in raw]==[r["cp"] for r in independent]==[r["cp"] for r in published["checkpoints"]]==list(range(24))
    write("original-raw-run-A.json",raw);write("published-run-A.json",published)
    def quote(cp,q,channel="T"):
        t=paths[cp].read_text(encoding="utf-8");assert q in t
        return {"cp":cp,"path":paths[cp].relative_to(ROOT).as_posix(),"line":t[:t.index(q)].count("\n")+1,"quote":q,"channel":channel}
    wall=quote(2,"the player needs to be at (2,8) [border] to move left into (2,7). Not possible.")
    animation=quote(0,'was a temporary "motion trail"/animation of the ring teleporting from (3,4) to (4,6)!')
    alternate=quote(6,"The ring always goes clockwise, and the dashed shows the counterclockwise option.")
    reverse=quote(0,"Let me move the player above the ball and push the ball down into the hoop.")
    cp2_reject=quote(2,"So the goal isn't " + chr(34) + "get the ring on top of the ball." + chr(34))
    cp2_reopen=quote(2,"So with interpretation B, the ring can land on top of the ball!")
    cp2_plan=quote(2,"So the goal might be to get the ring on top of the ball (3,6)")
    cp2_test=quote(2,"But interpretation A also fits (with a different transformation). I need a 3rd data point to distinguish.")
    groups={
      "wall_evidence": {"category":"clear_error","assessment":"Original labels miss explicit player-border impossibility in cp2. This earns wall-only partial under compound K2 and persists. Cp8+ source must include earlier thinking as well as notebook.","resolution":"Recommend original K2 belief partial at cp2-7 and source thinking there; source both at cp8-23. Frozen independent labels already do this.","evidence":[wall]},
      "selection_animation": {"category":"rubric_issue","assessment":"Frozen audit treats adopted animation/next-tick explanation as a wrong account of choosing. Original treats absence of selection knowledge as absent (cp0-5; notebooks), and later accurate alternate-marker geometry as partial (cp6+). Rubric does not operationalize how much visual knowledge is substantial correct content for compound K5.","resolution":"Unresolved rubric adjudication; do not count all K5 differences as proven original errors. Later original partial has a defensible correct-content basis.","evidence":[animation,alternate,quote(6,"So no hidden state there, just a ghost.")]},
      "reverse_goal": {"category":"rubric_issue","assessment":"Cp0 frozen wrong emphasizes reversal of movable crate and stationary target. Original partial can credit an intended overlap of the two objects despite the wrong causal direction. The observable-effect partial clause leaves a real threshold issue.","resolution":"Unresolved compound-rule threshold; original partial is defensible. Frozen independent labels retained.","evidence":[reverse]},
      "conditional_goal": {"category":"ambiguity","assessment":"Cp2 repeatedly adopts and rejects ring-on-ball, then reopens it conditionally under interpretation B. Frozen wrong carries the rejected-goal belief; late conditional planning may instead count as renewed adoption (partial) or suspension (absent). The original quote at line1798 alone does not resolve final chronology.","resolution":"Unresolved; frozen cp2 K7 wrong is fragile, not a proven original error. Original partial is defensible given the late plan. No frozen-label alteration after comparison.","evidence":[cp2_reject,cp2_reopen,cp2_plan,cp2_test]},
      "notebook_unknown": {"category":"ambiguity","assessment":"Cp16+ notebook says UNKNOWN and lists unconfirmed alternatives, but still runs H1's state sweep and asserts the ring can NEVER reach the ball. Frozen audit treats the acted-on hypothesis/exclusion as wrong; original notebook absent treats the alternatives as unadopted. Combined wrong agrees.","resolution":"Unresolved adoption/scope boundary for notebook-only K7 and consequent source. No combined-score effect.","evidence":[quote(16,"Level 1's win condition is STILL UNKNOWN",'N'),quote(16,"H1: win = a specific (player, ring) state",'N'),quote(16,"Ring can NEVER reach ball (3,6).",'N')]}
    }
    def group(cp,r):
        if r=="K2":return "wall_evidence"
        if r=="K5":return "selection_animation"
        if r=="K7" and cp==0:return "reverse_goal"
        if r=="K7" and cp==2:return "conditional_goal"
        if r=="K7" and cp>=16:return "notebook_unknown"
        raise AssertionError((cp,r))
    diffs=[];pubdiff=[];rawpub=[];curves=[];scoreval={"correct":1,"partial":.5,"wrong":0,"absent":0}
    def score(labels):return round(100*sum(scoreval[v] for v in labels)/7,1)
    def credit(labels):return sum(scoreval[v] for v in labels)
    for i,(a,b,c) in enumerate(zip(independent,raw,published["checkpoints"])):
        assert set(a["labels"])==set(b["labels"])==set(c["belief"])==set(inv[i]["rules"])
        for r,v in a["labels"].items():
            for field in ["belief","notebook","source"]:
                rv=b["labels"][r][field];pv=c[field][r]
                if rv!=pv:rawpub.append({"cp":i,"rule":r,"field":field,"raw":rv,"published":pv})
                if v[field]!=rv:
                    g=group(i,r);e=evidence[i]["evidence"][r]
                    resolved_cp=i
                    while "quote" not in evidence[resolved_cp]["evidence"][r]:resolved_cp=evidence[resolved_cp]["evidence"][r]["persisted_from_cp"]
                    resolved=evidence[resolved_cp]["evidence"][r]
                    d={"cp":i,"rule":r,"field":field,"independent":v[field],"original_raw":rv,"published":pv,"category":groups[g]["category"],"group":g,"original_path":locations[i],"original_note":b["labels"][r].get("note",""),"independent_evidence":e,"resolved_evidence_cp":resolved_cp,"resolved_evidence_line":resolved["line"],"resolved_evidence_quote":resolved["quote"]}
                    diffs.append(d)
                if v[field]!=pv:pubdiff.append({"cp":i,"rule":r,"field":field,"independent":v[field],"published":pv})
        ib=[v["belief"] for v in a["labels"].values()];inn=[v["notebook"] for v in a["labels"].values()]
        rb=[v["belief"] for v in b["labels"].values()];rn=[v["notebook"] for v in b["labels"].values()]
        assert score(c["belief"].values())==c["score"] and score(c["notebook"].values())==c["notebook_score"]
        curves.append({"cp":i,"actions":c["actions"],"minutes":c["minutes"],"independent_combined_credit_out_of_7":credit(ib),"raw_combined_credit_out_of_7":credit(rb),"independent_score":score(ib),"raw_score":score(rb),"published_score":c["score"],"delta_independent_minus_published":round(score(ib)-c["score"],1),"independent_notebook_score":score(inn),"raw_notebook_score":score(rn),"published_notebook_score":c["notebook_score"],"notebook_delta":round(score(inn)-c["notebook_score"],1)})
    assert not rawpub,"Raw/published run-A discrepancies require review"
    assert {(r['cp'],r['rule'],r['field']) for r in diffs}=={(r['cp'],r['rule'],r['field']) for r in pubdiff}
    write("disagreements.json",{"run":"run-A","groups":groups,"field_disagreements":diffs})
    csvwrite("disagreements.csv",[{k:d[k] for k in ["cp","rule","field","independent","original_raw","published","category","group","original_path","original_note","resolved_evidence_cp","resolved_evidence_line","resolved_evidence_quote"]} for d in diffs])
    csvwrite("curve-comparison.csv",curves)
    categories={}
    for cat in ["clear_error","ambiguity","rubric_issue"]:
        ds=[d for d in diffs if d["category"]==cat]
        categories[cat]={"field_entries":len(ds),"checkpoint_rule_slots":len({(d['cp'],d['rule']) for d in ds}),"fields":dict(Counter(d["field"] for d in ds))}
    unresolved=[{k:d[k] for k in ['cp','rule','field','independent','original_raw','category','group']} for d in diffs if d['category']!='clear_error']
    write("unresolved.json",{"meaning":"Reviewed disagreements requiring interpretation/rubric adjudication, not unreviewed or missing labels.","entries":unresolved})
    summary={"run":"run-A","identity":key,"frozen_labels_sha256":freeze["files"]["independent-labels.json"],"comparison_after_freeze":True,"raw_checkpoints":len(raw),"published_checkpoints":len(published['checkpoints']),"slots_checked":168,"fields_checked":504,"field_disagreements":len(diffs),"slot_disagreements":len({(d['cp'],d['rule']) for d in diffs}),"by_field":dict(Counter(d['field'] for d in diffs)),"by_category":categories,"unresolved_field_entries":len(unresolved),"unresolved_checkpoint_rule_slots":len({(d['cp'],d['rule']) for d in unresolved}),"missing_slots":0,"unreviewed_slots":0,"raw_vs_published_field_disagreements":rawpub,"published_run_A_corrections":{str(c['cp']):c['corrected'] for c in published['checkpoints'] if c.get('corrected')},"published_score_mismatch_count":sum(r['independent_score']!=r['published_score'] for r in curves),"published_notebook_score_mismatch_count":sum(r['independent_notebook_score']!=r['published_notebook_score'] for r in curves),"independent_combined_counts":dict(Counter(v['belief'] for r in independent for v in r['labels'].values())),"original_combined_counts":dict(Counter(v['belief'] for r in raw for v in r['labels'].values())),"independent_notebook_counts":dict(Counter(v['notebook'] for r in independent for v in r['labels'].values())),"original_notebook_counts":dict(Counter(v['notebook'] for r in raw for v in r['labels'].values()))}
    write("comparison-summary.json",summary)
    write("comparison-input-hashes.json",{"access_phase":"after independent freeze","recorded_at_utc":datetime.now(timezone.utc).isoformat(),"files":inputs})
    for name,h in inputs.items():assert digest(ROOT/name)==h
    for name,h in freeze['files'].items():assert digest(OUT/name)==h
    write("comparison-validation.json",{"status":"pass","checkpoint_count":24,"rule_slots_checked":168,"fields_checked":504,"raw_published_fields_checked":504,"score_points_recomputed":24,"independent_freeze_hashes_unchanged":True,"original_input_hashes_unchanged":True,"group_quote_checks":sum(len(g["evidence"]) for g in groups.values()),"field_difference_rows":len(diffs),"distinct_difference_keys":len({(d['cp'],d['rule'],d['field']) for d in diffs}),"unresolved_field_entries":len(unresolved),"missing_or_unreviewed_slots":0})
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
