# Session Management, Crash Recovery & Context Switching

**Source**: Reference architecture analysis
**Date**: 2026-04-03
**Purpose**: Capture session persistence, crash recovery, and lossless context switching for Hermes.C#

---

## 🎯 Core Systems Overview

Modern agentic systems use **5 critical systems** for handling power loss, session switching, and context persistence:

1. **Transcript Persistence** - Every message saved to disk before API call
2. **Session History** - JSONL history for resume/replay
3. **Auto-Compact** - Automatic context summarization
4. **Dream System** - Background memory consolidation
5. **KAIROS Mode** - Proactive assistant with daily logs

---

## 1. Transcript Persistence (CRITICAL)

### File Location
```
~/.claude/projects/<sanitized-git-root>/transcripts/
  <sessionId>.jsonl
```

### Key Insight
> **Messages are written to transcript BEFORE the API call** - ensures `--resume` works even if killed mid-flight

### Implementation Flow
```typescript
async function submitMessage(userMessage: string) {
  // 1. Build messages array
  mutableMessages.push(userMessage);
  
  // 2. PERSIST TO TRANSCRIPT (before API call!)
  if (isBareMode()) {
    // Fire-and-forget (saves ~4ms on SSD)
    saveToTranscript(mutableMessages);
  } else if (HERMES_EAGER_FLUSH || HERMES_IS_COWORK) {
    // Awaited + flushed
    await saveToTranscript(mutableMessages);
    await fs.flush();
  } else {
    // Default: async save
    saveToTranscript(mutableMessages);
  }
  
  // 3. NOW make API call
  const response = await callModel(mutableMessages);
  
  // 4. Append response to transcript
  mutableMessages.push(response);
  saveToTranscript(mutableMessages);
}
```

### Transcript Format (JSONL)
```jsonl
{"id":"msg_1","type":"user","content":"Hello","timestamp":"2026-04-03T12:00:00Z"}
{"id":"msg_2","type":"assistant","content":"Hi there!","timestamp":"2026-04-03T12:00:01Z"}
{"id":"msg_3","type":"tool_use","name":"bash","input":{"command":"ls"},"timestamp":"2026-04-03T12:00:02Z"}
{"id":"msg_4","type":"tool_result","tool_use_id":"msg_3","content":"file1.txt\nfile2.txt","timestamp":"2026-04-03T12:00:03Z"}
```

### Resume Logic
```typescript
async function resumeSession(sessionId: string) {
  const transcriptPath = getTranscriptPath(sessionId);
  
  if (!File.Exists(transcriptPath)) {
    throw new SessionNotFoundException(sessionId);
  }
  
  // Read all messages
  var messages = await ReadAllLinesAsync(transcriptPath);
  
  // Parse JSONL
  var sessionMessages = messages
    .Select(line => JsonSerializer.Deserialize<Message>(line))
    .ToList();
  
  // Restore session state
  state.SessionId = sessionId;
  state.Messages = sessionMessages;
  
  // Show resume notice
  Console.WriteLine($"Resumed session {sessionId} ({sessionMessages.Count} messages)");
  
  return sessionMessages;
}
```

---

## 2. Session History (Up-Arrow + Ctrl+R)

### File Location
```
~/.claude/history.jsonl
```

### Purpose
- **Up-arrow navigation** - Quick access to recent commands
- **Ctrl+R fuzzy search** - Find old commands
- **Project-scoped** - History is scoped to project root

### Entry Structure
```typescript
type HistoryEntry = {
  command: string;
  timestamp: number;
  project: string;  // git root or cwd
  sessionId?: string;
}
```

### Key Features

#### Pasted Content Handling
- **Inline**: If < 1024 bytes, stored directly in entry
- **External**: If >= 1024 bytes, stored as hash reference

#### Concurrent Session Handling
```typescript
// Current session entries first (newest-first)
// Then other session entries (also newest-first)
// MAX_HISTORY_ITEMS = 100 window
// Prevents concurrent sessions from interleaving up-arrow history
```

