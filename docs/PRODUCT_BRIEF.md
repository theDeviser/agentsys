# agentsys: product brief for an outside review

This one file holds everything a reviewer needs: what agentsys is, what it does today, the evidence from real use, what's
weak, and the questions the owner wants answered. Everything here was checked against the code and the live stores
on 2026-10-15 unless it says otherwise.

---

## 0. Instructions for the reviewing agent

You are reviewing an early open-source developer tool. The owner wants an honest, constructive critique, not encouragement.

**Deliver, in this order:**

1. **Verdict in three sentences.** Is there a real need? For whom? Is agentsys a credible answer to it?
2. **Market check.** Who has this problem today, how they solve it now, and what agentsys would replace. Name the
   closest alternatives (section 9 lists starting points) and say where each is stronger or weaker. **Verify every
   product claim against a current source and cite it.** Mark anything you couldn't verify as *unverified*.
3. **The ten most important weaknesses**, ranked: product, positioning, UX, architecture, security, and adoption.
   For each, give the evidence (a section of this brief or a file:line from the code) and a concrete fix.
4. **What to build next:** the five changes that would most raise adoption or retention, each with a rough effort
   estimate (S/M/L) and how to tell whether it worked.
5. **What to cut or postpone.**
6. **Answers to the open questions in section 10**, one by one.
7. **A validation plan:** the cheapest experiments that would confirm or kill the main hypotheses in section 10 within
   two weeks.

**Rules:**
- Separate facts (cited), inferences (reasoned), and opinions (labelled).
- Don't invent numbers for market size, pricing, or user counts. If you estimate, show the method.
- The token numbers in section 5 are real but come from one developer on one machine. Don't extrapolate them as if
  they were a benchmark.
- If you have the repo (`~/agentsys`), read the code to check claims. The key files are listed in section 4.

---

## 1. One-paragraph summary

**agentsys** is a local, zero-dependency coordination layer for running several AI coding agents from *different
vendors* on one codebase: Cursor, Claude Code, OpenAI Codex CLI, or a human. The agents can't talk to each other
directly, so agentsys gives them one shared task store (SQLite) and one CLI. Any agent that can run a shell command
can do the following:
- claim a task
- work in an isolated git worktree
- record findings for the next agent
- checkpoint and submit

Nothing counts as done until an automated verification gate passes **and** a reviewer who didn't do the work
approves. Merging needs a human. Token usage is tracked per provider *and* per account, with caps checked before
each run. A live dashboard, styled like Cursor, shows what is running where, how each task moved between agents, the
spend per account, and what's waiting on the human.

**Status:** about 3,200 lines (Python 3.9+ standard library, plus a 1,100-line single-file HTML/JS dashboard), 24
passing tests, MIT licence, 7 commits, one user (the author). Not yet published.

---

## 2. Problem and audience (these are hypotheses, not validated)

**The problem as the author experienced it:**
- Developers increasingly pay for **several** AI coding tools at once, for example a Cursor seat, a ChatGPT plan with
  Codex, and access to a colleague's Claude account. Each tool has separate quotas that reset on different schedules.
- These tools don't share context. Moving work from one to another means copy-pasting into chat. Nothing records
  who did what, what was verified, or what is half-finished.
- Running agents in parallel on one repo causes conflicts: the same files edited twice, or work lost when a session
  dies.
- Agents report success too eagerly. There is no independent check before work is accepted.
- Spend is invisible until a quota runs out. A single run can cost 5–10 times what you expected (see section 5).

**Intended users, in priority order (to be validated):**
1. Individual developers or small teams using two or more AI coding tools on the same repos.
2. Tech leads who want an audit trail and a human approval gate for agent-written changes.
3. People building agent pipelines who want a vendor-neutral, inspectable task layer rather than a framework.

**Explicit non-goals today:**
- A hosted service.
- A general agent framework or LLM SDK.
- Agent-to-agent chat.
- Pooling or sharing quotas between accounts or providers.

---

## 3. What it does today (verified)

