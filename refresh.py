"""Scheduled refresh. Run by GitHub Actions daily; commits data/research/*.json back to the repo so the hosted
server answers instantly from fresh results.

    python refresh.py                  # quick research for every niche in niches.txt
    python refresh.py deep "accounting"   # deep research for one niche
"""
import os
import sys

from radar import research

if __name__ == "__main__":
    os.environ.setdefault("RADAR_RATE_WAIT", "25")  # offline job waits for rate-limit tokens instead of skipping
    args = sys.argv[1:]
    depth = "quick"
    if args and args[0] in ("quick", "deep"):
        depth, args = args[0], args[1:]
    niches = args or [n.strip() for n in open("niches.txt") if n.strip() and not n.startswith("#")]
    for line in niches:
        n, _, lens = (p.strip() for p in line.partition("|"))
        d = research.research(n, depth, force=True, lens=lens or "any")
        states = {k: v["state"] for k, v in d["coverage"].items()}
        print(f"{n}: fetched {d['posts_fetched']}, relevant {d['posts_relevant']}, sources {states}")