#### Undo Last Entry
```typescript
function removeLastFromHistory() {
  // Fast path: if still in pendingEntries, splice out
  if (pendingEntries.Count > 0) {
    pendingEntries.RemoveAt(pendingEntries.Count - 1);
    return;
  }
  
  // Slow path: remove from file
  var lines = File.ReadAllLines(historyPath).ToList();
  lines.RemoveAt(lines.Count - 1);
  File.WriteAllLines(historyPath, lines);
}
```

### Implementation for Hermes.C#
```csharp
public sealed class HistoryManager
{
    private readonly string _historyPath;
    private readonly List<HistoryEntry> _pendingEntries = new();
    private const int MAX_HISTORY_ITEMS = 100;
    private const int MAX_PASTED_CONTENT_LENGTH = 1024;
    
    public void AddToHistory(string command, string project, string? sessionId)
    {
        var entry = new HistoryEntry
        {
            Command = command,
            Timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Project = project,
            SessionId = sessionId
        };
        
        _pendingEntries.Add(entry);
        
        // Fire-and-forget flush
        _ = FlushAsync();
    }
    
    public async IAsyncEnumerable<HistoryEntry> GetHistory()
    {
        // Current session first
        foreach (var entry in _pendingEntries.OrderByDescending(e => e.Timestamp))
        {
            yield return entry;
        }
        
        // Then from file
        if (File.Exists(_historyPath))
        {
            var lines = await File.ReadAllLinesAsync(_historyPath);
            foreach (var line in lines)
            {
                var entry = JsonSerializer.Deserialize<HistoryEntry>(line);
                yield return entry;
            }
        }
    }
    
    private async Task FlushAsync()
    {
        // Append pending entries to file
        var jsonLines = _pendingEntries.Select(e => JsonSerializer.Serialize(e));
        await File.AppendAllLinesAsync(_historyPath, jsonLines);
        _pendingEntries.Clear();
    }
}
```

---

## 3. Auto-Compact System (Context Window Management)

### Purpose
Automatically summarizes conversation when context window usage exceeds threshold (default 90%).

### Compaction Types

#### 1. Micro-Compact (Lightweight)
- **What**: Clears old tool result content
- **When**: Idle gap > threshold OR cache warm
- **Cost**: Free (no API call)
- **Result**: Tool results replaced with `[Old tool result content cleared]`

#### 2. Full Compact (Heavy)
- **What**: LLM-generated conversation summary
- **When**: Context > 90% full
- **Cost**: API call (~$0.10)
- **Result**: `<compact_summary>` tagged message

#### 3. Session Memory Compact (Medium)
- **What**: Summarizes older session memory segments
- **When**: Tokens > 10k AND text blocks > 5
- **Cost**: API call (~$0.05)
- **Result**: Preserves recent tool context

### Compaction Flow
```typescript
async function* query(messages: Message[]) {
  // 1. Check token budget
  const tokens = estimateTokens(messages);
  
  // 2. Micro-compact (if idle gap or cache warm)
  if (shouldMicroCompact()) {
    messages = await microcompactMessages(messages);
  }
  
  // 3. Check if over threshold
  if (tokens / CONTEXT_WINDOW_SIZE > 0.9) {
    // 4. Full compact
    const summary = await compact(messages);
    
    // 5. Insert compact boundary message
    messages = [
      ...messages.slice(0, summary.startIndex),
      { type: 'compact_summary', content: summary.text },
      ...messages.slice(summary.endIndex)
    ];
    
    // 6. Post-compact cleanup
    runPostCompactCleanup();
  }
  
  // 7. Call model
  yield* callModel(messages);
}
```

### Compact Boundary Message
```typescript
type CompactBoundaryMessage = {
  type: 'compact_summary';
  content: string;  // LLM-generated summary
  startIndex: number;  // Messages before compact
  endIndex: number;  // Messages after compact (recent)
  timestamp: number;
}
```

