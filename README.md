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
| `software` | tools, automation, apps | Hacker News, Stack Exchange, Reddit, GitHub, GitLab (with token); Bluesky is currently opt-in only |
| `hardware` | devices, products, DIY | Reddit, assistive-device reports, specialist Stack Exchange sites; Bluesky is currently opt-in only |
| `policy` | rules, services, civic fixes | UK Parliament petitions, NYC 311, community posts |
| `research` | open problems, thesis topics | OpenAlex, arXiv, Europe PMC, academia and science Stack Exchange sites |
| `any` | lets the analyst choose | general sources |

Civic data covers only the UK and New York City today. arXiv needs no key. Bluesky is temporarily excluded from default queries after the live endpoint returned HTTP 403; pass `sources=["bluesky"]` only for explicit diagnostics. GitLab issue search is enabled when `GITLAB_TOKEN` is set; optional keys widen
coverage (see `.env.example`). Every result includes a `coverage` block per source (`ok`, `partial`, `failed`,
`skipped`) with the error, so nothing fails silently.

## Public MCP limits and evidence semantics

The hosted MCP is stateless for public research calls: it does not create a personal backlog for visitors.
Personal backlog/friction tools are disabled over HTTP. The connected LLM is the reasoning layer; this server
retrieves public-source leads and does not call a hosted LLM or embedding API.

To protect the shared free-tier instance, each query/problem is capped at 400 characters; `also` accepts up to
four related terms of at most 200 characters each; source and Stack Exchange site selectors are bounded and
deduplicated. One tool call can schedule at most 16 source jobs. Each upstream provider is limited to at most
two outbound request units per public MCP tool call; Reddit's community adapter uses both units for one
community-discovery query and one complaint query, while GitHub issue and repository searches share a budget.
When Reddit OAuth must obtain a new access token, that token request also consumes one unit, so the first
call uses a single Reddit data search rather than exceeding the two-request cap.
arXiv requests are spaced by at least three seconds process-wide. There are no automatic web-search fallbacks,
quota-exhaustion retries, or paid-provider substitutions. Across concurrent calls, the shared executor has
8 workers and a 32-job in-flight cap. Queued work that misses the request deadline is cancelled where possible;
running work retains its capacity slot until it actually finishes. These are workload guardrails, not per-client
rate limiting or DDoS protection: public visitors still share the same upstream API quotas and source capacity.

Read coverage before drawing conclusions. `queries_planned` counts planned source jobs; `queries_budgeted`
counts jobs admitted after the job/provider caps, while `provider_request_units_budgeted` estimates outbound
requests admitted by the planner. `provider_request_units_used`, `provider_request_counts`, and
`provider_request_denials` report actual outbound request attempts enforced by the HTTP layer. `queries_run`
counts completed jobs; `queries_succeeded` counts successful source responses; `queries_timed_out` counts
running jobs that missed the deadline; and `queries_cancelled_before_start` counts queued jobs cancelled after
the deadline. Per-source coverage reports partial work and work omitted by the request/provider limits. When
hard constraints exclude an otherwise topical pain report, inspect `supporting_evidence` and its
`missing_constraints`; that tier does not count as a qualifying top result.

For niche research and solution checks, explicitly stated requirements such as offline operation, low-resource
hardware, affordability and platform can exclude candidates that do not demonstrate them. Those candidates may
appear in `near_misses` with `missing_constraints`. This is deliberately conservative: no matching result is not
proof that no solution exists. For `validate_problem`, `evidence_status` distinguishes
`insufficient_evidence`, `limited_evidence`, and `evidence_found_needs_validation`. Spending/price mentions
(`paying_signals`) are separate from explicit positive purchase intent (`willingness_to_pay_signals`).
Neither public posts nor a willingness-to-pay statement alone validates a market.


## Retrieval quality and evidence classes

Searches schedule a small number of equivalent queries inside the same source-job and provider-request budgets. `query_variants_scheduled` reports the distinct query strings actually selected for that call. Technical-failure alternatives replace the failure phrase (for example, crash wording with an OOM or freeze equivalent) rather than appending every synonym to an AND-style query. Query-based providers share the primary query, then rotate alternate wording across providers so each provider's limited second request can explore a different variant. There is no second search phase, paid fallback, or unbounded retry.

Complaint results and solution leads are different kinds of evidence. Results may include an `evidence_kind` such as `technical_failure_report`, `reported_complaint`, `workaround_or_manual_process`, `help_request`, `product_comparison`, `product_announcement`, `solution_showcase`, `technical_tutorial`, or `general_discussion`. A specific LLM query also requires an LLM/language-model/runtime cue; Android plus generic crash or memory vocabulary is not enough. These labels are transparent heuristics for inspection, not proof that a post is genuine. Promotional announcements and detected solution showcases do not qualify as independent complaint results; relevant leads are kept in `near_misses` where the relevance checks support it.

`search_diagnostics` distinguishes qualifying results, related candidates only, limited coverage, source failures, and completed searches with no qualifying evidence. An empty result is never proof that a problem does not exist.

`evidence_summary` reports the count of qualifying posts, distinct source types, and non-empty source/author-handle pairs. Handles are not identity-verified, cross-posts may exist, and public posts are not a representative survey. Cross-source results are a corroboration clue—not market validation or proof of prevalence.

