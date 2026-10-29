# What Problem Radar claims, and what it does not

Problem Radar retrieves public evidence about a problem and says how much of it there is and what kind. It does not measure how
common or how severe a problem is. Every field below follows from that rule.

## What counts as evidence
| Layer | Sources | What it can show |
|---|---|---|
| people_complaining | Hacker News, Reddit, Stack Exchange | that someone described the problem in their own words |
| builders_working_on_it | GitHub, GitLab | that someone is building or discussing a fix |
| official_data | UK petitions, NYC 311, FDA device reports | a recorded count from an institution (coverage is regional; each item says where) |
| research_interest | OpenAlex, arXiv, Europe PMC | that researchers call it open or understudied |

## Fields and their meaning
- **voices**: distinct handles among *people* posting about the problem. Papers, repositories and official counts are other kinds of
  evidence, not extra voices. A missing handle is never counted. Handles are not verified to be separate people.
- **evidence_strength**: weak / moderate / strong, by a fixed rule.
  strong = 3+ handles and a second kind of evidence; moderate = 3+ handles, or 2 handles plus another kind, or official data alone;
  weak = anything less. It describes the evidence in this sample. It is not prevalence, severity or demand.
- **recency_in_sample**: when the posts were written (first, last, how many in the last two years). Search returns what matches the
  wording and ranks well, so this is not a trend of the problem.
- **demand_evidence** (validation): `behaviour` = payment or workaround reported by the poster; `stated_intent_only` = "I would
  pay", which usually overstates later behaviour and carries the least weight. **Existing solutions are supply, not demand**; they
  never raise the evidence status and may mean the gap is narrower.
- **check_if_solved hint**: from topic words matched in repositories, posts and papers. Stars and citations are popularity, not proof
  the problem is solved for the people who have it.
- **fit rubric points**: a judgment aid, not a validated model.
- **check_claims**: whether a cited URL was really returned by this server, whether the numbers appear in the text, and the best
  supporting sentence. Lexical only: it catches invented links and numbers, not wrong reasoning.

## Known limits (each is tested or stated in output)
1. **Who is heard.** Online posts over-represent connected, literate, English-speaking users, and research on complaint behaviour finds
   that harmed people in some communities complain much less than others. Every result carries `representation_risk`.
2. **Wording.** Retrieval is lexical: a post that describes the topic in other words is not found (strict xfail tests in
   `tests/test_relevance_golden.py`). `people_say` and the `also` parameter are the mitigation.
3. **Quiet is not minor.** Problems people have learned to live with are rarely complained about.
4. **Absence is not evidence of absence.** Thin or empty results say the sources were thin, never that the problem is not there.
5. **Official data is regional.** Only the UK, NYC and the US FDA have connectors. Region packs only point to sources; they are not
   queried and not verified.
6. **Reddit.** Content is held in memory only, never written to disk, in line with Reddit's data terms.

## How relevance is checked
The strict ranking requires the topic's words together and a complaint signal. The wide `candidates` pool requires the topic's words
together in the title or opening text, so one shared word ("price", "mandi", "care") is not enough. Both are checked against a labelled
set built from reported failures (`tests/test_relevance_golden.py`): add a row whenever a live search returns something wrong.