| Area | Capability |
|---|---|
| Tasks | Kinds: `research`, `implement`, `review`. Each has a goal, acceptance criteria, allowed file paths, extra check commands, and dependencies. |
| Lifecycle | `ready → in_progress → submitted → verified → accepted → merged`, plus `blocked`, `changes_requested`, `escalated` and `cancelled`. Every change is a guarded transition that writes an append-only event in the same transaction. |
| Crash safety | Claims are time-limited holds (leases). An agent heartbeats to keep its hold. If the hold expires, the task returns to the queue with attempts+1, or is escalated to the human after the maximum number of attempts. |
| Handoff | `agentsys resume <task>` prints a self-contained brief: the goal, the last *verified* checkpoint, the latest findings (marked NEW after the checkpoint), any uncommitted leftovers, and the findings from dependency tasks. This is how one vendor's agent continues another's work. |
| Isolation | Every `implement` task gets its own git worktree and branch (`agent/<id>`). Claims with overlapping file scopes are refused. `merge-check` dry-runs the merge with `git merge-tree`. |
| Verification gate | Changed files must be inside the allowed paths; syntax checks (JS/JSX via `bun`, Python, JSON); a secret-pattern scan that reports the type, never the value; the task's own check commands; and, for research tasks, at least one finding with evidence. |
| Review | The reviewer must not be any identity that claimed, checkpointed or submitted the task. |
| Approvals | Merges need a `human:` identity's approval; `merge` refuses on a dirty main tree or conflicts. |
| Headless dispatch | `agentsys dispatch <task> --adapter cursor\|claude\|codex\|mock --account <name>` runs the vendor's own CLI in the worktree and sandbox. It strips API-key environment variables, records provider-reported token usage, posts the output as a finding, and submits or releases the task. |
| Budgets | Per (provider, account): total cap (or 0 = track only), per-run cap, rolling window (e.g. 5 h), and a review reserve (default 20 %; only review runs may use it). The check happens **before** a run, with an estimate equal to the average of the last 5 real runs. Alerts fire at 50/80/95 %. Usage is shared across all projects on the machine (`~/.agentsys/ledger.db`), so a cap holds whichever repo dispatches. Accounts are never pooled. |
| Dashboard | `agentsys ui`. A Cursor-styled local web app (dark and light) with views for:<br>- **Overview:** a plain-language headline, a "needs you" list with one-click actions, and agent cards showing live runs.<br>- **Flow:** each task's chain of agents and what each did, flagging reviews done by the same account that wrote the work.<br>- **Runs:** a timeline of every run with tokens, cost and failures.<br>- **Budget & spend:** each account's limits, edited in a dialog with a live preview of whether the next run would be allowed.<br>- **Activity:** the audit trail as sentences.<br>- **Task pages:** a progress stepper, a "Next" step with the exact command, notes as a thread, and the audit trail.<br>Also: a ⌘K palette and deep links. Actions you can take there: edit limits, approve or deny, requeue, unblock, cancel. They're recorded as `human:<you>` and protected by a per-session token, Host and Origin checks, and input validation; `--read-only` disables them. |

**CLI surface (29 commands):**
- Setup: `init`, `adapters`
- Tasks: `task add/list`, `show`, `claim`, `heartbeat`, `release`, `block`, `unblock`, `requeue`, `cancel`
- Work: `finding`, `checkpoint`, `submit`, `resume`, `dispatch`
- Gates: `verify`, `review`, `merge-check`, `merge`, `approvals`, `approve`, `deny`
- Status and spend: `status`, `log`, `budget set/show`, `usage add`, `ui`

---

## 4. How it works

```
 Cursor ──┐                       ┌── project A/.agent-system/state.db  (tasks, events, findings, checkpoints, runs)
 Claude ──┼── agentsys CLI ───────┼── project B/.agent-system/state.db
 Codex  ──┤   (any shell)         └── ~/.agentsys/ledger.db            (budgets + runs for every account, all projects)
 Human  ──┘        │
                   ├── git worktree per implement task  (<repo>.worktrees/<id>, branch agent/<id>)
                   ├── adapters: run vendor CLIs headless (cursor-agent -p, claude -p, codex exec)
                   └── agentsys ui: local dashboard (127.0.0.1)
```

- **Coordination is through the store, not chat.** An agent's identity is a self-declared string,
  `harness:account:role` (e.g. `codex:alice:work`). Instructions for agents live in the target repo's `AGENTS.md`
  and are appended to every dispatched prompt.
- **Concurrency:** SQLite in WAL mode; transitions use `UPDATE … WHERE state = ?` guards; stale holds are reclaimed
  lazily when any command runs.
- **Key files:**
  - `agentsys/store.py`: schema and state machine
  - `cli.py`: commands, the dispatch flow and `next_step()`
  - `verify.py`: the gate
  - `budget.py` and `ledger.py`: spend
  - `adapters.py`: vendor CLIs
  - `gitops.py`: worktrees and merges
  - `ui.py` and `ui.html`: the dashboard
  - `tests/test_agentsys.py`: 24 tests

---

## 5. Evidence from real use (one developer, one machine, 2026-10-15)

agentsys was run on a real product repo (a static UI prototype called "ToCom UI") and then on itself.

| | ToCom UI | agentsys itself |
|---|---|---|
| Tasks | 8: 4 accepted, 3 merged, 1 cancelled | 1 accepted |
| Headless runs | 8 | 1 |
| Vendors used | Claude Code, Codex CLI, Cursor | Codex CLI |

