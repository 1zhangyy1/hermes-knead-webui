# KAIROS & Multi-Agent Systems Deep Dive

**Source**: Reference architecture analysis
**Date**: 2026-04-03
**Purpose**: Complete specification of KAIROS proactive mode and multi-agent orchestration for Hermes.C#

---

## 🎯 Part 1: KAIROS Mode (Proactive Assistant)

### What is KAIROS?

**KAIROS** is a continuously-running proactive assistant mode that:
- Observes your development environment
- Takes autonomous action during idle time
- Maintains append-only daily logs
- Runs background memory consolidation ("dream")
- Schedules recurring tasks via cron

### Feature Gates
```typescript
// KAIROS is enabled when BOTH are true:
feature('KAIROS')  // GrowthBook feature flag
kairosActive       // Runtime state (Ctrl+Shift+B toggles)
```

### Key Commands (KAIROS-only)
| Command | Tool | Description |
|---------|------|-------------|
| `Ctrl+Shift+B` | BriefTool | Toggle brief mode (send user messages) |
| `/dream` | autoDream | Nightly memory distillation |
| `/cron create` | CronCreateTool | Schedule recurring tasks |
| `/cron list` | CronListTool | List scheduled tasks |
| `/cron delete` | CronDeleteTool | Delete scheduled task |

---

## KAIROS Architecture

### 1. Daily Logs (Append-Only)

**Location**:
```
~/.claude/projects/<git-root>/memory/logs/YYYY/MM/YYYY-MM-DD.md
```

**Format**:
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

**Implementation**:
```typescript
// AutoDream system appends to daily log
async function logDailySummary() {
  const today = new Date();
  const logPath = getAutoMemDailyLogPath(today);
  
  // Ensure directory exists
  const dir = path.dirname(logPath);
  await fs.mkdir(dir, { recursive: true });
  
  // Build summary
  const summary = buildDailySummary(today);
  
  // Append (NEVER overwrite)
  await fs.appendFile(logPath, summary);
}
```

### 2. Background Memory Extraction

**Gate**: `isExtractModeActive()` - checks if background memory extraction agent should run

**Process**:
1. Every 10 minutes, scan session transcripts
2. Find sessions since last consolidation
3. Fork a consolidation agent
4. Extract learnings → memory files
5. Update MEMORY.md index

**Consolidation Agent Prompt** (4 phases):
```markdown
# Phase 1: Orient
Read existing memory files to understand current state.

# Phase 2: Gather Recent Signal
Read session transcripts since last consolidation.
Focus on: decisions, lessons learned, user preferences
Ignore: transient errors, failed attempts

# Phase 3: Consolidate
Merge new learnings into memory files.
- Update existing memories if contradicted
- Create new memories for novel insights
- Prune outdated memories

# Phase 4: Prune and Index
Remove stale entries (>30 days, no references)
Update MEMORY.md index
Log consolidation summary
```

### 3. KAIROS Cron System

**Purpose**: Schedule recurring agent tasks

**Commands**:
- `/cron create <expression> <command>` - Schedule task
- `/cron list` - List scheduled tasks
- `/cron delete <id>` - Delete task

**Cron Expression Validation**:
```typescript
// Must be valid 5-field cron expression
// Must match at least one calendar date within next year
// Maximum 50 concurrent scheduled jobs

const MAX_JOBS = 50;

function validateCronExpression(expr: string): boolean {
  // Parse 5 fields: minute, hour, day, month, weekday
  const fields = expr.split(/\s+/);
  if (fields.length !== 5) return false;
  
  // Validate each field
  if (!isValidMinute(fields[0])) return false;
  if (!isValidHour(fields[1])) return false;
  if (!isValidDay(fields[2])) return false;
  if (!isValidMonth(fields[3])) return false;
  if (!isValidWeekday(fields[4])) return false;
  
  // Must match at least one date in next year
  const nextYear = new Date();
  nextYear.setFullYear(nextYear.getFullYear() + 1);
  
  let matches = 0;
  for (let d = new Date(); d < nextYear; d.setMinutes(d.getMinutes() + 1)) {
    if (cronMatches(expr, d)) {
      matches++;
      if (matches > 0) return true;
    }
  }
  
  return false; // No matches in next year
}
```

