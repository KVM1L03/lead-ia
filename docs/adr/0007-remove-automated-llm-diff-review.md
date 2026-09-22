# Drop the automated LLM diff review from CI

The `llm-review.yml` workflow ran on every PR open/reopen: it sent the backend diff
(`ai_worker/`, `api_gateway/`, `maps_bridge/`, `shared/`, tests excluded) to Claude Haiku
using `.github/prompts/llm-review-prompt.txt` and posted a comment with a verdict —
`APPROVE | NEEDS CHANGES | BLOCKING ISSUE`. It was advisory only: it never blocked merge,
and required status checks stayed `python` + `frontend`.

In practice it added little signal beyond what human review and the `python`/`frontend`
CI checks already caught, and it occasionally mis-read a diff — flagging invariant
violations that weren't there, or missing ones that were, on hunks it saw out of the
context of the full file. Once that happens a few times the comment stops being useful:
it either gets skimmed and ignored (defeating the point of having it) or it costs real
review time to double-check against the actual diff. A backend diff >400 lines also
skipped the review outright with no fallback, so it wasn't even consistently present.

Removed:
- `.github/workflows/llm-review.yml`
- `.github/prompts/llm-review-prompt.txt`

PRs now rely on `python` + `frontend` CI (lint, types, tests) plus a human reviewer for
everything the automated pass used to advise on, including the architecture invariants
in `AGENTS.md` §4 — those stay listed in the PR template checklist, just checked by a
person instead of a first LLM pass. `mattpocock-skills:code-review` (`AGENTS.md` §6) is
still available for a PR author to self-review a diff before requesting human review; the
difference is it's opt-in and run by whoever is accountable for reading its output, not an
unconditional CI step whose verdict shows up unprompted on every PR.

If a similar check is reintroduced later, it should be evaluated against a concrete
false-positive/false-negative rate on this repo's own PR history, not re-added on the
assumption that an LLM pass is free signal.
