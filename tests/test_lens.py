from radar import explore as X
from radar import research
from radar import sources as S


def V(i, title, snippet, source="reddit/eldercare", comments=10, url=None, **k):
    return {"id": f"c{i}", "title": title, "snippet": snippet, "source": source, "comments": comments, "score": 5,
            "url": url or f"https://www.reddit.com/r/eldercare/comments/abc{i}/x/", "kind": "general_discussion", **k}


VIEWS = [
    V(1, "Assisted living costs are insane", "assisted living facility monthly fees keep rising for my mother"),
    V(2, "Assisted living vs home care", "we compared assisted living facility fees and home care hours"),
    V(3, "Hospice paperwork confusion", "assisted living staff could not explain hospice paperwork", source="reddit/AgingParents"),
    V(4, "Ask HN: tool for caregivers", "looking for a tool to share a caregiver schedule", source="hn", url="https://news.ycombinator.com/item?id=111"),
]


def test_people_say_mines_the_communitys_own_words_not_the_query():
    words = X.people_say(VIEWS, "elder care", ["elder care"])
    assert "assisted living" in words and "elder" not in " ".join(words)


def test_communities_and_gaps_say_where_to_go_and_what_is_missing():
    comms = X.communities(VIEWS)
    assert comms[0] == {"where": "reddit/eldercare", "posts": 2}
    gaps = X.gaps(VIEWS, research.EVIDENCE_LAYER)
    assert {g["missing"] for g in gaps} == {"builders_working_on_it", "official_data", "research_interest"}


def test_next_moves_are_concrete_tool_calls():
    vocab = X.people_say(VIEWS, "elder care", ["elder care"])
    moves = X.next_moves(VIEWS, [], vocab, X.communities(VIEWS), X.gaps(VIEWS, research.EVIDENCE_LAYER), "elder care", "policy")
    tools = [m["tool"] for m in moves]
    assert tools[0] == "read_thread" and "search_pain" in tools and "check_if_solved" in tools
    assert all(m["args"] and m["why"] for m in moves)
    assert moves[0]["args"]["url"].startswith("https://")


def test_research_payload_carries_the_lens(monkeypatch):
    out = research.research("quickbooks invoices", force=True)
    for key in ("people_say", "communities", "evidence_gaps", "next_moves"):
        assert key in out
    assert out["next_moves"] and out["next_moves"][-1]["tool"] in {"check_if_solved", "find_research_gaps"}


def test_comment_flags_point_at_lines_to_read():
    f = X.comment_flags("I pay $30 a month for a spreadsheet workaround, is there a tool for this?")
    assert f["asks_for_solution"] and f["workaround"] and f["mentions_payment"]
    assert not any(X.comment_flags("Nice weather today").values())


def test_read_thread_rejects_other_hosts_and_bad_links():
    assert "error" in S.read_thread("https://evil.example.com/item?id=1")
    assert "error" in S.read_thread("http://news.ycombinator.com/item?id=1")
    assert "error" in S.read_thread("https://news.ycombinator.com/item?id=abc")
    assert "error" in S.read_thread("https://www.reddit.com/r/x/")


def test_read_thread_parses_hn_and_hides_authors(monkeypatch):
    tree = {"title": "Ask HN", "text": "<p>post</p>", "children": [
        {"author": "secret", "text": "I pay $20 a month for a workaround", "points": 3, "children": [{"author": "x", "text": "same here", "children": []}]},
        {"author": "gone", "text": None, "children": []}]}
    monkeypatch.setattr(S, "_get", lambda *a, **k: (tree, ""))
    out = research.read_thread("https://news.ycombinator.com/item?id=42")
    assert out["source"] == "hn" and len(out["comments"]) == 2
    assert "secret" not in str(out) and out["flagged"]["mentions_payment"] == 1


def test_read_thread_parses_reddit(monkeypatch):
    data = [{"data": {"children": [{"data": {"title": "T", "selftext": "body"}}]}},
            {"data": {"children": [{"kind": "t1", "data": {"body": "I would pay for this", "score": 9, "author": "secret",
                                                           "replies": {"data": {"children": [{"kind": "t1", "data": {"body": "[deleted]"}}]}}}}]}}]
    monkeypatch.setattr(S, "_reddit_json", lambda path, params: (data, ""))
    out = research.read_thread("https://www.reddit.com/r/eldercare/comments/abc123/title/")
    assert out["source"] == "reddit" and [c["text"] for c in out["comments"]] == ["I would pay for this"]
    assert "secret" not in str(out)


def test_server_registers_read_thread_and_instructions():
    import asyncio, server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "read_thread" in names and "not a web search" in server.INSTRUCTIONS


def test_suggested_searches_do_not_overlap():
    moves = X.next_moves(VIEWS, [], ["assisted living", "living facility", "hospice paperwork"], [], [], "elder care", "policy")
    queries = [m["args"]["query"] for m in moves if m["tool"] == "search_pain"]
    assert queries == ["assisted living", "hospice paperwork"]


def test_a_recommendation_is_not_a_request_for_one():
    assert not X.comment_flags("I recommend the paper version, it works fine")["asks_for_solution"]
    assert X.comment_flags("Can anyone recommend a tool for this?")["asks_for_solution"]