**Task Types**:
```typescript
type TaskType =
  | 'local_bash'       // prefix: 'b' - Local bash execution
  | 'local_agent'      // prefix: 'a' - Local agent spawn
  | 'remote_agent'     // prefix: 'r' - Remote agent
  | 'in_process_teammate' // prefix: 't' - In-process teammate
  | 'local_workflow'   // prefix: 'w' - Workflow script
  | 'monitor_mcp'      // prefix: 'm' - MCP monitoring
  | 'dream'            // prefix: 'd' - Dream consolidation
```

### 4. BriefTool (SendUserMessage)

**Tool Name**: `SendUserMessage` (alias: `Brief`)

**Purpose**: KAIROS can proactively message the user

**Input Schema**:
```typescript
type BriefToolInput = {
  message: string;      // Message to send
  status?: 'normal' | 'proactive';  // Message status
  attachments?: Array<{
    type: 'file' | 'image';
    path: string;
  }>;
}
```

**Behavior**:
- `status: 'proactive'` - Messages sent during idle time
- `status: 'normal'` - Regular messages
- Attachments can include files or images
- Requires `userMsgOptIn` or `kairosActive`

**Permission**: Always asks user (passthrough)

---

## Part 2: Multi-Agent Orchestration

### Agent Types

The reference architecture defines **4 agent roles**:

| Role | Description | Spawned By |
|------|-------------|------------|
| **Main Thread** | Primary interactive agent | User |
| **Subagent** | Worker agent for specific tasks | Main thread or coordinator |
| **Teammate** | Persistent agent in a team | Team lead |
| **Coordinator** | Orchestrates multiple workers | User (coordinator mode) |

### Agent Identification

```typescript
// In ToolUseContext
type ToolUseContext = {
  agentId?: AgentId;        // This agent's ID
  isSubagent?: boolean;     // True if spawned by another agent
  isCoordinator?: boolean;  // True if orchestrating workers
}
```

---

## AgentTool (Spawn Subagents)

**Tool Name**: `Agent` (alias: `Task`)

**Purpose**: Spawn subagents for parallel work

**Input Schema**:
```typescript
type AgentToolInput = {
  description: string;      // 3-5 word task description
  prompt: string;           // Full task prompt
  subagent_type?: string;   // 'fork' for fork subagent
  model?: 'sonnet' | 'opus' | 'haiku';  // Model alias
  run_in_background?: boolean;
  name?: string;            // Named agent for messaging
  team_name?: string;       // Associate with team
  mode?: string;            // Permission mode override
  isolation?: 'worktree' | 'remote';  // Isolation strategy
  cwd?: string;             // Working directory (KAIROS only)
}
```

**Output Schema**:
```typescript
type AgentToolOutput = {
  agent_id: AgentId;
  status: 'spawned' | 'queued';
  background_task_id?: string;
}
```

**Behavior**:
- Auto-backgrounds after 120_000ms (2 min)
- Progress shown after 2_000ms (2 sec)
- `subagent_type: 'fork'` - Creates fork subagent
- `isolation: 'worktree'` - Git worktree isolation
- `isolation: 'remote'` - Remote session execution
- `team_name` - Associates with agent swarm

**Isolation Strategies**:

#### 1. Worktree Isolation
```typescript
if (input.isolation === 'worktree') {
  // Create git worktree
  const worktreePath = await createWorktree(taskName);
  
  // Spawn agent in worktree
  const agent = await spawnAgent({
    cwd: worktreePath,
    env: { ...process.env, GIT_WORKTREE: worktreePath }
  });
  
  return { agent_id: agent.id, status: 'spawned' };
}
```

#### 2. Remote Isolation
```typescript
if (input.isolation === 'remote') {
  // Route via Remote Control API
  const session = await createRemoteSession({
    cwd: input.cwd,
    model: input.model
  });
  
  // Send prompt to remote session
  await sendToRemote(session.id, input.prompt);
  
  return { agent_id: session.id, status: 'spawned' };
}
```

---

## Team System (Agent Swarms)

### TeamCreateTool

**Tool Name**: `TeamCreate`

