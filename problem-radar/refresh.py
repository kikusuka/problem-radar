"""Scheduled refresh. Run by GitHub Actions daily; commits data/cards/*.json back to the repo.

    python refresh.py                 # all niches in niches.txt
    python refresh.py "accounting"    # one niche
"""
import sys

from radar import store

if __name__ == "__main__":
    niches = sys.argv[1:] or [n.strip() for n in open("niches.txt") if n.strip() and not n.startswith("#")]
    for n in niches:
        d = store.refresh(n)
        print(f"{n}: scanned {d['posts_scanned']} posts, {len(d['cards'])} verified problems")