### Implementation for Hermes.C#
```csharp
public sealed class AutoCompactManager
{
    private const double COMPACT_THRESHOLD = 0.9;
    private const int CONTEXT_WINDOW_SIZE = 200_000;
    private const int MICROCOMPACT_IDLE_MS = 5 * 60_000; // 5 minutes
    
    public async Task<List<Message>> MaybeCompactAsync(List<Message> messages)
    {
        var tokens = EstimateTokens(messages);
        
        // Check threshold
        if ((double)tokens / CONTEXT_WINDOW_SIZE < COMPACT_THRESHOLD)
        {
            return messages; // No compaction needed
        }
        
        // Find compaction point (keep last 10 messages)
        var keepCount = 10;
        var compactStart = messages.Count - keepCount;
        
        // Generate summary
        var summaryPrompt = BuildCompactPrompt(messages.Take(compactStart).ToList());
        var summary = await _chatClient.CompleteAsync(summaryPrompt);
        
        // Build compact boundary message
        var compactMessage = new Message
        {
            Role = "system",
            Content = $"<compact_summary>\n{summary}\n</compact_summary>",
            Timestamp = DateTime.UtcNow
        };
        
        // Rebuild messages
        var result = new List<Message> { compactMessage };
        result.AddRange(messages.Skip(compactStart));
        
        // Cleanup
        RunPostCompactCleanup();
        
        return result;
    }
    
    private int EstimateTokens(List<Message> messages)
    {
        // Rough estimation: 4 chars per token
        var totalChars = messages.Sum(m => m.Content?.Length ?? 0);
        return (int)(totalChars / 4 * 1.33); // 4/3 padding factor
    }
}
```

---

## 4. Dream System (Background Memory Consolidation)

### Purpose
Periodically scans session transcripts and uses a forked agent to consolidate learnings into persistent memory files.

### Architecture
```
AutoDream System
  ├─ Session Scanner (every 10 minutes)
  ├─ Consolidation Agent (forked)
  ├─ Memory Merger
  └─ Index Updater
```

### Consolidation Prompt (4 Phases)
```markdown
# Phase 1: Orient
Read existing memory files to understand current state.

# Phase 2: Gather Recent Signal
Read session transcripts since last consolidation.
- Focus on: decisions, lessons learned, user preferences
- Ignore: transient errors, failed attempts

# Phase 3: Consolidate
Merge new learnings into memory files.
- Update existing memories if contradicted
- Create new memories for novel insights
- Prune outdated memories

# Phase 4: Prune and Index
- Remove stale entries (>30 days, no references)
- Update MEMORY.md index
- Log consolidation summary
```

### Consolidation Interval
```typescript
const SESSION_SCAN_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

async function autoDreamLoop() {
  while (true) {
    await delay(SESSION_SCAN_INTERVAL_MS);
    
    if (!isAutoDreamEnabled()) continue;
    
    const sessions = findSessionsSinceLastConsolidation();
    
    for (const session of sessions) {
      await consolidateSession(session);
    }
    
    updateLastConsolidationTime();
  }
}
```

### Implementation for Hermes.C#
```csharp
public sealed class AutoDreamService : BackgroundService
{
    private static readonly TimeSpan SCAN_INTERVAL = TimeSpan.FromMinutes(10);
    
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await Task.Delay(SCAN_INTERVAL, stoppingToken);
            
            if (!IsAutoDreamEnabled()) continue;
            
            var sessions = FindSessionsSinceLastConsolidation();
            
            foreach (var session in sessions)
            {
                await ConsolidateSessionAsync(session, stoppingToken);
            }
            
            UpdateLastConsolidationTime();
        }
    }
    
    private async Task ConsolidateSessionAsync(Session session, CancellationToken ct)
    {
        // Read session transcript
        var transcript = await ReadTranscriptAsync(session.Id, ct);
        
        // Read existing memories
        var memories = await ReadMemoriesAsync(ct);
        
        // Build consolidation prompt
        var prompt = $@"
# Phase 1: Orient
Current memories:
{string.Join("\n", memories.Select(m => $"- {m.Name}: {m.Description}"))}

# Phase 2: Gather Recent Signal
Session transcript ({session.Id}):
{string.Join("\n", transcript.Select(m => $"{m.Role}: {m.Content}"))}

# Phase 3: Consolidate
Extract new learnings, update contradictions, prune outdated.

# Phase 4: Prune and Index
Remove stale entries, update index.";
        
        // Call LLM
        var result = await _chatClient.CompleteAsync(prompt, ct);
        
        // Parse and apply changes
        await ApplyConsolidationChangesAsync(result, ct);
    }
}
```

