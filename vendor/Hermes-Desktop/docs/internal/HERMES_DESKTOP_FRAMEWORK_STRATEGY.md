# Hermes Desktop — Native Windows Agentic Framework
## Internal implementation strategy (refocused)

---

## 1. Executive refocus decision

**Decision:** Hermes Desktop is refocused to be a **native Windows agentic framework and product**, not a downstream reimplementation of upstream Hermes.

**Facts we accept:**

- Upstream Hermes bundles **multiple products** (TUI, gateway/server, Python runtime ecosystem). Those are **different form factors and lifetimes** than a WinUI desktop app.
- **Broad feature parity** with upstream would be an open-ended grind, would distort priorities, and would trade away the one asset that cannot be copied from Python: **a coherent Windows-native runtime and UX**.

**What we optimize for instead:**

- **Windows runtime correctness** — tool loops, permissions, transcripts, providers, failure modes.
- **Trust** — secrets, persistence, deterministic behavior where the user depends on it.
- **Native desktop UX** — surfaces that make agentic work legible and controllable on Windows (sessions, replay, skills, soul, settings, files/tasks/diffs).

**What we explicitly stop doing:**

- Treating upstream Hermes as a **checklist to complete**.
- Letting **gateway/server** concerns define the architecture of the desktop framework.

**Non-goals:** Winning a race to "most tools" or "most parity badges." **Goals:** a **solid, trustworthy Windows agentic framework** that teams can extend without fighting the shell.

This is a **product and architecture decision**, not a preference. Execution, staffing, and backlog should align to it.

---

## 2. Product boundary definition

### What Hermes Desktop is

| Layer | Role |
|--------|------|
| **Agent runtime** | In-process agent (`Agent`, tool registry, tool-calling loop, streaming and non-streaming paths, provider integration). |
| **Control plane** | Configuration, permissions, session lifecycle, profiles/soul, provider credentials — **user-owned** desktop semantics. |
| **UX / product** | WinUI surfaces: chat, skills, memory, sessions, replay, activity, settings, file/task/diff presentation. |
| **Framework** | Extension points: tools, plugins, context/memory, skills — **Windows-first** contracts. |

### What Hermes Desktop is not

| Anti-pattern | Why it fails |
|--------------|--------------|
| **Full upstream clone** | Divergent constraints; endless parity chase; you ship imitation, not product. |
| **Primary gateway/server product** | Wrong lifetime, wrong failure modes, wrong update model; belongs in a **sidecar** or separate service. |
| **TUI replacement** | Desktop UX is the differentiator; terminal parity is a distraction. |
| **Feature dumping ground** | Every upstream feature must **earn its place** in the Windows framework. |

### When to borrow from upstream

Translate or port **only** when:

- It strengthens **runtime invariants** (e.g. proven tool semantics, safety patterns).
- It strengthens **Windows UX** (e.g. workflows that map to session/replay/diff surfaces).
- It is a **small, bounded** extract — not "bring the whole Python subsystem."

If the only reason is "upstream has it," **defer or reject.**

---

## 3. Windows-first strategy

**Question:** How does this become excellent **as a Windows agentic framework on its own terms?**

### Runtime architecture