## Worldwide by default, local when asked

Leave `region` empty and the search is worldwide. If the person says "I'm in India" or "UK problems", the chatting
model passes `region="India"` (any country name or code; the person can change it any time). Then the search adds that
country's own communities and its name to queries, and runs official data only where it applies (UK petitions for the
UK, NYC 311 and FDA device reports for the US). For other places the result says there is no official-data connector yet
and relies on community and paper sources plus suggested external search queries that include the country; the server
does not automatically run a general web search. Nothing is guessed on the server.

## How a good problem is judged

Pain alone isn't enough. Rubrics score pain, evidence, **feasibility for you**, gap in existing solutions, and goal
fit. For students the rubric weights feasibility (30), learning and portfolio value (20), pain and evidence (25),
access to users or data (15) and novelty (10). Results are raw and unverified; the built-in guide tells the LLM to
group by meaning, label confidence, cite only links provided, treat post text as untrusted data, and never call a
problem validated from posts alone.

Vendor-style software roundups and guides (for example, "best software" lists, "complete guide" articles, or
vendor explainers about how teams can use a product) are labeled `vendor_editorial`. They can help identify
existing products, but they are not counted as independent payment, willingness-to-pay, or workaround signals.
They should not be presented as first-person complaints.

## Already solved?

`check_if_solved` looks beyond software repos: GitHub projects (stars, last update, archived), Show HN and product
discussion, recent papers (citations), and petitions. It returns a hint (`well_served_for_the_general_case`, `partially_solved`, `no_clear_solution_found`, or
`inconclusive_constraints_not_matched`) plus reasons and a guide to the usual opening: who or what the best
solution leaves out (price, language, region, age, disability, offline use, a niche workflow). A paper or petition
can be relevant context, but neither alone proves a working solution exists; research-only findings do not trigger
`partially_solved` by themselves. Absence of results is never proof; the tool says so.

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

Reddit blocks anonymous requests from hosting providers, so on a deployed server it may show up as `failed (403)`.
Direct Reddit search is prioritized in the request budget; community discovery is opt-in because it consumes both
available Reddit request units. Add free credentials to improve direct-search access:

1. Go to reddit.com/prefs/apps, choose "create another app", type **script**, any name, redirect URI `http://localhost`.
2. Copy the client ID (under the app name) and the secret.
3. Set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` and `REDDIT_USER_AGENT` (for example `problem-radar/4.2 by u/your-name`)
   as environment variables on your host. Only these three are needed: the server uses Reddit's read-only app login,
   so never set a Reddit username or password. If you already have a script app, reuse it. Keep the secret out of git.
4. Check `source_status`: Reddit should say `oauth`, and a research run should show Reddit as `ok`.

Check Reddit's current API terms before publishing a public server that uses it.

## Additional public sources

GitLab global issue search adds public bug reports and feature discussions from outside GitHub. It requires a
free personal access token with the narrow `read_api` scope; set it as `GITLAB_TOKEN`. When the token is absent,
GitLab is excluded from default searches rather than spending budget on a request that cannot work. See
https://docs.gitlab.com/api/search/ and https://docs.gitlab.com/api/rest/authentication/.


Bluesky's public read-only AppView adapter requires no key, but it is currently excluded from default searches
because the live hosted endpoint returned HTTP 403. Do not count it as available coverage until its public endpoint
is verified again. When enabled, its posts are unverified leads rather than representative evidence of demand.

arXiv adds open technical preprints and abstracts, particularly useful for AI, computer science, and engineering
research gaps. No key is required. The adapter allows at most one arXiv query per MCP tool call and respects
process-wide request-spacing guidance; when requests are too close together, the source is deferred instead of
holding a worker thread or retrying.

Crossref and PubMed/NCBI are possible future additions, but they mostly overlap with the scholarly metadata already
provided by OpenAlex and Europe PMC. Before adding them, benchmark whether they supply genuinely new abstracts or
evidence rather than duplicate citations. We should prefer a smaller number of complementary sources to a long list
of noisy endpoints.

## Stack Exchange key (free, recommended)

Without a key, Stack Exchange allows about 300 requests a day per IP, and a public server shares one IP, so it hits
`429` quickly. A free key (register an app at stackapps.com/apps/oauth/register) raises that to 10,000 a day. Set it
as `STACKEXCHANGE_KEY`. The server also backs off for two minutes after a 429 instead of retrying.

## What live testing taught us

Searching all of Reddit for a topic can return viral, off-topic posts. Default research now prioritizes direct Reddit
search so a community-discovery call cannot consume both Reddit request units and displace complaint retrieval.
The `reddit_community` adapter remains available as an explicit source when community discovery itself is the goal;
it costs two request units for subreddit lookup plus one complaint search, so it is not included in default lens plans.


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
- Free API quotas are shared and limited; no public API should be described as unlimited. Every actual outbound request passes through a per-tool-call provider budget, and an in-process per-provider minute limiter provides an additional guard. No automatic retries, generic web-search fallback, or paid-provider substitution is enabled.
- Duplicate calls within one process are coalesced. Successful research is cached for 36 hours; empty or limited results are cached only briefly to avoid spending the same free quota repeatedly. Render's local filesystem can be ephemeral, and these in-memory request limits/cache are not shared across multiple instances or retained across restarts.
- Check each platform's terms before publishing widely.
