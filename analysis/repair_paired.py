"""D59: paired comparison of the repair arms (R0 report vs R1 review) by solution: counts fixed in one arm only,
difference with a 95 % bootstrap over tasks (2,000 resamples, seed 20261106), fixed without regressions.
  python3 analysis/repair_paired.py analysis/out/repair/repair_solutions.csv
"""
import csv,random,sys,collections
def run(p):
    R=[r for r in csv.DictReader(open(p)) if r["still_failing_now"]=="1"]
    by=collections.defaultdict(dict)
    for r in R: by[(r["cond"],r["model"],r["task"],r["lang"],r["sample"])][r["arm"]]=r
    ks=[k for k in by if "R0" in by[k] and "R1" in by[k]]
    f=lambda r:r["fixed"]=="1"
    nr=lambda r:r["fixed"]=="1" and r["regression"] in ("0","")
    a=sum(f(by[k]["R0"]) and not f(by[k]["R1"]) for k in ks); b=sum(f(by[k]["R1"]) and not f(by[k]["R0"]) for k in ks)
    n=len(ks)
    d=lambda kk:100*(sum(f(by[k]["R0"]) for k in kk)-sum(f(by[k]["R1"]) for k in kk))/len(kk)
    tasks=collections.defaultdict(list)
    for k in ks: tasks[k[2]].append(k)
    T=sorted(tasks); rnd=random.Random(20261106); bs=[]
    for _ in range(2000):
        kk=[k for t in (rnd.choice(T) for _ in T) for k in tasks[t]]; bs.append(d(kk))
    bs.sort()
    print(p.split("/")[-2], "n",n,"only R0",a,"only R1",b,"diff %.1f (%.1f-%.1f)"%(d(ks),bs[49],bs[1949]),
          "fixed no reg R0 %.1f R1 %.1f"%(100*sum(nr(by[k]["R0"]) for k in ks)/n,100*sum(nr(by[k]["R1"]) for k in ks)/n))
run(sys.argv[1])