- **Single coherent agent core** (C#): one tool loop, one permission model, one transcript story. Avoid parallel "special" paths that behave differently under stress.
- **Explicit provider model:** primary + fallback ([`agent.cs`](../../src/Core/agent.cs) already encodes fallback state); every failure mode must be **observable** (logs + UI where appropriate), not silent degradation.
- **Context vs archive:** [`ContextManager`](../../src/Context/ContextManager.cs) models transcript as archive + selective recall — keep this distinction sharp; don't blur "what's on disk" with "what's in the prompt."

### Desktop UX architecture

- **Pages map to mental models:** Chat (work), Sessions (structure), Replay/Activity (audit), Skills (capabilities), Memory (long-term), Settings (trust and cost), Agent/Soul (identity). Existing XAML layout under [`Desktop/HermesDesktop/Views/`](../../Desktop/HermesDesktop/Views/) should stay **task-centered**, not "settings for everything."
- **Tool use must be legible:** tool cards, approvals, streaming text — users must see **what ran** and **what changed** (foundation for Wave B diffs).

### Tool model

- **Register tools with clear contracts:** read-only vs mutating, parallel-safe vs serial (see `ParallelSafeTools` in agent).
- **Framework rule:** every new tool pays for **permission coverage**, **secret scanning on outputs**, and **transcript fidelity** — or it doesn't ship.

### Session model

- Sessions are the **unit of work** on desktop: branch conversations, resume, export. Tie UI ([`SessionPanel`](../../Desktop/HermesDesktop/Views/Panels/SessionPanel.xaml)) to transcript IDs and persistence guarantees.

### Identity / soul / profile

- **SoulService** and agent profiles are part of **product identity**, not cosmetic. Workflows: default persona, per-task overrides, clarity in prompts vs UI.

### Observability and replay

- **ReplayPanel / activity** are first-class: they turn the runtime into something **reviewable** — critical for trust and debugging without reading JSONL by hand.

### File, task, diff surfaces

- **Framework goal:** first-class presentation of artifacts (paths, patches, task state) in Windows-native controls — not dumping raw strings into chat forever. Inline diff previews (Wave B) are the natural compression of this.

### Settings and configuration

- Visual, searchable, safe: providers, keys (secure storage), feature flags, sidecar paths — **control plane** clarity.

### Extension points

- **Tools, plugins, memory providers, skills** — each should be **interface-driven** so Wave A (pluggable memory) and Wave C (one heavy capability) don't become one-off hacks.

---

## 4. Wave-based delivery plan

### Immediate

| | |
|--|--|
| **Goal** | Prove **Anthropic** tool-calling **in the real app**: multi-step tool loop, visible tool execution, sane final answer. |
| **Why** | If this is broken, nothing else matters; it's the proof the runtime is real. |
| **Deliverables** | Manual E2E script + captured evidence (session id, transcript snippet, screenshot or log); fix regressions in [`HermesChatService`](../../Desktop/HermesDesktop/Services/HermesChatService.cs) / [`AnthropicClient`](../../src/LLM/AnthropicClient.cs) / [`Agent`](../../src/Core/agent.cs) as needed. |
| **Risks** | Passing only `CompleteAsync` health checks while tool path fails; streaming vs non-streaming divergence. |
| **Verification gate** | At least one conversation where **multiple tool rounds** occur **or** tool + final text in one turn with correct transcript ordering. |
| **Defer** | New tools, gateway work, UX polish beyond blocking bugs. |

### Wave A — Trust, hardening, core runtime integrity

| | |
|--|--|
| **Goal** | Make the runtime **hard to misuse and hard to betray the user** — secrets, memory, transcripts, permissions, providers, persistence. |
| **Why** | Trust beats features; silent failure is worse than missing features. |
| **Deliverables** | (1) **Secret exfiltration blocking** — extend [`SecretScanner`](../../src/security/SecretScanner.cs) coverage on **all** tool output paths and high-risk tools (not only agent core). (2) **Pluggable memory providers** — `IMemory`-style abstraction + built-in default; Memory UI wired to selection. (3) **Transcript integrity** — after tool loops, crash mid-write, reordering; assert JSONL ordering matches in-memory. (4) **Streaming vs non-streaming audit** — document and test parity for tool turns (`CompleteWithToolsAsync` vs stream final). (5) **Permission consistency** — same rules for `ChatAsync` and `StreamChatAsync`. (6) **Provider fallback** — deterministic transitions, user-visible state when on fallback. (7) **Persistence safety** — atomic writes ([`TranscriptStore`](../../src/transcript/transcriptstore.cs)), eager flush where needed. (8) **Deterministic IDs** — tool call id normalization already present; verify cross-provider. |
| **Risks** | Over-blocking (false positives on SecretScanner); memory provider interface churn. |
| **Verification gate** | Scripted failure injection (see section 5); checklist sign-off; no P0 open items on trust paths. |
| **Defer** | Smart routing, heavy multimodal, gateway features. |

### Wave B — High-leverage Windows UX

| | |
|--|--|
| **Goal** | Reduce cost and increase clarity for daily use. |
| **Why** | UX is the moat; routing and diffs are **multiplicative** on the same runtime. |
| **Deliverables** | **Smart model routing** (task classification -> cheaper/faster model with safe fallbacks). **Inline diff previews** in chat (patch-aware control, link to file/session). |
| **Risks** | Routing misclassification -> wrong model -> bad output; diff UI performance on large patches. |
| **Verification gate** | Routing metrics or logs; diff preview on representative edits without UI freeze. |
| **Defer** | Additional heavy tools beyond Wave C choice. |

### Wave C — Selective capability expansion

| | |
|--|--|
| **Goal** | Add **one or two** expensive capabilities that desktop users actually use — not a zoo. |
| **Why** | Browser and vision are **maintenance and security liabilities**; pick deliberately. |
| **Deliverables** | Choose **e.g. browser automation OR vision** with explicit **Windows workflow** justification (e.g. "review web + capture for task" vs "screenshot understanding"). Integrate through the same permission + secret + transcript stack. |
| **Risks** | Supply-chain and sandbox boundaries for browser; token cost for vision. |
| **Verification gate** | Threat-minimal default; opt-in; clear kill switch; cost visible in settings or activity. |
| **Defer** | The capability you didn't pick; parity with any upstream mega-tool list. |

### Wave D — Sidecar integration without product drift

| | |
|--|--|
| **Goal** | **Gateway in its lane:** configure, launch, health, logs — **not** the core runtime. |
| **Why** | Server processes must not dictate desktop architecture. |
| **Deliverables** | Settings entries: path, env, start/stop, status. Optional deep link to logs. **No** embedding long-running gateway **inside** the GUI process. |
| **Risks** | UX that implies "this app is the gateway" — wrong mental model. |
| **Verification gate** | With gateway off, desktop agent still fully usable; with gateway on, clear isolated status. |
| **Defer** | Feature parity with upstream gateway plugins until desktop core is stable. |

---

## 5. Behavioral hardening audit (Windows runtime)

Use this as a **release gate** for Wave A and after any provider/tool loop change.

| Item | Risk | Proof required | Likely production failure mode |
|------|------|----------------|--------------------------------|
| **Compression / context pressure** | Silent truncation, wrong summary, lost tool context | Stress long sessions; verify eviction + summary path; compare tool results before/after compression | Wrong answers; tool arguments built from stale context |
| **Provider fallback** | Stuck on fallback, double billing, wrong endpoint | Inject primary failure; verify recovery interval and user-visible state | Hidden degraded quality; runaway retries |
| **Transcript integrity after tool loops** | Disk != memory; partial writes | Kill process mid-tool-batch; reopen session | Lost messages, duplicate tool ids, corrupt resume |
| **Secret redaction** | Leak via tool output, logs, UI copy | Fuzz secrets in tool returns; grep UI clipboard paths | API keys in screenshots, chat, or exported JSONL |
| **Streaming vs non-streaming** | Different tool behavior, missing saves | Same prompt via both paths; diff transcript | Missing assistant/tool messages in one mode |
| **Permission prompts** | Inconsistent approve/deny between paths | Matrix: stream/non-stream, parallel tools | Unauthorized writes despite UI expectation |
| **Deterministic IDs** | Broken tool_result pairing | Multi-tool turns; provider quirks | Orphan results, retries, hallucinated "success" |
| **Persistence** | Corruption, ordering | Power loss simulation; `HERMES_EAGER_FLUSH` testing | Truncated JSONL, unrecoverable sessions |

---

## 6. Recommended architecture rules (compact)

1. **Windows-first:** Every subsystem must justify itself for **desktop agent workflows**, not for upstream symmetry.
2. **Harden before expand:** No new surface area until Wave A gates pass for adjacent paths.
3. **No blind parity:** Upstream is **reference**, not **spec**.
4. **Sidecar for server lifetimes:** Gateway, long bots, always-on listeners — **out of process**.
5. **One agent loop semantics:** Streaming and blocking paths must not diverge in **permissions, transcripts, or security**.
6. **Trust path completeness:** Tool output -> SecretScanner -> transcript -> UI; gaps are **P0**.
7. **Coherence over sprawl:** Prefer one excellent diff/session story over three half-baked integrations.
8. **Observable failure:** Silent degradation is a bug; user or operator must be able to see **degraded mode**.

---

## 7. Implementation backlog (builder-ready)

| Priority | Task | Subsystem | Reason | Dependency | Verification |
|----------|------|-----------|--------|------------|--------------|
| P0 | E2E Anthropic multi-turn tool conversation in shipping UI | Desktop + Agent + LLM | Confirms core product works | Valid API key, network | Manual script + transcript evidence |
| P0 | Streaming vs non-streaming parity audit (tool turns) | Agent, HermesChatService | Prevents split-brain bugs | Immediate E2E | Automated or scripted dual-path test |
| P0 | Extend SecretScanner coverage to all tool egress | Tools + SecretScanner | Trust | None | Unit tests + manual leak attempts |
| P1 | Pluggable memory provider interface + UI | MemoryManager, Memory page | Wave A requirement | Transcript/session stable | Swap provider in settings; reload session |
| P1 | Permission matrix test (stream/blocking x tools) | Permissions + Agent | Consistency | E2E path | Checklist + optional UI test |
| P1 | Transcript corruption / crash tests | TranscriptStore | Data integrity | None | Kill process tests |
| P2 | Smart model routing | LLM + routing policy | Cost/latency | Wave A trust stable | Metrics + mis-route rollback |
| P2 | Inline diff preview in chat | WinUI + chat controls | UX moat | CodeBlock/tool views | Large patch perf test |
| P3 | Pick 1 heavy capability (browser or vision) | Tools + sandbox policy | Controlled expansion | Wave B partial | Security review gate |
| P3 | Gateway sidecar settings (start/stop/config) | Settings + optional process host | Wave D | Desktop agent standalone | Gateway off = full local use |

---

## 8. Final recommendation

**Proceed for the next several cycles as follows:**

1. **Stop** measuring success by upstream coverage. **Start** measuring by **E2E agent reliability on Windows** and **UX clarity** for sessions, tools, and replay.
2. **Ship Immediate first:** a real Anthropic tool-calling conversation in the **actual app**, with evidence. Until that holds, defer Wave B/C/D scope except blocking fixes.
3. **Invest Wave A heavily** — secrets, memory providers, transcript and permission parity, provider fallback. This is the **bar** for calling the framework "production-grade."
4. **Use Wave B** for leverage (routing + diffs), not for more tools.
5. **Use Wave C** as a **deliberate bet** (one or two capabilities), with security and cost gates.
6. **Use Wave D** to keep the gateway **peripheral** — configured and visible, never the spine of the desktop architecture.

**Outcome to hold the team accountable to:**
Hermes Desktop is a **solid, trustworthy, Windows-native agentic framework and desktop product**: strong runtime foundations, strong native UX, and **no trap of upstream imitation.**