---

## 5. KAIROS Mode (Proactive Assistant with Daily Logs)

### Purpose
Continuously-running proactive assistant that observes development environment and takes autonomous action during idle time.

### Daily Log Structure
```
~/.claude/projects/<git-root>/memory/logs/YYYY/MM/YYYY-MM-DD.md
```

### Log Format
```markdown
# 2026-04-03

## Session Summary
- **Sessions**: 3
- **Tools Used**: 47
- **Files Changed**: 12
- **Key Decisions**:
  - Refactored auth module to use JWT
  - Added rate limiting to API endpoints

## Observations
- User prefers TypeScript over JavaScript
- Working on authentication feature
- Struggled with Docker networking

## Actions Taken
- Created memory file for auth patterns
- Updated project README with setup instructions
- Scheduled follow-up for Docker debugging
```

### KAIROS Features
- **Append-only logs** - Daily logs never modified, only appended
- **Proactive actions** - Takes action during idle time
- **Observation mode** - Watches user work patterns
- **Memory extraction** - Automatically creates memory files

### Implementation for Hermes.C#
```csharp
public sealed class KairosService : BackgroundService
{
    private readonly string _logsDir;
    
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromHours(1), stoppingToken);
            
            if (!IsKairosActive()) continue;
            
            await LogDailySummaryAsync(stoppingToken);
        }
    }
    
    private async Task LogDailySummaryAsync(CancellationToken ct)
    {
        var today = DateTime.Today;
        var logPath = GetDailyLogPath(today);
        
        // Ensure directory exists
        Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
        
        // Build summary
        var summary = new StringBuilder();
        summary.AppendLine($"# {today:yyyy-MM-dd}\n");
        
        // Session stats
        var sessions = GetSessionsToday(today);
        summary.AppendLine("## Session Summary");
        summary.AppendLine($"- **Sessions**: {sessions.Count}");
        summary.AppendLine($"- **Tools Used**: {sessions.Sum(s => s.ToolCount)}");
        summary.AppendLine($"- **Files Changed**: {sessions.Sum(s => s.FilesChanged)}");
        
        // Key decisions
        var decisions = ExtractKeyDecisions(sessions);
        if (decisions.Any())
        {
            summary.AppendLine("- **Key Decisions**:\n");
            foreach (var decision in decisions)
            {
                summary.AppendLine($"  - {decision}");
            }
        }
        
        // Append to log
        await File.AppendAllTextAsync(logPath, summary.ToString(), ct);
    }
}
```

---

## 6. Session State Management

### Global State Singleton
```typescript
// bootstrap/state.ts
const state: State = {
  // Session identity
  sessionId: randomUUID(),
  parentSessionId: undefined,
  
  // Working directories
  originalCwd: resolvedCwd,
  projectRoot: gitRoot,
  cwd: currentCwd,
  
  // Cost tracking
  totalCostUSD: 0,
  totalAPIDuration: 0,
  totalToolDuration: 0,
  
  // Model usage
  modelUsage: {},
  mainLoopModelOverride: undefined,
  
  // Feature flags
  isInteractive: true,
  kairosActive: false,
  sessionPersistenceDisabled: false,
  
  // Lineage tracking
  planSlugCache: new Map(),  // sessionId -> wordSlug
  
  // Metrics
  turnHookDurationMs: 0,
  turnToolDurationMs: 0,
  totalLinesAdded: 0,
  totalLinesRemoved: 0,
};
```

### Session Switching
```typescript
function switchSession(sessionId: SessionId, projectDir?: string | null) {
  const oldSessionId = state.sessionId;
  
  // Atomically update
  state.sessionId = sessionId;
  state.sessionProjectDir = projectDir ?? null;
  
  // Emit signal for UI/components
  sessionSwitched.emit(sessionId);
  
  // Log telemetry
  logSessionSwitch(oldSessionId, sessionId);
}
```

### Parent Session Tracking
```typescript
function regenerateSessionId(options?: { setCurrentAsParent?: boolean }) {
  if (options?.setCurrentAsParent) {
    state.parentSessionId = state.sessionId;
  }
  
  state.sessionId = randomUUID();
  
  return state.sessionId;
}
```

