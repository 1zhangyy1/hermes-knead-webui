# Implementation Reference: Upstream Source Mapping

Maps each missing feature to its upstream source file, key patterns, and C# port strategy.

## Phase 1: Architecture

### 1.1 Plugin System
**Upstream**: `agent/memory_manager.py`
**Key patterns**:
- `IMemoryProvider` interface with 12 lifecycle hooks: `system_prompt_block()`, `prefetch()`, `queue_prefetch()`, `sync_turn()`, `get_tool_schemas()`, `handle_tool_call()`, `on_turn_start()`, `on_session_end()`, `on_pre_compress()`, `on_memory_write()`, `on_delegation()`, `initialize()`, `shutdown()`
- Single external provider constraint (max 1 non-builtin)
- Tool routing via `_tool_to_provider` dict
- Failure isolation: exceptions per-provider never block others
- Context fencing: memory recalls wrapped in `<memory-context>` tags
**C# port**: `src/plugins/IPlugin.cs`, `PluginManager.cs`. Use `ConcurrentDictionary<string, IPlugin>` for registry. Each hook is an `async Task` method on the interface. Use try/catch per-plugin in dispatch.

### 1.2 Gateway Backend
**Upstream**: `gateway/run.py` (GatewayRunner class, ~1500 lines)
**Key patterns**:
- `GatewayRunner` orchestrates `Dict[Platform, BasePlatformAdapter]`
- `BasePlatformAdapter` interface: `connect()`, `send()`, `disconnect()`, `set_message_handler()`, `set_fatal_error_handler()`
- `MessageEvent` object: text, message_type, source, media_urls, media_types, message_id
- Session key encoding: platform + chat_id + user grouping policy
- Multi-tier authorization: platform exemptions → allow-all flags → pairing store → platform allowlists → global allowlist
- Stale agent detection with wall-clock + idle-time checks
- Failed platform recovery: exponential backoff (30s → 300s cap, max 20 retries)
- Background watchers: session expiry flusher (5 min), platform reconnect watcher
- 40+ built-in slash commands dispatched from `_handle_message()`
- Agent cache for prefix cache preservation across turns
- Pending approval queue for gateway async approval
- Shutdown: interrupt all agents, disconnect adapters, persist state
**C# port**: `src/gateway/GatewayService.cs`, `src/gateway/IPlatformAdapter.cs`, `src/gateway/platforms/TelegramAdapter.cs` etc. Use `BackgroundService` for the runner. Wire to existing IntegrationsPage config.

### 1.3 Execution Backends
**Upstream**: `tools/terminal_tool.py` + `tools/environments/` (6 backends)
**Key patterns**:
- `_create_environment()` factory dispatches on `TERMINAL_ENV` env var
- Backends: Local, Docker, Singularity, SSH, Modal, ManagedModal, Daytona
- Each backend implements: execute command, get output, cleanup
- Output truncation: 50K chars, 40% head + 60% tail split
- ANSI stripping + secret redaction on all output
- Exit code interpretation (grep=1 not error, diff=1 not error)
- Workdir validation: strict `[A-Za-z0-9/_\-.~ +@=,]` allowlist
- Sudo handling: `sudo -S -p ''` transformation with password piping
- Per-task environment caching with inactivity cleanup (300s default)
- Background process support via `process_registry.spawn_local()`
**C# port**: Extend existing `AgentService` isolation enum. Add `DockerIsolation`, `DaytonaIsolation` strategies. Use `Process` class with timeout.

## Phase 2: Core Intelligence

### 2.1 Autonomous Skill Creation
**Upstream**: `tools/skill_manager_tool.py`
**Key patterns**:
- 6 actions: create, edit, patch, delete, write_file, remove_file
- Name validation: max 64 chars, `^[a-z0-9][a-z0-9._-]*$`
- Frontmatter validation: requires `---` YAML with `name` and `description`, max 1024 char desc
- Content cap: 100K chars
- Atomic write: `os.mkstemp()` + `os.replace()` (never partial writes)
- Security scan + rollback: saves original, restores on scan failure
- Patch: fuzzy find-and-replace with whitespace normalization
- Supporting files restricted to: `references/`, `templates/`, `scripts/`, `assets/`
- Per-file limit: 1 MiB
- Directory cleanup on delete: removes empty parent categories
**C# port**: Add `CreateSkillAsync()`, `EditSkillAsync()`, `PatchSkillAsync()` to existing `SkillManager`. Atomic write via temp file + `File.Move()`. Security scan via existing `SecretScanner`.

### 2.2 Smart Model Routing
**Upstream**: `agent/smart_model_routing.py`
**Key patterns**:
- 32 complexity keywords: "debug", "implement", "refactor", "exception", "analyze", "architecture", "optimize", "test", "docker", etc.
- Length thresholds: max 160 chars, max 28 words
- Disqualifiers: >1 newline, code blocks (backticks), URLs
- `choose_cheap_model_route()` returns route dict or None
- `resolve_turn_route()` falls back to primary model
- Config-disabled by default
**C# port**: `src/LLM/ModelRouter.cs`. Simple method `ShouldUseCheapModel(string message) -> bool`. Plug into `HermesChatService` before `StreamStructuredAsync`.

