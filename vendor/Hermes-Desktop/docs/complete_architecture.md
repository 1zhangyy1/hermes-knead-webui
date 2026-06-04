# Hermes.C# - Complete Architecture Blueprint

**Vision**: Build a **teammate**, not a tool. Persistent, proactive, coordinated, crash-proof.

**Date**: 2026-04-03  
**Status**: Foundation complete (6/19 tools), Architecture designed

---

## The 9 Architectural Pillars

| # | Pillar | Status | Priority |
|---|--------|--------|----------|
| 1 | **Persistent Memory** | ⬜ Not started | P0 |
| 2 | **Dream System** | ⬜ Not started | P1 |
| 3 | **Agent Teams** | ⬜ Not started | P0 |
| 4 | **Coordinator Mode** | ⬜ Not started | P1 |
| 5 | **Transcript-First** | ⬜ Not started | P0 |
| 6 | **Task V2** | ⬜ Not started | P1 |
| 7 | **Buddy System** | ⬜ Not started | P3 |
| 8 | **Skills System** | ⬜ Not started | P1 |
| 9 | **Granular Permissions** | ⬜ Not started | P0 |

**Foundation** (✅ Done):
- 6 core tools: bash, read_file, write_file, edit_file, glob, grep
- C# project structure
- .NET 9 SDK
- Build system working

---

## 📐 Project Structure (Final)

