# Smart Cache Layer — Activity Submission

**Team:** _Joseph Boussamba, Angel Kibui, Lydivine Umutesi, Erick Kanja_

**Team Participation Task sheet:** _[Click here](https://docs.google.com/spreadsheets/d/1SRQx7vBHtfFNu0qXp3XI4FxSLcxLQLM0TGdpj8Hr2ds/edit?usp=sharing)_

---

## Level 1 — Baseline

| Endpoint | First Request | Average |
| --- | --- | --- |
| All Posts | 74.3 ms | 47.0 ms |
| Single Post | 0.3 ms | 0.22 ms |

---

## Level 2 — Discussion

**What cache key did you choose for the list endpoint? Did a classmate choose the same?**

We used a single fixed key (`posts:list`). The response does not vary per request — `/api/posts/` returns every published post, identical for every caller — so one stored copy serves everyone, which gives the best possible hit rate.

The detail endpoint is different: its response depends on which post was requested, so the post id goes into the key.

Classmates chose different strings — `posts:list`, `all_posts`, `posts:published` — and all work. The spelling doesn't matter. What matters is that the key is identical everywhere the endpoint is read or invalidated, and that it captures everything the response varies by. A key that's merely different is fine; a key missing a dimension the response depends on is a bug.

---

## Bug Report — `BrokenDraftsView`

**1. What is the bug?**

The cache key is a fixed string with no user component, so every authenticated caller reads and writes the same entry. The queryset underneath is correct — it filters by `request.user` — but that filtering only runs on a cache miss. On a hit the view returns stored data and never reaches the query.

**2. Walk through the scenario.**

1. **Alice calls the endpoint.** Cache miss. The view queries the database filtered to alice, stores her drafts under the shared key, returns them. Nothing looks wrong.
2. **Bob calls the endpoint.** Cache hit. `cache.get()` returns alice's drafts and the view returns immediately — no database query, and `request.user` is never consulted. **Bob receives alice's drafts.**

Whoever calls first poisons the entry for everyone else until the TTL expires.

**3. Real-world impact?**

Unpublished private content served to the wrong authenticated user. Three things make it worse than a typical bug:

- **Non-deterministic** — who leaks to whom depends on request ordering, so it won't reproduce reliably.
- **Passes testing** — single-user tests all succeed. It needs concurrent multi-user traffic to surface.
- **No audit trail** — it's a read leak. Nothing is modified, nothing is logged, and the only signal is a user noticing unfamiliar content.

Under GDPR and POPIA it is reportable unauthorised disclosure of personal data.

**4. One-line fix?**

```python
cache_key = f"drafts:user:{request.user.id}"
```

---

## Level 4 — Discussion

**`cache.delete()` vs updating the cache directly. When would you choose each?**

Delete removes the entry and lets the next reader rebuild it from the database. Writing through puts fresh data in place, so no reader ever misses.

Delete is the safer default: the cache can only hold something the database actually produced. The cost is that the next request pays the full query, and under load several requests can stampede the database together.

Writing through keeps every request fast, but it constructs the cached value outside the read path. Two pieces of code now produce what should be the same thing, and the moment they drift the cache holds something that was never true — silent, and persisting for the full TTL.

Delete by default. Write through only for keys hot enough that the recompute genuinely hurts.

---

## Final Results

| Endpoint | Before | After | Improvement |
| --- | --- | --- | --- |
| All Posts | 74.3 ms | 8.2 ms | 88.9 % |
| Single Post | 0.3 ms | 0.02 ms | 93.3 % |

The first request stays near baseline — still a miss, still paying the database query — while the average drops sharply because every subsequent request is served from memory. That gap is cache-aside working: the cost is paid once and amortised across everything after it.

---

## Reflection Questions

**1. Why a shared key for `/api/posts/` but a user-specific key for `/my-drafts/`?**

Because of what the response depends on. `/api/posts/` returns the same bytes to every caller, so identity isn't an input and one copy serves everyone — adding the user would fragment one entry into one-per-user and collapse the hit rate for no gain. `/my-drafts/` returns posts belonging to the requester, so identity is an input to the response and must be an input to the key.

The rule: the key must capture every variable the response depends on. Miss one and you serve one variant's data for another's request. When the missing variable is user identity, that's a security bug.

**2. What would happen with `timeout=None` on the post list cache?**

The entry would never expire on its own, so the only thing that could clear it is our explicit `cache.delete()` in `PostListView.post()`. That covers exactly one path. A post edited or deleted, a status flipped, a change through the admin or a management command, or a write added later by someone who doesn't know the key exists — each leaves the cache permanently wrong.

A TTL doesn't prevent staleness, it bounds it. At 300 seconds a missed invalidation is wrong for five minutes; at `None` it's wrong until the process restarts. The TTL is a safety net for the invalidation you forgot.

**3. When would caching `/my-drafts/` cause a bug even with the correct key?**

Immediately after the user saves a new draft. The write path doesn't invalidate the drafts key, so their cached list is the one built before the save. They create a draft, land on their drafts page, and it isn't there — as far as they can tell, their work was lost.

This is the most alarming version of a caching bug because it's the user's own data and their own action. Staleness elsewhere is invisible; staleness here looks like data loss. The fix is to invalidate on write:

```python
cache.delete(f"drafts:user:{request.user.id}")
```

on every path that creates, edits or deletes that user's drafts. Caching correctness depends on invalidating on every write path, not just the one you thought of.

---