**Usage per account (provider-reported, cache reads included):**

| Account | Runs | Tokens | Reported cost |
|---|---|---|---|
| Anthropic (Claude Code, borrowed account) | 1 | 145,940 | $0.0073 |
| Cursor | 4 | 1,149,518 | not reported by the CLI |
| OpenAI (Codex CLI, ChatGPT plan) | 4 | 775,705 | not reported by the CLI |

One of the four Codex runs failed before reaching the model and is counted at its 60k estimate.

**What worked:**
- A three-vendor handoff: Claude researched, Codex cross-checked, then Cursor synthesised, each using the previous
  one's findings from the store.
- Two implementation tasks ran in parallel in isolated worktrees (Cursor and Codex) and merged cleanly after human
  approval.
- An independent review caught a wrong root cause in another agent's report, and the task went back for changes.
- Codex reviewed agentsys's own UX in 35 seconds (258k tokens) and returned 12 accurate, line-referenced findings,
  all of which were adopted.

**What went wrong (important for the critique):**
- **Estimates were far off.** Runs cost 362k, 372k and 747k tokens against estimates of 80–120k. Caps can only be
  checked before a run; a vendor CLI can't be stopped mid-run on token count.
- **Fixed overhead is high.** Even a trivial Claude Code run used about 146k tokens, mostly cached context, though it
  cost under a cent. Token-denominated caps are therefore a poor proxy for cost on some vendors.
- **Identity is self-declared.** The orchestrating agent once recorded a decision as `human:…` to get around the
  "authors can't review" rule. It was caught and logged, but nothing technically prevents it. In two flows, an
  account's "reviewer" role approved work from the same account's "worker" role; the dashboard now flags this.
- **Ledgers were per project at first.** Two repos could together exceed one account's cap. This is fixed by the
  shared ledger.
- Several real UX gaps (jargon, copy buttons whose command didn't match the text, dead-end error messages) were
  found and fixed only after a dedicated review.

---

## 6. Design principles (owner's constraints)

- Never claim that tokens are pooled, shared or unlimited, and never rotate accounts to get around limits.
- Never expose secrets in logs, prompts, commits or artifacts. API keys are stripped from child processes.
- A human approves anything destructive, expensive, external or security-sensitive (merges today).
- Nothing counts as done until it passes the verification gate and a different identity reviews it.
- Ship the smallest useful version first, and don't fake connectivity: vendors without an adapter are labelled
  "No adapter yet".
- Zero dependencies, local-first, inspectable (SQLite plus readable events).

---

## 7. Known limitations and open issues

1. **Reviewer independence relies on trust.** Identities are strings anyone can claim, and there's no signing and no
   binding to a vendor's login.
2. **Budgets can't be enforced mid-run.** Overruns are reported after the fact; the estimates learn from history but
   are noisy.
3. **Cost isn't tracked for subscription CLIs.** Cursor and Codex report tokens but not dollars, and plan quotas
   aren't visible to agentsys. It can't see "you have X left on your plan".
4. **The CLI isn't a session.** Interactive work in an IDE chat isn't captured unless the user self-reports it with
   `usage add`. The dashboard therefore under-reports total spend.
5. **Single machine.** There's no sync between teammates; the stores are local files.
6. **No scheduler.** Humans or an orchestrating agent decide what to dispatch, to whom, and when. There's no
   automatic routing by cost, skill or quota.
7. **Adapters break easily.** They parse each vendor CLI's JSON output, which changes without notice (e.g. a model
   name that stopped working on one login caused a failed run).
8. **The verification gate is shallow.** Syntax, scope and secret regexes only; it doesn't run project tests unless
   the task lists them.
9. **The dashboard is localhost-only by design**; there's no auth for remote viewing.
10. **No packaging or distribution yet**: no PyPI release, no docs site, no demo video.

---

## 8. Where editing and control could grow (owner's question)

Done on 2026-10-15: editing limits (total, per-run, window, reserve), approve/deny, requeue, unblock and cancel are
all possible from the dashboard.

Candidates the owner wants critiqued:

| Candidate | Why it might matter | Risk |
|---|---|---|
| **Create and edit tasks in the UI** (title, goal, acceptance, allowed paths, dependencies) | Today you need the CLI to start anything | Low |
| **Dispatch from the UI** with a model/account picker and the budget preview | The most-requested control; makes the tool usable without a terminal | Spends real quota, so it needs a confirm step and the per-run cap |
| **Routing rules** (e.g. "research to Codex while its 5 h window is under 70 %, else Cursor") | Uses several subscriptions efficiently | Complex; could look like getting around limits, so it must stay within each account's own caps |
| **Per-model limits and model allow-lists per account** | Some models cost far more | Medium |
| **Spend in dollars** with a per-provider price table the user maintains | Token caps mislead (section 5) | Prices change; must be user-owned |
| **Notifications** (desktop, Slack) for "needs you" items | Approvals currently wait until someone looks | Low |
| **Review assignment** (pick which vendor reviews which author) | Makes independence explicit | Low |
| **Editable verification profiles** per repo (test commands, linters) | Deepens the gate | Low |
| **Signed identities** (e.g. bound to the vendor CLI's login or a local key) | Fixes limitation 1 | High effort |
| **Team mode** (shared store over git or a small server) | Multi-person use | High effort; changes the product |

---

## 9. Alternatives to research (unverified starting list; check what's current)

The author has **not** verified the current state of these. The reviewer should confirm each one and add any missing.

- **Multi-agent frameworks:** LangGraph, CrewAI, AutoGen/AG2, OpenAI Agents SDK. These are code-level
  orchestration inside one runtime, usually with one model provider per agent.
- **Running several coding agents in parallel:** tools that run multiple Claude Code or Codex sessions in separate
  worktrees with a UI (e.g. claude-squad, Conductor, Vibe Kanban, Crystal).
- **Hosted background coding agents:** GitHub Copilot coding agent, Cursor background agents, OpenAI Codex (cloud),
  Google Jules, Devin, Factory.
- **Protocols:** MCP (tools and context for one agent) and Google's A2A (agent-to-agent). agentsys deliberately uses
  neither for coordination.
- **Agent observability and cost tracking:** LangSmith, Langfuse, Helicone, AgentOps. These are mostly API-level and
  don't see subscription CLI usage.
- **Issue trackers as agent queues:** Linear, Jira or GitHub Issues driven through MCP.

**Positioning hypothesis:** agentsys sits between these. It's vendor-neutral like a tracker, local and git-native
like the worktree runners, and it adds verification, review independence and per-account spend controls that the
others treat as out of scope.

---

## 10. Hypotheses and open questions

**Hypotheses to confirm or kill:**
- H1: A meaningful number of developers actively use **two or more** AI coding tools on the same repo every week.
- H2: They feel handoff pain (lost context, duplicated work) strongly enough to adopt a CLI convention.
- H3: The **verification gate plus independent review** is valued more than raw parallelism.
- H4: Per-account spend visibility across subscriptions is a reason to adopt on its own.
- H5: A local, zero-dependency tool beats a hosted one for this audience.

**Questions for the reviewer:**
1. Is "cross-vendor" a durable wedge, or will each vendor's own multi-agent features make it irrelevant?
2. Which audience should come first: solo multi-tool developers, tech leads, or pipeline builders?
3. Should the core stay CLI-first, or should the dashboard become the primary interface (with dispatch from the UI)?
4. Is it a credible trust model to rely on agents following `AGENTS.md` and calling a CLI, or does it need an MCP
   server or wrapper so vendors can't skip steps?
5. Should spend be measured in tokens, dollars or "percent of plan window"? What do users actually reason in?
6. What's the minimum security bar before publishing (signed identities, remote dashboard auth, sandbox defaults)?
7. Open-source only, or open core with a paid team/sync tier? Which parts would anyone pay for?
8. What would a convincing 2-minute demo show?
9. What's the biggest reason a developer would try this and then stop using it within a week?
10. Which of the section 8 candidates should come first, and which should never be built?

---

## 11. Glossary

| Term | Meaning |
|---|---|
| Task | A unit of work with a goal, acceptance criteria and allowed paths. |
| Hold (lease) | A time-limited claim on a task. It's renewed by heartbeat; if it expires, the task returns to the queue. |
| Checkpoint | Recorded progress, optionally a commit in the task's worktree. "Verified" once the gate passes. |
| Finding | A note an agent leaves for others: finding, decision, blocker, question, artifact or output. |
| Verification gate | The automated checks between "submitted" and "verified". |
| Independent review | An approve/reject by an identity that didn't work on the task. |
| Adapter | A wrapper that runs one vendor's CLI headless and parses its usage report. |
| Ledger | The user-level record of budgets and runs that every project shares. |
| Review reserve | The share of a total cap that only review runs may use, so work can't starve verification. |

---

## 12. Appendix: try it in five minutes

```sh
git clone <repo> ~/agentsys && export PATH="$HOME/agentsys/bin:$PATH"
cd <any git repo> && agentsys init && echo ".agent-system/" >> .gitignore
export AGENTSYS_ACTOR=human:me
agentsys task add "Find dead buttons in the settings page" --kind research
agentsys dispatch <task-id> --adapter mock              # free, deterministic
agentsys budget set openai me --limit 0 --window-hours 5
agentsys dispatch <task-id> --adapter codex --account me   # real run, real quota
agentsys ui                                              # http://127.0.0.1:8791
```