```
Hermes.CS/
├── src/
│   ├── Hermes.Agent.csproj          # Core library
│   ├── Hermes.CLI.csproj            # CLI executable
│   ├── Hermes.Gateway.csproj        # Multi-platform gateway (Telegram, Discord)
│   │
│   ├── Core/
│   │   ├── Agent.cs                 # Main agent loop
│   │   ├── Session.cs               # Session state, transcript persistence
│   │   ├── Message.cs               # Message types
│   │   ├── ToolResult.cs            # Tool execution results
│   │   └── ITool.cs                 # Tool interface
│   │
│   ├── Tools/                       # ✅ 6 implemented, 13 remaining
│   │   ├── BashTool.cs              # ✅ Shell execution
│   │   ├── ReadFileTool.cs          # ✅ File reading
│   │   ├── WriteFileTool.cs         # ✅ File writing
│   │   ├── EditFileTool.cs          # ✅ String replacement
│   │   ├── GlobTool.cs              # ✅ Pattern matching
│   │   ├── GrepTool.cs              # ✅ Content search
│   │   ├── AgentTool.cs             # ⬜ Spawn subagents
│   │   ├── SendMessageTool.cs       # ⬜ Inter-agent messaging
│   │   ├── TaskCreateTool.cs        # ⬜ Task V2
│   │   ├── TaskGetTool.cs           # ⬜
│   │   ├── TaskUpdateTool.cs        # ⬜
│   │   ├── TaskListTool.cs          # ⬜
│   │   ├── TaskStopTool.cs          # ⬜
│   │   ├── TaskOutputTool.cs        # ⬜
│   │   └── BriefTool.cs             # ⬜ KAIROS user messaging
│   │
│   ├── Memory/                      # ⬜ PILLAR 1: Persistent Memory
│   │   ├── MemoryManager.cs         # Scan, select, inject memories
│   │   ├── MemoryFile.cs            # Memory file format
│   │   ├── MemoryScanner.cs         # Frontmatter parsing
│   │   ├── MemoryRelevance.cs       # LLM-based relevance selection
│   │   └── FreshnessWarnings.cs     # Age-based caveats
│   │
│   ├── Dream/                       # ⬜ PILLAR 2: Dream Consolidation
│   │   ├── AutoDreamService.cs      # Background service (10-min interval)
│   │   ├── ConsolidationAgent.cs    # Forked agent for consolidation
│   │   ├── ConsolidationPrompt.cs   # 4-phase prompt
│   │   └── DreamConfig.cs           # GrowthBook-like config
│   │
│   ├── Agents/                      # ⬜ PILLAR 3: Agent Teams
│   │   ├── AgentService.cs          # Spawn/manage agents
│   │   ├── TeamManager.cs           # Team CRUD
│   │   ├── MailboxService.cs        # Inter-agent messaging
│   │   ├── AgentContext.cs          # Agent identification
│   │   └── IsolationStrategy.cs     # Worktree, remote, none
│   │
│   ├── Coordinator/                 # ⬜ PILLAR 4: Coordinator Mode
│   │   ├── CoordinatorService.cs    # Multi-worker orchestration
│   │   ├── WorkerPrompt.cs          # Worker guidelines
│   │   ├── TaskWorkflow.cs          # Research→Synthesis→Implement→Verify
│   │   └── ModeMatcher.cs           # Resume mode alignment
│   │
│   ├── Transcript/                  # ⬜ PILLAR 5: Transcript-First
│   │   ├── TranscriptStore.cs       # JSONL persistence
│   │   ├── ResumeManager.cs         # Session resume logic
│   │   ├── WriteAheadLogger.cs      # Write-before-execute
│   │   └── SessionHistory.cs        # Up-arrow, Ctrl+R
│   │
│   ├── Tasks/                       # ⬜ PILLAR 6: Task V2
│   │   ├── TaskManager.cs           # Task CRUD
│   │   ├── TaskModels.cs            # Task types, states
│   │   ├── TaskScheduler.cs         # Cron scheduling
│   │   └── VerificationNudge.cs     # Completion verification
│   │
│   ├── Skills/                      # ⬜ PILLAR 8: Skills System
│   │   ├── SkillManager.cs          # Load/apply skills
│   │   ├── SkillFile.cs             # Markdown + YAML format
│   │   └── SkillInvoker.cs          # Skill execution
│   │
│   ├── Permissions/                 # ⬜ PILLAR 9: Granular Permissions
│   │   ├── PermissionManager.cs     # Rule evaluation
│   │   ├── PermissionRules.cs       # Rule DSL
│   │   ├── PermissionModes.cs       # default, auto, bypass, acceptEdits
│   │   └── PermissionDialog.cs      # User prompts
│   │
│   ├── Buddy/                       # ⬜ PILLAR 7: Buddy System
│   │   ├── BuddyService.cs          # Companion management
│   │   ├── BuddyGenerator.cs        # Deterministic gacha (Mulberry32)
│   │   ├── BuddySoul.cs             # AI-generated personality
│   │   └── BuddyRenderer.cs         # ASCII art display
│   │
│   ├── KAIROS/                      # Proactive Mode
│   │   ├── KairosService.cs         # Background proactive assistant
│   │   ├── DailyLogger.cs           # Append-only daily logs
│   │   └── ObservationTracker.cs    # User behavior tracking
│   │
│   ├── Compact/                     # Context Management
│   │   ├── AutoCompactManager.cs    # Token threshold compaction
│   │   ├── MicroCompact.cs          # Tool result clearing
│   │   └── CompactBoundary.cs       # Summary messages
│   │
│   ├── LLM/
│   │   ├── IChatClient.cs           # ✅ LLM interface
│   │   └── OpenAiClient.cs          # ✅ OpenAI-compatible client
│   │
│   ├── Platform/                    # Multi-platform support
│   │   ├── IPlatform.cs             # Platform interface
│   │   ├── TelegramPlatform.cs      # Telegram bot
│   │   ├── DiscordPlatform.cs       # Discord bot
│   │   └── CliPlatform.cs           # Terminal CLI
│   │
│   └── Program.cs                   # CLI entry point
│
├── tests/
│   └── Hermes.Tests.csproj
│
├── docs/
│   ├── README.md                    # ✅ Project overview
│   ├── TOOLS_STATUS.md              # ✅ Tool implementation status
│   ├── AGENT_ARCHITECTURE_DEEP_DIVE.md  # ✅ Tool system analysis
│   ├── SESSION_MANAGEMENT.md        # ✅ Session/crash recovery
│   └── KAIROS_AND_MULTIAGENT.md     # ✅ KAIROS + multi-agent
│
└── Hermes.CS.sln
```

---

## 🏗️ Core Implementation

### Pillar 1: Persistent Memory