**Gate**: `isAgentSwarmsEnabled()`

**Purpose**: Create a team of agents working together

**Input Schema**:
```typescript
type TeamCreateInput = {
  team_name: string;        // Team name
  description?: string;     // Team description
  agent_type?: string;      // Default agent type for members
}
```

**Output Schema**:
```typescript
type TeamCreateOutput = {
  team_name: string;
  team_file_path: string;   // ~/.claude/teams/<team_name>.json
  lead_agent_id: AgentId;   // Team lead
}
```

**Behavior**:
- Creates team file at `~/.claude/teams/<team_name>.json`
- Resets task list to team-scoped task list
- Registers team for session cleanup
- **One team per leader** - calling again returns error

**Team File Format**:
```json
{
  "team_name": "refactoring-squad",
  "description": "Team for large-scale refactoring",
  "lead_agent_id": "agent_abc123",
  "members": [
    {
      "agent_id": "agent_def456",
      "name": "typescript-expert",
      "role": "worker",
      "status": "active"
    },
    {
      "agent_id": "agent_ghi789",
      "name": "test-writer",
      "role": "worker",
      "status": "idle"
    }
  ],
  "created_at": "2026-04-03T12:00:00Z"
}
```

### TeamDeleteTool

**Tool Name**: `TeamDelete`

**Input**: `{}` (empty object)

**Behavior**:
- Refuses if any non-lead members are still running
- Calls `cleanupTeamDirectories(teamName)`
- Unregisters team from session cleanup
- Clears teammate color assignments
- Clears leader team name (task list falls back to session ID)

### SendMessageTool

**Tool Name**: `SendMessage`

**Gate**: `isAgentSwarmsEnabled()`

**Purpose**: Send messages between agents/teammates

**Input Schema**:
```typescript
type SendMessageInput = {
  recipient: string;        // Agent name or team name
  message: string;          // Message content
  attachments?: Array<{
    type: 'file' | 'image';
    path: string;
  }>;
}
```

**Routing**:
1. **In-process agents**: Queue in agent's inbox or resume paused agent
2. **Mailbox (teammates)**: Write to `~/.claude/mailboxes/<name>.json`
3. **UDS socket**: Unix domain socket (local inter-process)
4. **Bridge (cross-machine)**: Remote Control API (requires user consent)

**Mailbox Format**:
```json
{
  "recipient": "typescript-expert",
  "messages": [
    {
      "from": "main-thread",
      "content": "Please review the auth module",
      "timestamp": "2026-04-03T12:00:00Z",
      "read": false
    }
  ]
}
```

**Permission**: Bridge messages require user consent

---

## Coordinator Mode (Multi-Worker Orchestration)

### What is Coordinator Mode?

**Coordinator mode** is where the agent orchestrates multiple parallel workers:

```
┌─────────────────┐
│   Coordinator   │
│  (Main Thread)  │
└────────┬────────┘
         │
    ┌────┼────┐
    │    │    │
    ▼    ▼    ▼
┌───────┐ ┌───────┐ ┌───────┐
│Worker1│ │Worker2│ │Worker3│
└───────┘ └───────┘ └───────┘
```

### Enabling Coordinator Mode

```typescript
// Env var + feature flag
HERMES_COORDINATOR_MODE=true
feature('COORDINATOR_MODE')  // GrowthBook flag
```

### Coordinator System Prompt

```markdown
You are a COORDINATOR orchestrating multiple worker agents.

## Your Role
- Break complex tasks into subtasks
- Assign subtasks to workers via Agent tool
- Monitor worker progress
- Synthesize worker outputs
- Ensure quality and completeness

## Available Tools
- Agent: Spawn worker agents
- SendMessage: Communicate with workers
- TaskStop: Stop misbehaving workers
- SyntheticOutput: Return structured results

## Workflow
1. **Research**: Understand the task
2. **Synthesis**: Plan the approach
3. **Implementation**: Assign subtasks
4. **Verification**: Review results

## Worker Prompt Guidelines
- Be specific and actionable
- Include success criteria
- Specify output format
- Set clear constraints

## Example Session

User: Refactor the authentication module to use JWT

Coordinator: I'll break this into parallel subtasks:

1. Research current auth implementation
2. Design JWT schema
3. Implement JWT utilities
4. Update auth endpoints
5. Write tests

Let me spawn workers for each subtask...

[spawns 5 Agent tools in parallel]
```

