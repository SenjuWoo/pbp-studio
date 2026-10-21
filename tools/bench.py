# Run one full job through the engine from the command line (no browser) for benchmarking.
#   py -3 tools/bench.py klein|qwen|anima --design "text" [--master master.png] [--seed N] [--out DIR]
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import engine

ap = argparse.ArgumentParser()
ap.add_argument("backend", choices=["klein", "qwen", "anima"])
ap.add_argument("--design", default="a heroic cartoon knight")
ap.add_argument("--master", default="")
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--out", default="")
ap.add_argument("--name", default="Bench")
a = ap.parse_args()
e = engine.Engine()
out = a.out or str(Path(engine.APP_DATA) / "bench" / a.backend)
job = e.start_job({"design": a.design, "backend": a.backend, "master_png": a.master, "seed": a.seed,
                   "output_dir": out, "name": a.name, "magic": "Poison", "controlnet": True})
seen = 0
while job.state in ("queued", "running"):
    time.sleep(2)
    for line in job.logs[seen:]:
        print(line, flush=True)
    seen = len(job.logs)
for line in job.logs[seen:]:
    print(line)
print("STATE", job.state, job.error, "->", out)
