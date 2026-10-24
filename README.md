# Problem Radar

An MCP server that gives any LLM (Claude, etc.) a tool to find **real, evidence-backed problems** worth solving.
It mines Hacker News, GitHub issues and Reddit for pain phrases ("tired of manually...", "is there a tool that..."),
clusters repeated complaints, scores them, and returns ranked problem cards with links to the real posts.

The LLM you chat with does the thinking and writing. This server only fetches, clusters and scores, so it needs
**no LLM API key and costs nothing to run.**

## Tools

| Tool | What it does |
|---|---|
| `find_problems(niche, limit, refresh, sources)` | Ranked problem cards for a niche |
| `get_problem(problem_id)` | Full evidence for one card |
| `hackathon_ideas(theme, limit)` | Problem statements fitted to a hackathon theme |
| `save_problem(problem_id, note)` | Save to your backlog |
| `list_backlog()` | Your saved problems, best first |

Evidence rule: a card only appears if it has 3+ posts from 2+ independent authors.

## Run locally

```bash
pip install -r requirements.txt
python server.py            # stdio
```

Claude Desktop: add to your MCP config

```json
{ "mcpServers": { "problem-radar": { "command": "python", "args": ["/full/path/to/server.py"] } } }
```

Claude Code: `claude mcp add problem-radar -- python /full/path/to/server.py`

Then ask: *"Use problem-radar to find problems in property management."*

## Free, run-and-forget hosting

1. Push this repo to GitHub (public).
2. The included **GitHub Action** (`.github/workflows/refresh.yml`) mines every niche in `niches.txt` daily and
   commits `data/cards/*.json`. Free, no server needed, nothing to babysit.
3. To make it a remote server others can connect to, deploy the `Dockerfile` on a free tier
   (Render web service or a Hugging Face Docker Space). Free instances sleep when idle and wake on the next request.
   Endpoint: `https://<your-app>/mcp`

Note: on a hosted server the backlog file is shared by all users and may reset on redeploy. For personal use,
run it locally.

## Notes

- Reddit often blocks cloud IPs. If it returns nothing, HN and GitHub still work.
- Set `GITHUB_TOKEN` for higher GitHub rate limits (the Action provides one automatically).
- Check each platform's API terms before publishing widely.

## Roadmap

App-store reviews, Stack Overflow, Product Hunt, Upwork-style briefs, a Streamlit viewer, scoring feedback loop.