### 2.3 Credential Pool Upgrade
**Upstream**: `agent/credential_pool.py`
**Key patterns**:
- 4 strategies: FILL_FIRST (default), ROUND_ROBIN, RANDOM, LEAST_USED
- `PooledCredential` dataclass: provider, id, label, auth_type, access_token, refresh_token, priority, request_count, last_status, error fields, expires_at
- `select()` → `_select_unlocked()` with strategy dispatch
- `mark_exhausted_and_rotate()`: extracts retry delays, parses reset timestamps (epoch, ISO-8601)
- Cooldowns: 1 hour for 429 (rate limit), 24 hours for others
- `_available_entries()` filters out entries still in cooldown
- OAuth refresh per provider (Anthropic, OpenAI Codex, Nous)
- Lease system: `acquire_lease()` / `release_lease()` with soft cap (`_max_concurrent` = 1)
- Persistence: write to auth.json on every state change
- Seeding: from env vars, credentials files, config.yaml custom_providers
**C# port**: Extend existing `CredentialPool.cs`. Add `SelectionStrategy` enum, `Lease` tracking, `ExhaustionState` with cooldown math. Keep existing rotation as FILL_FIRST default.

## Phase 3: Heavy Tools

### 3.1 Browser Tool
**Upstream**: `tools/browser_tool.py`
**Key patterns**:
- Accessibility tree via `agent-browser` CLI (not vision)
- Interactive elements get refs: `@e1`, `@e2`
- 3 backend tiers: Local (headless Chromium), Cloud (Browserbase/BrowserUse/Firecrawl), Camofox (anti-detection)
- Command format: `agent-browser [--cdp <url> | --session <name>] --json <command> [args]`
- Actions: navigate, click, type (fill), scroll (5x repeat), press key, eval JS, vision (screenshot + AI)
- SSRF: API key detection in URLs, private address blocking, post-redirect checks, website policy
- Inactivity timeout: 5 min default, background cleanup thread every 30s
- Content extraction: >8K chars → LLM summarization with task context
- Session isolation per task_id, thread-safe via `_cleanup_lock`
**C# port**: `src/Tools/BrowserTool.cs`. Use Playwright for .NET (Microsoft.Playwright). Accessibility tree via `page.Accessibility.SnapshotAsync()`. SSRF via existing validators.

### 3.2 Approval System Enhancement
**Upstream**: `tools/approval.py`
**Key patterns**:
- 30+ dangerous patterns: rm -r /, mkfs, chmod 777, DROP TABLE, curl|sh, fork bombs, etc.
- 3 approval scopes: Once, Session, Always (persisted to config.yaml)
- Smart approval mode: auxiliary LLM risk assessment (APPROVE/DENY/ESCALATE)
- Gateway async path: `threading.Event` per approval, `/approve` `/deny` handlers, 300s timeout
- ANSI stripping, null byte removal, Unicode NFKC normalization (defeats fullwidth obfuscation)
- Tirith static analysis integration
- Session key via ContextVar for thread-safe concurrent gateway
**C# port**: Extend existing `PermissionManager`. Add pattern-based dangerous command detection to `ShellSecurityAnalyzer`. Add approval persistence to config.

## Phase 4: Intelligence Features

### 4.1 Session Search (FTS5)
**Upstream**: `tools/session_search_tool.py`
**Key patterns**:
- SQLite FTS5 full-text search of past sessions
- Boolean search syntax (AND/OR/NOT/phrase)
- LLM-summarized results
- Parallel summarization
**C# port**: Add SQLite FTS5 index via `Microsoft.Data.Sqlite`. Index messages on save in `TranscriptStore`. New `SessionSearchTool.cs`.

### 4.2 Insights/Analytics
**Upstream**: `agent/insights.py`
**Key patterns**:
- Token consumption per session/model
- Cost estimates via `usage_pricing.py`
- Tool usage patterns, activity trends
- Model/platform breakdowns
**C# port**: `src/analytics/InsightsService.cs`. Track in `Agent.ChatAsync` post-loop. Dashboard panel.

### 4.3 Hook System
**Upstream**: `gateway/hooks.py`
**Key patterns**:
- `HookRegistry` with `discover_and_load()` and `emit(event_type, context)`
- Events: gateway:startup, session:start/end/reset, agent:start/step/end, command:*
- YAML manifest: name, events, description
- Handler: `async handle(event_type, context)` function
- Error isolation: exceptions caught and logged, never propagate
- Wildcard matching: `command:*` matches any `command:...`
**C# port**: Existing `src/hooks/HookSystem.cs` already has 9 event types. Extend with discovery from `~/.hermes-cs/hooks/` directories.

## Phase 5: Quick Wins

### 5.1 Home Assistant Tool
**Upstream**: `tools/homeassistant_tool.py`
- REST API: list entities, get state, list services, call services
- Block dangerous domains (shell commands, scripts)

### 5.2 Send Message Tool
**Upstream**: `tools/send_message_tool.py`
- Cross-platform send to 13 platforms
- Smart chunking, format conversion, media support
- Thread/topic targeting, cron deduplication

### 5.3 Skills Hub Client
**Upstream**: `tools/skills_hub.py`
- Sources: GitHub, skills.sh, clawhub.ai, LobeHub (14.5K agents)
- Quarantine scanning, lock files, audit logging
- Trust stratification: builtin/trusted/community

### 5.4 MCP OAuth
**Upstream**: `tools/mcp_oauth.py`
- OAuth flow for MCP server authentication