```csharp
// src/Memory/MemoryManager.cs
namespace Hermes.Agent.Memory;

public sealed class MemoryManager
{
    private readonly string _memoryDir;
    private readonly IChatClient _chatClient;
    
    public MemoryManager(string memoryDir, IChatClient chatClient)
    {
        _memoryDir = memoryDir;
        _chatClient = chatClient;
    }
    
    /// <summary>
    /// Scan memory files, select relevant ones, inject into context
    /// </summary>
    public async Task<List<MemoryContext>> LoadRelevantMemoriesAsync(
        string query, 
        List<string> recentTools,
        CancellationToken ct)
    {
        // 1. Scan all memory files (frontmatter only)
        var headers = await ScanMemoryFilesAsync(_memoryDir, ct);
        
        // 2. Filter out already-surfaced memories
        var freshHeaders = headers.Where(h => !h.AlreadySurfaced).ToList();
        
        // 3. Use LLM to select most relevant (up to 5)
        var relevant = await SelectRelevantMemoriesAsync(
            query, freshHeaders, recentTools, ct);
        
        // 4. Load full content + add freshness warnings
        var memories = new List<MemoryContext>();
        foreach (var mem in relevant)
        {
            var content = await File.ReadAllTextAsync(mem.Path, ct);
            var warning = GetFreshnessWarning(mem.Mtime);
            memories.Add(new MemoryContext
            {
                Path = mem.Path,
                Content = content,
                FreshnessWarning = warning
            });
        }
        
        return memories;
    }
    
    private async Task<List<MemoryHeader>> ScanMemoryFilesAsync(
        string dir, CancellationToken ct)
    {
        var headers = new List<MemoryHeader>();
        
        if (!Directory.Exists(dir))
            return headers;
        
        var files = Directory.EnumerateFiles(dir, "*.md", SearchOption.AllDirectories)
            .Where(f => !f.EndsWith("MEMORY.md")) // Skip entrypoint
            .Take(200); // Cap at 200 files
        
        foreach (var file in files)
        {
            var header = await ParseFrontmatterAsync(file, ct);
            if (header != null)
                headers.Add(header);
        }
        
        // Sort by modification time (newest first)
        return headers.OrderByDescending(h => h.Mtime).ToList();
    }
    
    private async Task<MemoryHeader?> ParseFrontmatterAsync(
        string path, CancellationToken ct)
    {
        var lines = await File.ReadAllLinesAsync(path, ct);
        
        // Parse YAML frontmatter (first 30 lines max)
        var yamlLines = lines
            .TakeWhile((l, i) => i < 30 && (i == 0 || !l.Trim().Equals("---")))
            .Skip(1) // Skip opening ---
            .ToList();
        
        var yaml = string.Join("\n", yamlLines);
        
        try
        {
            var frontmatter = Yaml.Deserialize<MemoryFrontmatter>(yaml);
            return new MemoryHeader
            {
                Path = path,
                Filename = Path.GetFileName(path),
                Mtime = File.GetLastWriteTimeUtc(path),
                Description = frontmatter.Description,
                Type = frontmatter.Type
            };
        }
        catch
        {
            return null;
        }
    }
    
    private async Task<List<MemoryHeader>> SelectRelevantMemoriesAsync(
        string query, 
        List<MemoryHeader> candidates,
        List<string> recentTools,
        CancellationToken ct)
    {
        // Build manifest for LLM
        var manifest = string.Join("\n", candidates.Select(h => 
            $"- [{h.Type}] {h.Filename}: {h.Description}"));
        
        var prompt = $@"
You are selecting relevant memories for this query.

Query: {query}
Recent tools used: {string.Join(", ", recentTools)}

Available memories:
{manifest}

Select up to 5 most relevant memories. Return ONLY filenames, one per line.
Filenames:";
        
        var response = await _chatClient.CompleteAsync(
            new[] { new Message { Role = "user", Content = prompt } }, ct);
        
        var filenames = response.Split('\n')
            .Select(l => l.Trim().TrimEnd(':'))
            .Where(l => !string.IsNullOrEmpty(l))
            .Take(5)
            .ToList();
        
        return candidates.Where(h => filenames.Contains(h.Filename)).ToList();
    }
    
    private string? GetFreshnessWarning(DateTime mtime)
    {
        var days = (DateTime.UtcNow - mtime).TotalDays;
        
        if (days < 1)
            return null; // Too fresh, no warning
        
        return $"<system-reminder>This memory is {days:F0} days old. " +
               $"Memories are point-in-time observations, not live state. " +
               $"Verify against current code before asserting as fact.</system-reminder>";
    }
}

// Memory file format
public sealed class MemoryFrontmatter
{
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";
    public string Type { get; set; } = "user"; // user, feedback, project, reference
}

public sealed class MemoryHeader
{
    public string Path { get; set; } = "";
    public string Filename { get; set; } = "";
    public DateTime Mtime { get; set; }
    public string? Description { get; set; }
    public string? Type { get; set; }
    public bool AlreadySurfaced { get; set; }
}

public sealed class MemoryContext
{
    public string Path { get; set; } = "";
    public string Content { get; set; } = "";
    public string? FreshnessWarning { get; set; }
}
```

