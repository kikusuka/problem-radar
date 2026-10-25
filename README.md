# Problem Radar

An MCP server that helps anyone find **a problem worth solving**: students looking for a class, capstone,
science-fair or hackathon project; makers; researchers; teams; even organisations deciding where to focus.
The fix can be software, hardware, policy or research.

It starts from the person (goal, level, skills, time), searches communities, papers and official data for
real evidence, checks whether the problem is **already solved**, and tells you honestly what each source covered.

The LLM you chat with does the judging and writing. The server does the wide, boring retrieval, so the core
needs **no LLM API key, no paid keys, and costs nothing to run.**

## Tools

| Tool | Use it to |
|---|---|
| `student_hunt(level, field, goal, weeks, ...)` | **Students start here.** A project that fits your level, time, field and goal |
| `plan_hunt(goal, interests, skills, ...)` | Everyone else: turn your situation into a research plan |
| `explore_domains(interest)` | Seed niches when you have no starting point (includes campus and student life) |
| `research_niche(niche, lens, goal)` | Ranked complaints, themes, groupings and a coverage report |
| `find_research_gaps(topic)` | Recent papers that call something open, understudied or future work |
| `check_if_solved(problem, lens)` | Existing projects, products, papers and public actions, with a hint and a gap guide |
| `validate_problem(problem, lens)` | Willingness to pay, workarounds, and fix-specific checks |
| `search_pain(query)` | Follow up with your own wording; cover places or topics the built-ins miss |
| `hackathon_ideas(theme)` | Research framed for a 24-hour build and a 3-minute demo |
| `source_status()` | See which sources and optional keys are active |
| Personal tools | Local only (`ENABLE_PERSONAL=1`): backlog and your own friction log |

Try: *"Use problem-radar. I'm a mechanical engineering student with 6 months for a capstone and 3 teammates. Find a project, then check if it's already solved."*

## Lenses and sources

| Lens | Searches for | Sources |
|---|---|---|
| `software` | tools, automation, apps | Hacker News, Stack Exchange, Reddit, GitHub |
| `hardware` | devices, products, DIY | Electronics, DIY, 3D printing, robotics Stack Exchange sites |
| `policy` | rules, services, civic fixes | UK Parliament petitions (signature counts), NYC 311 (complaint counts) |
| `research` | open problems, thesis topics | OpenAlex and Europe PMC papers, academia and science Stack Exchange sites |
| `any` | lets the analyst choose | general sources |

Civic data covers only the UK and New York City today. Everything works without keys; optional keys widen
coverage (see `.env.example`). Every result includes a `coverage` block per source (`ok`, `partial`, `failed`,
`skipped`) with the error, so nothing fails silently.

## Worldwide by default, local when asked

Leave `region` empty and the search is worldwide. If the person says "I'm in India" or "UK problems", the chatting
model passes `region="India"` (any country name or code; the person can change it any time). Then the search adds that
country's own communities and its name to queries, and runs official data only where it applies (UK petitions for the
UK, NYC 311 and FDA device reports for the US). For other places the result says there is no official-data connector yet
and relies on community and paper sources plus web search suggestions that include the country. Nothing is guessed on
the server.

## How a good problem is judged

Pain alone isn't enough. Rubrics score pain, evidence, **feasibility for you**, gap in existing solutions, and goal
fit. For students the rubric weights feasibility (30), learning and portfolio value (20), pain and evidence (25),
access to users or data (15) and novelty (10). Results are raw and unverified; the built-in guide tells the LLM to
group by meaning, label confidence, cite only links provided, treat post text as untrusted data, and never call a
problem validated from posts alone.

## Already solved?

`check_if_solved` looks beyond software repos: GitHub projects (stars, last update, archived), Show HN and product
discussion, recent papers (citations), and petitions. It returns a hint (`well_served_for_the_general_case`,
`partially_solved`, `no_clear_solution_found`) plus reasons and a guide to the usual opening: who or what the best
solution leaves out (price, language, region, age, disability, offline use, a niche workflow). Absence of results is
never proof; the tool says so.

