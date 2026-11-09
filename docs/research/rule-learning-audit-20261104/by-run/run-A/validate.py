import contextlib, glob, hashlib, io, json, runpy, sys
from collections import Counter
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
def read(p): return json.loads(p.read_text(encoding="utf-8"))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    inv=[r for r in read(ROOT/"docs/research/rule-learning-audit-20261104/inventory.json") if r["run"]=="run-A"]
    labels=read(OUT/"independent-labels.json"); evidence=read(OUT/"evidence.json"); log=read(OUT/"read-log.json")
    assert read(OUT/"labels.json")==labels
    assert [r["cp"] for r in inv]==list(range(24))
    assert [r["cp"] for r in labels]==[r["cp"] for r in inv]==[r["cp"] for r in evidence]==[r["cp"] for r in log]
    texts={}; notebooks={}; current=None; quotes=0; notes=0; persisted=0
    for r in inv:
        cp=r["cp"]; p=ROOT/r["path"]; data=p.read_bytes()
        assert len(data)==r["bytes"] and digest(p)==r["sha256"]
        t=p.read_text(encoding="utf-8");texts[cp]=t
        if "NEW VERSION" in t:current=cp
        notebooks[cp]=current
        assert log[cp]["full_text_read_by_reviewer"] and log[cp]["lines"]==len(t.splitlines())
        assert evidence[cp]["full_read"] and evidence[cp]["sha256"]==r["sha256"]
    def check_quote(ref,cp):
        nonlocal quotes
        at=ref.get("cp",cp); t=texts[at]; q=ref["quote"];line=ref["line"]
        assert q in t and q in t.splitlines()[line-1],(cp,ref)
        assert at<=cp
        if "path" in ref:assert ref["path"]==inv[at]["path"]
        split=t.index("## Thinking written since the previous checkpoint")
        if ref.get("channel")=="N":assert t.index(q)<split
        if ref.get("channel")=="T":assert q in t[split:]
        quotes+=1
    prev={}
    for row,er in zip(labels,evidence):
        cp=row["cp"];assert set(row["labels"])==set(inv[cp]["rules"])==set(er["evidence"])
        for k,v in row["labels"].items():
            assert v["belief"] in {"correct","partial","wrong","absent"}
            assert v["notebook"] in {"correct","partial","wrong","absent"}
            assert v["source"] in {"notebook","thinking","both","none"}
            assert (v["belief"]=="absent")== (v["source"]=="none")
            if notebooks[cp] is None:assert v["notebook"]=="absent"
            if v.get("note"):
                n=v["note"];assert n[:3] in {"T: ","N: "};assert len(n[3:].split())<=20
                assert n[3:] in texts[cp];notes+=1
            if v["belief"]!=prev.get(k) and v["belief"]!="absent":assert v.get("note")
            prev[k]=v["belief"]
            e=er["evidence"][k]
            if "quote" in e:check_quote(e,cp)
            else:
                persisted+=1;pc=e["persisted_from_cp"];assert 0<=pc<cp
                assert labels[pc]["labels"][k]["belief"]==v["belief"]
                seen={cp}
                while "quote" not in evidence[pc]["evidence"][k]:
                    assert pc not in seen;seen.add(pc);pc=evidence[pc]["evidence"][k]["persisted_from_cp"]
            if v["source"]=="both":
                check_quote(e["notebook_support"],cp);check_quote(e["thinking_support"],cp)
                assert e["notebook_support"]["cp"]==notebooks[cp]
                assert v["notebook"]==v["belief"]
    sv=read(OUT/"source-verification.json")
    for source in [sv,sv["input_mapping"]]:
        p=ROOT/source["path"];assert digest(p)==source["sha256"];ls=p.read_text(encoding="utf-8").splitlines()
        refs=source.get("evidence",[]) or [e for r in source["rules"].values() for e in r["evidence"]]
        for r in refs:assert ls[r["line"]-1]==r["quote"]
    # Execute unmodified repository checker, adapting only checkpoint discovery to this cross-segment output layout.
    oldglob=glob.glob;oldargv=sys.argv[:];output=io.StringIO()
    def inventory_glob(pattern,*args,**kwargs):
        if Path(pattern).parent==OUT and Path(pattern).name=="cp-*.md":return [str(ROOT/r["path"]) for r in inv]
        return oldglob(pattern,*args,**kwargs)
    try:
        glob.glob=inventory_glob;sys.argv=["check.py",str(OUT)]
        with contextlib.redirect_stdout(output):runpy.run_path(str(ROOT/"docs/research/rule-learning-20261028/grade/check.py"),run_name="__main__")
    finally:glob.glob=oldglob;sys.argv=oldargv
    checker=output.getvalue().strip();assert checker=="ok: 24 checkpoints x 7 rules",checker
    frozen=OUT/"freeze.json"
    if frozen.exists():
        for name,h in read(frozen)["files"].items():assert digest(OUT/name)==h,("frozen file modified",name)
    result={"status":"pass","checkpoint_count":24,"rule_count":7,"slot_count":168,"missing_slots":0,"unreviewed_slots":0,"checkpoint_hashes_matched":24,"exact_quote_checks":quotes,"note_checks":notes,"persistence_links":persisted,"repository_checker":checker,"checker_layout_adapter":"Inventory paths supplied to glob; original checker code unmodified.","combined_counts":dict(Counter(v["belief"] for row in labels for v in row["labels"].values())),"notebook_counts":dict(Counter(v["notebook"] for row in labels for v in row["labels"].values())),"source_counts":dict(Counter(v["source"] for row in labels for v in row["labels"].values()))}
    (OUT/"validation.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