---

## 7. Crash Recovery Patterns

### Pattern 1: Write-Ahead Logging
```typescript
// BEFORE making state change
await fs.appendFile(transcriptPath, JSON.stringify(message) + '\n');

// THEN update in-memory state
messages.push(message);
```

### Pattern 2: Atomic File Replacement
```typescript
async function atomicWriteFile(filePath: string, content: string) {
  const tempPath = filePath + '.tmp.' + randomUUID();
  
  // Write to temp file
  await fs.writeFile(tempPath, content);
  
  // Atomic rename
  await fs.rename(tempPath, filePath);
}
```

### Pattern 3: Periodic Flush
```typescript
let pendingWrites: string[] = [];
let flushTimer: NodeJS.Timeout | null = null;

function queueWrite(line: string) {
  pendingWrites.push(line);
  
  if (!flushTimer) {
    flushTimer = setTimeout(flush, 100); // 100ms debounce
  }
}

async function flush() {
  if (pendingWrites.length === 0) return;
  
  const lines = pendingWrites;
  pendingWrites = [];
  
  await fs.appendFile(historyPath, lines.join('\n') + '\n');
  
  flushTimer = null;
}
```

### Pattern 4: Cleanup on Exit
```typescript
process.on('exit', () => {
  // Flush pending writes
  flushSync();
  
  // Release locks
  releaseFileLocks();
  
  // Log shutdown
  logEvent('process_exit', { reason: 'normal' });
});

process.on('SIGINT', () => {
  gracefulShutdown('SIGINT');
});

process.on('SIGTERM', () => {
  gracefulShutdown('SIGTERM');
});
```

---

## 8. Implementation Checklist for Hermes.C#

### Phase 1: Basic Persistence ✅
- [x] Transcript file format (JSONL)
- [ ] Write-before-execute pattern
- [ ] Resume session from transcript
- [ ] Session ID generation (UUID)

### Phase 2: History Management
- [ ] History file (JSONL)
- [ ] Up-arrow navigation
- [ ] Ctrl+R fuzzy search
- [ ] Project-scoped history
- [ ] Pasted content handling

### Phase 3: Auto-Compact
- [ ] Token estimation
- [ ] Micro-compact (idle gap)
- [ ] Full compact (LLM summary)
- [ ] Compact boundary messages
- [ ] Post-compact cleanup

### Phase 4: Dream System
- [ ] Background service (10-min interval)
- [ ] Session scanner
- [ ] Consolidation agent
- [ ] Memory merger
- [ ] Index updater

### Phase 5: KAIROS Mode
- [ ] Daily log creation
- [ ] Session summarization
- [ ] Observation tracking
- [ ] Proactive actions
- [ ] Append-only logs

### Phase 6: Crash Recovery
- [ ] Write-ahead logging
- [ ] Atomic file replacement
- [ ] Periodic flush (100ms debounce)
- [ ] Cleanup on exit hooks
- [ ] File locking

### Phase 7: Session Management
- [ ] Global state singleton
- [ ] Session switching
- [ ] Parent session tracking
- [ ] Cost tracking
- [ ] Metrics collection

---

## 9. File Structure

```
~/.hermes-cs/
  projects/
    <sanitized-git-root>/
      transcripts/
        <sessionId>.jsonl
      memory/
        MEMORY.md
        <topic>.md
        logs/
          YYYY/
            MM/
              YYYY-MM-DD.md
  history.jsonl
  config.yaml
```

---

## 10. Key Design Principles

### 1. Durability Over Speed
> Write to disk BEFORE making API calls or changing state

### 2. Atomic Operations
> Use temp files + rename for critical writes

### 3. Periodic Flush
> Debounce writes (100ms) to balance durability and performance

### 4. Graceful Degradation
> If flush fails, log error but continue (don't block user)

### 5. Idempotent Recovery
> Resume should work even if called multiple times

### 6. Append-Only Logs
> Daily logs, transcripts are append-only (easier recovery)

---

**Next Step**: Implement transcript persistence and resume functionality as the foundation!