---

### Pillar 2: Dream System

```csharp
// src/Dream/AutoDreamService.cs
namespace Hermes.Agent.Dream;

public sealed class AutoDreamService : BackgroundService
{
    private static readonly TimeSpan SCAN_INTERVAL = TimeSpan.FromMinutes(10);
    private readonly ILogger<AutoDreamService> _logger;
    private readonly IServiceProvider _services;
    
    public AutoDreamService(
        ILogger<AutoDreamService> logger,
        IServiceProvider services)
    {
        _logger = logger;
        _services = services;
    }
    
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        _logger.LogInformation("AutoDream service starting");
        
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(SCAN_INTERVAL, ct);
            
            if (!IsAutoDreamEnabled())
                continue;
            
            try
            {
                await ConsolidateSessionsAsync(ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Dream consolidation failed");
            }
        }
    }
    
    private async Task ConsolidateSessionsAsync(CancellationToken ct)
    {
        // 1. Find sessions since last consolidation
        var sessions = FindSessionsSinceLastConsolidation();
        
        if (!sessions.Any())
        {
            _logger.LogDebug("No new sessions to consolidate");
            return;
        }
        
        _logger.LogInformation("Consolidating {Count} sessions", sessions.Count);
        
        // 2. Fork consolidation agent
        using var scope = _services.CreateScope();
        var consolidator = scope.ServiceProvider.GetRequiredService<ConsolidationAgent>();
        
        // 3. Run consolidation
        await consolidator.ConsolidateAsync(sessions, ct);
        
        // 4. Update last consolidation time
        UpdateLastConsolidationTime();
    }
    
    private bool IsAutoDreamEnabled()
    {
        // Check GrowthBook-like config
        var config = DreamConfig.Load();
        return config.Enabled && 
               config.MinSessions <= GetSessionCount() &&
               config.MinHours <= GetHoursSinceLastConsolidation();
    }
}

// src/Dream/ConsolidationAgent.cs
public sealed class ConsolidationAgent
{
    private readonly IChatClient _chatClient;
    private readonly MemoryManager _memoryManager;
    
    public async Task ConsolidateAsync(
        List<Session> sessions, 
        CancellationToken ct)
    {
        // 1. Read existing memories
        var existingMemories = await _memoryManager.LoadAllMemoriesAsync(ct);
        
        // 2. Read session transcripts
        var transcripts = sessions.Select(s => ReadTranscript(s.Id)).ToList();
        
        // 3. Build 4-phase consolidation prompt
        var prompt = BuildConsolidationPrompt(existingMemories, transcripts);
        
        // 4. Call LLM
        var result = await _chatClient.CompleteAsync(
            new[] { new Message { Role = "user", Content = prompt } }, ct);
        
        // 5. Parse and apply changes
        await ApplyConsolidationChangesAsync(result, ct);
    }
    
    private string BuildConsolidationPrompt(
        List<MemoryContext> existing,
        List<string> transcripts)
    {
        return $@"
# Phase 1: Orient
Current memories:
{string.Join("\n", existing.Select(m => $"- {m.Path}: {m.Content.Take(200)}..."))}

# Phase 2: Gather Recent Signal
Session transcripts since last consolidation:
{string.Join("\n---\n", transcripts)}

# Phase 3: Consolidate
Extract new learnings, update contradictions, prune outdated.
Focus on:
- Decisions made
- Lessons learned
- User preferences
- Architecture patterns
Ignore:
- Transient errors
- Failed attempts
- Temporary workarounds

# Phase 4: Prune and Index
Remove stale entries (>30 days, no references)
Update MEMORY.md index
Log consolidation summary

Return your changes as:
## New Memories
[memory content]

## Updated Memories
[filename]: [changes]

## Deleted Memories
[filename]

## Summary
[consolidation summary]
";
    }
}
```