### Coordinator User Context

```typescript
function getCoordinatorUserContext(): { [k: string]: string } {
  return {
    workerToolsContext: `
Available worker tools:
- Agent: Spawn subagents
- SendMessage: Inter-agent messaging
- TaskStop: Stop workers

MCP Servers: ${mcpClients.map(c => c.name).join(', ')}

${scratchpadDir ? `Scratchpad: ${scratchpadDir}` : ''}
`.trim()
  };
}
```

### Mode Switching on Resume

```typescript
function matchSessionMode(
  sessionMode: 'coordinator' | 'normal' | undefined
): string | undefined {
  const currentMode = isCoordinatorMode() ? 'coordinator' : 'normal';
  
  if (currentMode !== sessionMode) {
    // Switch mode to match session
    if (sessionMode === 'coordinator') {
      process.env.HERMES_COORDINATOR_MODE = 'true';
    } else {
      delete process.env.HERMES_COORDINATOR_MODE;
    }
    
    // Log analytics
    logEvent('tengu_coordinator_mode_switched', {
      from: currentMode,
      to: sessionMode
    });
    
    return `Switched to ${sessionMode} mode to match session`;
  }
  
  return undefined; // No change needed
}
```

---

## Task Management (V2)

### Task Types

```typescript
type TaskType =
  | 'local_bash'       // Bash command (prefix: 'b')
  | 'local_agent'      // Local agent (prefix: 'a')
  | 'remote_agent'     // Remote agent (prefix: 'r')
  | 'in_process_teammate' // In-process teammate (prefix: 't')
  | 'local_workflow'   // Workflow script (prefix: 'w')
  | 'monitor_mcp'      // MCP monitoring (prefix: 'm')
  | 'dream'            // Dream consolidation (prefix: 'd')
```

### Task States

```typescript
type TaskStatus =
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'killed'
```

### TaskCreateTool (V2)

**Tool Name**: `TaskCreate`

**Gate**: `isTodoV2Enabled()`

**Input Schema**:
```typescript
type TaskCreateInput = {
  description: string;
  status?: 'pending' | 'in_progress' | 'completed' | 'failed';
  priority?: 'low' | 'medium' | 'high' | 'urgent';
  assignee?: string;    // Agent name
  due_date?: string;    // ISO 8601
  dependencies?: string[];  // Task IDs
}
```

**Output Schema**:
```typescript
type TaskCreateOutput = {
  task_id: string;
  status: string;
  message: string;
}
```

**Behavior**:
- Runs `executeTaskCreatedHooks` after creation
- Auto-expands task panel in UI
- Deletes task if hook throws error

### TaskGetTool (V2)

**Tool Name**: `TaskGet`

**Input Schema**:
```typescript
type TaskGetInput = {
  task_id: string;
}
```

**Output**:
```typescript
type TaskGetOutput = {
  task_id: string;
  description: string;
  status: string;
  priority: string;
  assignee?: string;
  due_date?: string;
  dependencies: string[];
  created_at: string;
  updated_at: string;
}
```

### TaskUpdateTool (V2)

**Tool Name**: `TaskUpdate`

**Input Schema**:
```typescript
type TaskUpdateInput = {
  task_id: string;
  description?: string;
  status?: string;
  priority?: string;
  assignee?: string;
  due_date?: string;
  dependencies?: string[];
}
```

**Behavior**:
- Writes mailbox notification on owner change
- `verificationNudgeNeeded`: set when 3+ tasks completed without verification

### TaskListTool (V2)

**Tool Name**: `TaskList`

**Input**: `{}` (empty object)

**Output**:
```typescript
type TaskListOutput = {
  tasks: Array<{
    task_id: string;
    description: string;
    status: string;
    priority: string;
    assignee?: string;
  }>;
}
```

### TaskStopTool

**Tool Name**: `TaskStop` (alias: `KillShell`)