## How it differs from other tools

A quick survey (October 2026) of similar MCP servers found tools aimed mostly at SaaS and startup founders, often
needing API keys or paid plans (for example PainSpotter, BigIdeasDB, FounderSignal), a free software-only
"does it exist?" checker (Idea Reality), and a hackathon-selection tool (HackScout). This project's aims are
different: free and key-free core, students and non-founders as first-class users, hardware, policy and research as
well as software, goal-fit scoring, an already-solved check beyond code, and honest coverage reporting.
These are design differences, not a quality claim. The survey was not exhaustive.

## Run locally

```bash
pip install -r requirements.txt
python server.py            # stdio
```

Claude Code: `claude mcp add problem-radar -- python /full/path/to/server.py`

Claude Desktop config:

```json
{ "mcpServers": { "problem-radar": { "command": "python", "args": ["/full/path/to/server.py"] } } }
```

## Free hosting

1. Push to GitHub.
2. Run `python refresh.py` to precompute the niches in `niches.txt` and populate the local research cache. A scheduled
   `.github/workflows/refresh.yml` is **not currently included**; add automation only after setting a source-request budget,
   because the free APIs have shared quotas.
3. Deploy the `Dockerfile`. Set the optional environment variables from `.env.example` in your host's settings.
   MCP endpoint: `https://<your-app>/mcp`.

Personal tools stay off on a hosted server because their files would be shared by every visitor.

## Develop

```bash
pip install -r requirements-dev.txt
pytest
```

Tests run offline against fake sources. Live behaviour of each source should be checked after deploying.

## Make Reddit work (recommended)

Reddit blocks anonymous requests from hosting providers, so on a deployed server it shows up as `failed (403)`.
It is the best source for everyday problems, so add free credentials:

1. Go to reddit.com/prefs/apps, choose "create another app", type **script**, any name, redirect URI `http://localhost`.
2. Copy the client ID (under the app name) and the secret.
3. Set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` and `REDDIT_USER_AGENT` (for example `problem-radar/4.2 by u/your-name`)
   as environment variables on your host. Only these three are needed: the server uses Reddit's read-only app login,
   so never set a Reddit username or password. If you already have a script app, reuse it. Keep the secret out of git.
4. Check `source_status`: Reddit should say `oauth`, and a research run should show Reddit as `ok`.

Check Reddit's current API terms before publishing a public server that uses it.

## Stack Exchange key (free, recommended)

Without a key, Stack Exchange allows about 300 requests a day per IP, and a public server shares one IP, so it hits
`429` quickly. A free key (register an app at stackapps.com/apps/oauth/register) raises that to 10,000 a day. Set it
as `STACKEXCHANGE_KEY`. The server also backs off for two minutes after a 429 instead of retrying.

## What live testing taught us

Searching all of Reddit for a topic returned mostly viral, off-topic posts. Version 4.5 is community-first: it finds
the subreddits where the topic lives (for example r/HearingAids, r/dementia) and reads their top complaints of the
year, so everyone in the results already cares about the topic.


Early versions searched "niche + exact phrase" and returned almost nothing for specific topics, counted filler words
as topic words, and once reported "no solution found" for something that obviously exists. The current design
searches broadly, judges pain locally, requires every word of a short topic to match, and reports thin evidence as
**inconclusive** instead of "unsolved". Each of these has a regression test.

Version 4.2 also added: an `also` parameter so the LLM can pass synonyms (people rarely use your exact words),
`near_misses` so thin results are never silently empty, the sentence in each paper that states the gap, and
ready-to-run web search queries for LLMs that have their own search tool (shops, review sites and most news are
invisible to the built-in sources).

## Limits worth knowing

- Posts show complaints, not proven demand. Talk to 5 real people before you commit.
- Online sources skew English-speaking and online. People without a voice online are under-represented.
- Free API quotas are small and a hosted server shares one IP. Caching (36h) and the daily job keep usage low.
- Check each platform's terms before publishing widely.