---

### Pillar 3: Agent Teams

```csharp
// src/Agents/TeamManager.cs
namespace Hermes.Agent.Agents;

public sealed class TeamManager
{
    private readonly string _teamsDir;
    private readonly MailboxService _mailbox;
    
    public async Task<TeamResult> CreateTeamAsync(
        string teamName, 
        string? description,
        CancellationToken ct)
    {
        var teamPath = Path.Combine(_teamsDir, $"{teamName}.json");
        
        if (File.Exists(teamPath))
            throw new TeamAlreadyExistsException(teamName);
        
        var team = new Team
        {
            TeamName = teamName,
            Description = description,
            LeadAgentId = GetCurrentAgentId(),
            Members = new List<TeamMember>(),
            CreatedAt = DateTime.UtcNow
        };
        
        var json = JsonSerializer.Serialize(team, JsonOptions);
        await File.WriteAllTextAsync(teamPath, json, ct);
        
        _logger.LogInformation("Created team {TeamName}", teamName);
        
        return new TeamResult
        {
            TeamName = teamName,
            TeamFilePath = teamPath,
            LeadAgentId = team.LeadAgentId
        };
    }
    
    public async Task DeleteTeamAsync(string teamName, CancellationToken ct)
    {
        var team = await LoadTeamAsync(teamName, ct);
        
        // Check for running members
        var runningMembers = team.Members
            .Where(m => m.Status == "active" && m.AgentId != team.LeadAgentId)
            .ToList();
        
        if (runningMembers.Any())
        {
            throw new TeamHasRunningMembersException(
                $"Cannot delete team with {runningMembers.Count} running members");
        }
        
        // Cleanup worktrees
        await CleanupTeamWorktreesAsync(teamName, ct);
        
        // Delete team file
        var teamPath = Path.Combine(_teamsDir, $"{teamName}.json");
        File.Delete(teamPath);
        
        _logger.LogInformation("Deleted team {TeamName}", teamName);
    }
}

// src/Agents/MailboxService.cs
public sealed class MailboxService
{
    private readonly string _mailboxDir;
    
    public async Task SendMessageAsync(
        string recipient,
        string message,
        string? fromAgentId,
        CancellationToken ct)
    {
        var mailboxPath = Path.Combine(_mailboxDir, $"{recipient}.json");
        
        var msg = new MailboxMessage
        {
            From = fromAgentId ?? "unknown",
            Content = message,
            Timestamp = DateTime.UtcNow,
            Read = false
        };
        
        // Load or create mailbox
        var mailbox = await LoadMailboxAsync(mailboxPath, ct);
        mailbox.Messages.Add(msg);
        
        // Save
        await SaveMailboxAsync(mailboxPath, mailbox, ct);
        
        _logger.LogInformation("Sent message to {Recipient}", recipient);
    }
    
    public async Task<List<MailboxMessage>> ReadMessagesAsync(
        string agentName,
        CancellationToken ct)
    {
        var mailboxPath = Path.Combine(_mailboxDir, $"{agentName}.json");
        
        if (!File.Exists(mailboxPath))
            return new List<MailboxMessage>();
        
        var mailbox = await LoadMailboxAsync(mailboxPath, ct);
        
        // Mark as read
        foreach (var msg in mailbox.Messages.Where(m => !m.Read))
        {
            msg.Read = true;
        }
        
        await SaveMailboxAsync(mailboxPath, mailbox, ct);
        
        return mailbox.Messages.OrderByDescending(m => m.Timestamp).ToList();
    }
}
```

---

### Pillar 5: Transcript-First Persistence