**Input Schema**:
```typescript
type TaskStopInput = {
  task_id: string;
}
```

**Behavior**:
- Task must exist
- Task must be in running state (non-terminal)
- Kills background process
- Updates task state to 'killed'

### TaskOutputTool

**Tool Name**: `TaskOutput`

**Input Schema**:
```typescript
type TaskOutputInput = {
  task_id: string;
  filter?: string;  // Regex to filter output lines
}
```

**Output Schema**:
```typescript
type TaskOutputOutput = {
  retrieval_status: 'success' | 'timeout' | 'not_ready';
  task: {
    task_id: string;
    task_type: TaskType;
    status: TaskStatus;
    description: string;
    output: string;
  } | null;
}
```

---

## Part 3: Implementation for Hermes.C#

### KAIROS Service

```csharp
public sealed class KairosService : BackgroundService
{
    private static readonly TimeSpan SCAN_INTERVAL = TimeSpan.FromMinutes(10);
    private readonly ILogger<KairosService> _logger;
    
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(SCAN_INTERVAL, ct);
            
            if (!IsKairosActive()) continue;
            
            await LogDailySummaryAsync(ct);
            await ScanSessionsForDreamAsync(ct);
        }
    }
    
    private async Task LogDailySummaryAsync(CancellationToken ct)
    {
        var today = DateTime.Today;
        var logPath = GetDailyLogPath(today);
        
        Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
        
        var summary = new StringBuilder();
        summary.AppendLine($"# {today:yyyy-MM-dd}\n");
        
        var sessions = GetSessionsToday(today);
        summary.AppendLine("## Session Summary");
        summary.AppendLine($"- **Sessions**: {sessions.Count}");
        summary.AppendLine($"- **Tools Used**: {sessions.Sum(s => s.ToolCount)}");
        summary.AppendLine($"- **Files Changed**: {sessions.Sum(s => s.FilesChanged)}");
        
        var decisions = ExtractKeyDecisions(sessions);
        if (decisions.Any())
        {
            summary.AppendLine("- **Key Decisions**:\n");
            foreach (var decision in decisions)
            {
                summary.AppendLine($"  - {decision}");
            }
        }
        
        await File.AppendAllTextAsync(logPath, summary.ToString(), ct);
    }
}
```

### Agent Spawning

```csharp
public sealed class AgentService
{
    public async Task<AgentResult> SpawnAgentAsync(AgentRequest request, CancellationToken ct)
    {
        var agentId = GenerateAgentId();
        
        // Determine isolation strategy
        var isolation = request.Isolation switch
        {
            "worktree" => await CreateWorktreeIsolationAsync(request, ct),
            "remote" => await CreateRemoteIsolationAsync(request, ct),
            _ => IsolationStrategy.None
        };
        
        // Build agent context
        var context = new AgentContext
        {
            AgentId = agentId,
            Prompt = request.Prompt,
            Model = request.Model ?? "default",
            WorkingDirectory = isolation.WorkingDirectory ?? Environment.CurrentDirectory,
            IsSubagent = true,
            ParentAgentId = _currentAgentId
        };
        
        // Spawn agent
        var agent = new AgentRunner(context, _serviceProvider);
        
        if (request.RunInBackground)
        {
            _ = agent.RunAsync(ct); // Fire and forget
            return new AgentResult { AgentId = agentId, Status = "spawned" };
        }
        else
        {
            var result = await agent.RunAsync(ct);
            return new AgentResult 
            { 
                AgentId = agentId, 
                Status = "completed",
                Output = result.Output
            };
        }
    }
    
    private async Task<IsolationStrategy> CreateWorktreeIsolationAsync(
        AgentRequest request, CancellationToken ct)
    {
        var worktreeName = $"agent-{Guid.NewGuid():N}";
        var worktreePath = Path.Combine(".git", "worktrees", worktreeName);
        
        // Create worktree
        await RunBashAsync($"git worktree add {worktreePath}", ct);
        
        return new IsolationStrategy
        {
            WorkingDirectory = worktreePath,
            Cleanup = async () =>
            {
                await RunBashAsync($"git worktree remove {worktreePath}", ct);
            }
        };
    }
}
```

### Team Management