```csharp
// src/Transcript/TranscriptStore.cs
namespace Hermes.Agent.Transcript;

public sealed class TranscriptStore
{
    private readonly string _transcriptsDir;
    
    public async Task SaveMessageAsync(
        string sessionId,
        Message message,
        CancellationToken ct)
    {
        var transcriptPath = GetTranscriptPath(sessionId);
        
        // Ensure directory exists
        Directory.CreateDirectory(Path.GetDirectoryName(transcriptPath)!);
        
        // Serialize to JSONL
        var json = JsonSerializer.Serialize(message);
        
        // CRITICAL: Write BEFORE updating in-memory state
        await File.AppendAllTextAsync(transcriptPath, json + "\n", ct);
        
        // Flush to disk (optional, adds ~4ms latency)
        if (ShouldEagerFlush())
        {
            using var fs = File.Open(transcriptPath, FileMode.Append);
            await fs.FlushAsync(ct);
        }
    }
    
    public async Task<List<Message>> LoadSessionAsync(
        string sessionId,
        CancellationToken ct)
    {
        var transcriptPath = GetTranscriptPath(sessionId);
        
        if (!File.Exists(transcriptPath))
            throw new SessionNotFoundException(sessionId);
        
        var lines = await File.ReadAllLinesAsync(transcriptPath, ct);
        
        return lines
            .Select(l => JsonSerializer.Deserialize<Message>(l))
            .Where(m => m != null)
            .ToList()!;
    }
    
    private bool ShouldEagerFlush()
    {
        // Eager flush in these cases:
        // 1. HERMES_EAGER_FLUSH env var set
        // 2. Running in Cowork (cloud) mode
        // 3. Bare mode (--bare flag) - fire-and-forget, no flush
        return Environment.GetEnvironmentVariable("HERMES_EAGER_FLUSH") != null;
    }
}

// src/Transcript/ResumeManager.cs
public sealed class ResumeManager
{
    private readonly TranscriptStore _transcripts;
    
    public async Task<Session> ResumeSessionAsync(
        string sessionId,
        CancellationToken ct)
    {
        // Load transcript
        var messages = await _transcripts.LoadSessionAsync(sessionId, ct);
        
        // Restore session state
        var session = new Session
        {
            Id = sessionId,
            Messages = messages,
            LastActivityAt = messages.LastOrDefault()?.Timestamp ?? DateTime.UtcNow
        };
        
        Console.WriteLine($"Resumed session {sessionId} ({messages.Count} messages)");
        
        return session;
    }
}
```

---

### Pillar 9: Granular Permissions

```csharp
// src/Permissions/PermissionManager.cs
namespace Hermes.Agent.Permissions;

public sealed class PermissionManager
{
    private readonly PermissionContext _context;
    
    public async Task<PermissionDecision> CheckPermissionsAsync<T>(
        string toolName,
        T input,
        CancellationToken ct)
    {
        // 1. Check mode
        if (_context.Mode == PermissionMode.BypassPermissions)
            return Allow(input);
        
        if (_context.Mode == PermissionMode.Plan)
        {
            if (IsReadOnlyTool(toolName, input))
                return Allow(input);
            else
                return Ask($"Cannot modify files in plan mode");
        }
        
        // 2. Check always_allow rules
        if (MatchesRule(toolName, input, _context.AlwaysAllow))
            return Allow(input);
        
        // 3. Check always_deny rules
        if (MatchesRule(toolName, input, _context.AlwaysDeny))
            return Deny($"Blocked by permission rule");
        
        // 4. Check always_ask rules
        if (MatchesRule(toolName, input, _context.AlwaysAsk))
            return Ask($"Requires permission");
        
        // 5. Default behavior by mode
        return _context.Mode switch
        {
            PermissionMode.Auto => IsReadOnlyTool(toolName, input) 
                ? Allow(input) 
                : Ask($"Modify operation requires permission"),
            PermissionMode.AcceptEdits => IsInWorkspace(input)
                ? Allow(input)
                : Ask($"Outside workspace"),
            _ => Ask($"Default: requires permission")
        };
    }
    
    private bool MatchesRule<T>(string toolName, T input, List<PermissionRule> rules)
    {
        foreach (var rule in rules)
        {
            if (rule.ToolName != toolName && rule.ToolName != "*")
                continue;
            
            if (rule.Pattern == null)
                return true; // Matched tool name, no pattern
            
            // Check pattern against input
            if (MatchesPattern(input, rule.Pattern))
                return true;
        }
        
        return false;
    }
}

// Permission rule DSL
public sealed class PermissionRule
{
    public string ToolName { get; set; } = ""; // "Bash", "Write", "*"
    public string? Pattern { get; set; }       // "git *", "**/*.cs", null
    
    // Examples:
    // Bash(git *) - Allow all git commands
    // Write(**/*.cs) - Allow writing C# files
    // Read(src/**) - Allow reading from src/
    // * - Match all tools
}

public enum PermissionMode
{
    Default,           // Always ask
    Plan,              // Read-only planning
    Auto,              // Auto-approve read-only
    BypassPermissions, // Allow everything (dangerous!)
    AcceptEdits        // Auto-approve edits in workspace
}

public sealed class PermissionDecision
{
    public PermissionBehavior Behavior { get; set; }
    public object? UpdatedInput { get; set; }
    public string? Message { get; set; }
    public string? DecisionReason { get; set; }
}

public enum PermissionBehavior
{
    Allow,
    Ask,
    Deny
}
```

---

## 📋 Implementation Phases

### Phase 1: Foundation (✅ DONE - Week 1)
- [x] Project scaffolding
- [x] 6 core tools (bash, read, write, edit, glob, grep)
- [x] Build system
- [x] CLI entry point
- [ ] LLM client (OpenAI-compatible)

### Phase 2: Core Differentiators (P0 - Weeks 2-3)
- [ ] **Transcript-First Persistence**
  - [ ] TranscriptStore (JSONL)
  - [ ] ResumeManager
  - [ ] Write-ahead logging
  - [ ] Session history (up-arrow, Ctrl+R)
  
- [ ] **Granular Permissions**
  - [ ] PermissionManager
  - [ ] Rule DSL parser
  - [ ] Permission modes
  - [ ] Permission dialogs
  
- [ ] **Persistent Memory**
  - [ ] MemoryManager
  - [ ] Frontmatter parser
  - [ ] Relevance selection
  - [ ] Freshness warnings
  
- [ ] **Agent Teams**
  - [ ] TeamManager (CRUD)
  - [ ] MailboxService
  - [ ] AgentService (spawning)
  - [ ] Isolation strategies

### Phase 3: Advanced Features (P1 - Weeks 4-5)
- [ ] **Dream System**
  - [ ] AutoDreamService (10-min interval)
  - [ ] ConsolidationAgent
  - [ ] 4-phase prompt
  - [ ] Config system
  
- [ ] **Coordinator Mode**
  - [ ] CoordinatorService
  - [ ] Worker orchestration
  - [ ] Mode matching on resume
  
- [ ] **Task V2**
  - [ ] TaskManager (CRUD)
  - [ ] TaskScheduler (cron)
  - [ ] Dependencies
  - [ ] Verification nudge
  
- [ ] **Skills System**
  - [ ] SkillManager
  - [ ] Markdown + YAML parser
  - [ ] Skill invocation

### Phase 4: Proactive Features (P2 - Weeks 6-7)
- [ ] **KAIROS Mode**
  - [ ] KairosService
  - [ ] DailyLogger (append-only)
  - [ ] ObservationTracker
  - [ ] BriefTool
  
- [ ] **Auto-Compact**
  - [ ] AutoCompactManager
  - [ ] MicroCompact
  - [ ] Token estimation

### Phase 5: Polish (P3 - Week 8)
- [ ] **Buddy System**
  - [ ] BuddyService
  - [ ] Mulberry32 PRNG
  - [ ] ASCII renderer
  - [ ] Soul generation
  
- [ ] **Platform Support**
  - [ ] Telegram gateway
  - [ ] Discord gateway
  - [ ] Multi-session management

---

## 🎯 Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Tools Implemented | 19/19 | 6/19 (32%) |
| Pillars Complete | 9/9 | 0/9 (0%) |
| Crash Recovery | ✅ Transcript-first | ⬜ |
| Memory System | ✅ Persistent | ⬜ |
| Agent Teams | ✅ Mailbox comms | ⬜ |
| Coordinator Mode | ✅ Multi-worker | ⬜ |
| Task V2 | ✅ Dependencies | ⬜ |
| KAIROS | ✅ Proactive | ⬜ |

---

## 🚀 Next Immediate Actions

1. **Implement TranscriptStore** - Foundation for everything
2. **Implement PermissionManager** - Safety for auto-mode
3. **Implement MemoryManager** - First differentiator
4. **Implement AgentService** - Enable multi-agent

Once these 4 are done, Hermes.C# will have capabilities matching modern agentic systems.

---

**This is the blueprint. Build it.**