```csharp
public sealed class TeamManager
{
    private readonly string _teamsDir;
    
    public async Task<TeamResult> CreateTeamAsync(TeamCreateRequest request, CancellationToken ct)
    {
        var teamPath = Path.Combine(_teamsDir, $"{request.TeamName}.json");
        
        if (File.Exists(teamPath))
        {
            throw new TeamAlreadyExistsException(request.TeamName);
        }
        
        var team = new Team
        {
            TeamName = request.TeamName,
            Description = request.Description,
            LeadAgentId = _currentAgentId,
            Members = new List<TeamMember>(),
            CreatedAt = DateTime.UtcNow
        };
        
        var json = JsonSerializer.Serialize(team, JsonOptions);
        await File.WriteAllTextAsync(teamPath, json, ct);
        
        return new TeamResult
        {
            TeamName = request.TeamName,
            TeamFilePath = teamPath,
            LeadAgentId = _currentAgentId
        };
    }
    
    public async Task SendMessageAsync(SendMessageRequest request, CancellationToken ct)
    {
        var mailboxPath = Path.Combine(_mailboxDir, $"{request.Recipient}.json");
        
        var message = new MailboxMessage
        {
            From = _currentAgentId,
            Content = request.Message,
            Timestamp = DateTime.UtcNow,
            Read = false
        };
        
        // Append to mailbox
        var mailbox = await LoadMailboxAsync(mailboxPath, ct);
        mailbox.Messages.Add(message);
        await SaveMailboxAsync(mailboxPath, mailbox, ct);
    }
}
```

### Cron Scheduler

```csharp
public sealed class CronScheduler : BackgroundService
{
    private readonly ConcurrentDictionary<string, CronJob> _jobs = new();
    
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var now = DateTime.Now;
            
            foreach (var (jobId, job) in _jobs)
            {
                if (CronExpression.Matches(job.Expression, now))
                {
                    await RunJobAsync(job, ct);
                }
            }
            
            await Task.Delay(TimeSpan.FromMinutes(1), ct);
        }
    }
    
    public async Task<string> CreateJobAsync(CronJobRequest request, CancellationToken ct)
    {
        if (_jobs.Count >= 50)
        {
            throw new MaxJobsExceededException(50);
        }
        
        // Validate cron expression
        if (!CronExpression.IsValid(request.Expression))
        {
            throw new InvalidCronExpressionException(request.Expression);
        }
        
        // Must match at least one date in next year
        if (!CronExpression.MatchesWithinYear(request.Expression))
        {
            throw new CronNoMatchesException(request.Expression);
        }
        
        var jobId = Guid.NewGuid().ToString("N");
        var job = new CronJob
        {
            Id = jobId,
            Expression = request.Expression,
            Command = request.Command,
            AgentId = _currentAgentId,
            CreatedAt = DateTime.UtcNow
        };
        
        _jobs[jobId] = job;
        await SaveJobsAsync(ct);
        
        return jobId;
    }
}
```

---

## Summary

### KAIROS Key Points
- **Proactive assistant** - observes and acts during idle time
- **Daily logs** - append-only records in `memory/logs/YYYY/MM/YYYY-MM-DD.md`
- **Dream system** - background memory consolidation every 10 min
- **Cron scheduling** - recurring tasks with 5-field cron expressions
- **BriefTool** - proactive user messaging

### Multi-Agent Key Points
- **4 agent roles** - Main thread, Subagent, Teammate, Coordinator
- **AgentTool** - spawn subagents with worktree/remote isolation
- **Team system** - persistent agent swarms with mailboxes
- **SendMessage** - inter-agent messaging via inbox/mailbox/UDS/bridge
- **Coordinator mode** - orchestrate multiple parallel workers
- **Task V2** - full task management (create/get/update/list/stop/output)

### Implementation Priorities
1. ✅ Basic agent spawning
2. ✅ Worktree isolation
3. ⬜ Team management
4. ⬜ Mailbox system
5. ⬜ Coordinator mode
6. ⬜ KAIROS daily logs
7. ⬜ Dream consolidation
8. ⬜ Cron scheduler

---

**Next Step**: Implement agent spawning with worktree isolation!
