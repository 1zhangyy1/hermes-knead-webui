# Agent Architecture Deep Dive - Key Learnings for Hermes.C#

**Source**: Reference architecture analysis
**Date**: 2026-04-03
**Purpose**: Capture critical implementation details for Hermes.C# tools

---

## 🎯 Critical Discoveries

### 1. **Tool Interface Design** (from `spec/03_tools.md`)

The `Tool<TInput, TOutput, TProgress>` interface is the foundation:

```typescript
type Tool<Input, Output, Progress> = {
  // Identity
  name: string
  isMcp?: boolean
  mcpInfo?: { serverName: string; toolName: string }
  isLsp?: boolean
  alwaysLoad?: boolean
  shouldDefer?: boolean

  // Schema
  readonly inputSchema: ZodType<Input>
  readonly outputSchema?: ZodType<Output>

  // Metadata
  description(): Promise<string>
  prompt(): Promise<string>
  userFacingName(input?: Input): string
  maxResultSizeChars?: number
  searchHint?: string

  // Capability flags
  isEnabled(permissionContext?: ToolPermissionContext): boolean
  isConcurrencySafe(input?: Input): boolean
  isReadOnly(input?: Input): boolean
  isDestructive?(input: Input): boolean
  toAutoClassifierInput(input: Input): string
  isSearchOrReadCommand?: (input: Input) => { isSearch: boolean; isRead: boolean }

  // Execution
  validateInput?(input: Input): Promise<ValidationResult>
  checkPermissions(input: Input, context: ToolUseContext): Promise<PermissionDecision>
  call(input: Input, context: ToolUseContext): Promise<ToolResult<Output>>

  // UI rendering (React/Ink)
  renderToolUseMessage(input: Input, options: RenderOptions): ReactNode | null
  renderToolUseProgressMessage?(progress: Progress, input?: Input): ReactNode | null
  renderToolResultMessage(output: Output): ReactNode | null

  // Output mapping
  mapToolResultToToolResultBlockParam(
    output: Output,
    toolUseID: string,
    context: ToolUseContext,
  ): ToolResultBlockParam

  // Path tracking (for permission rules)
  getPath?(input?: Input): string | undefined
}
```

**Key insight**: Every tool has:
- **Input/output schemas** (Zod validation)
- **Permission checking** (`checkPermissions`)
- **Execution** (`call`)
- **UI rendering** (React components for terminal)
- **Capability flags** (readOnly, concurrencySafe, destructive)

---

### 2. **Permission System** (from `spec/05_components_agents_permissions_design.md`)

#### PermissionDecision Type
```typescript
type PermissionDecision =
  | { behavior: 'allow'; updatedInput: Input }
  | { behavior: 'ask'; message: string; decisionReason?: string }
  | { behavior: 'deny'; message: string }
```

#### ToolPermissionContext
```typescript
type ToolPermissionContext = {
  mode: PermissionMode  // 'default' | 'plan' | 'auto' | 'bypassPermissions' | 'acceptEdits'
  alwaysAllow: PermissionRule[]
  alwaysDeny: PermissionRule[]
  alwaysAsk: PermissionRule[]
  additionalWorkingDirectories: string[]
  toolPermissions: Record<string, ToolPermissionOverride>
}

type PermissionMode =
  | 'default'      // Always ask
  | 'plan'         // Read-only planning mode
  | 'auto'         // Auto-approve read-only, ask for writes
  | 'bypassPermissions'  // Allow everything (dangerous!)
  | 'acceptEdits'  // Auto-approve edits in workspace
```

#### Permission Rules
Rules use a DSL like:
- `Bash(git *)` - Allow git commands
- `Bash(npm test)` - Allow npm test
- `Write(**/*.cs)` - Allow writing C# files
- `Read(src/**)` - Allow reading from src/

**Implementation**: Pattern matching against tool name + input

---

### 3. **BashTool Deep Dive** (from `spec/03_tools.md`)

#### Input Schema
```typescript
type BashToolInput = {
  command: string
  timeout?: number  // Max 600000ms (10 min)
  description?: string  // 5-10 word description
  run_in_background?: boolean
  dangerouslyDisableSandbox?: boolean
}
```

#### Output Schema
```typescript
type BashToolOutput = {
  stdout: string
  stderr: string
  exitCode: number
  interrupted?: boolean  // Killed due to timeout
  backgroundTaskId?: string  // When run_in_background=true
  backgroundedByUser?: boolean  // User pressed Ctrl+B
  assistantAutoBackgrounded?: boolean  // Auto-backgrounded after blocking budget
  dangerouslyDisableSandbox?: boolean
  returnCodeInterpretation?: string  // Semantic meaning of exit code
  noOutputExpected?: boolean
  structuredContent?: unknown
}
```

#### Sandbox Implementation
- **Linux**: `bwrap` (bubblewrap) based isolation
- **macOS**: `sandbox-exec` based isolation
- **Windows**: Windows Sandbox backend (`WindowsSandbox.exe` + generated `.wsb`) for local OS-provided isolation
- **Enterprise policy**: If sandbox required and unavailable → execution blocked

#### Auto-Background Thresholds
- `AUTO_BACKGROUND_THRESHOLD_MS: 120_000` (2 min)
- `ASSISTANT_BLOCKING_BUDGET_MS: 15_000` (15s in assistant mode)
- `PROGRESS_THRESHOLD_MS: 2_000` (show progress after 2s)

#### Blocked Patterns
```typescript
function detectBlockedSleepPattern(command: string): string | null
// Detects bare `sleep N` commands with N>=2 as first statement
// Suggests using SleepTool instead
```

#### Permission Behavior
- `bypassPermissions` mode: allows all commands
- `auto`/`acceptEdits` mode: auto-approve read-only, ask for writes
- `default` mode: always asks unless explicitly allowed

#### Search/Read Classification
```typescript
function isSearchOrReadBashCommand(command: string): { isSearch: boolean; isRead: boolean }
// Used to classify bash commands as "safe" read operations
// Examples: `cat file.txt`, `ls -la`, `rg pattern`
```

---

### 4. **PowerShellTool** (Windows-specific)

Mirrors BashTool but for PowerShell:

```typescript
type PowerShellToolInput = {
  command: string
  timeout?: number
  description?: string
  run_in_background?: boolean
  dangerouslyDisableSandbox?: boolean
}
```

#### PowerShell-Specific Features
- `PS_SEARCH_COMMANDS`: `Select-String`, `Get-ChildItem`, `FindStr`, `where.exe`
- `PS_READ_COMMANDS`: `Get-Content`, `Get-Item`, `Test-Path`, `Resolve-Path`, `Get-Process`
- `PS_SEMANTIC_NEUTRAL_COMMANDS`: `Write-Output`, `Write-Host`
- `detectBlockedSleepPattern()`: catches `Start-Sleep N`, `sleep N`
- `DISALLOWED_AUTO_BACKGROUND_COMMANDS`: `['start-sleep', 'sleep']`

#### Windows Sandbox Issue
> Windows-native sandbox policy: prefer the Windows Sandbox backend when the optional Windows feature is available; otherwise execution is blocked when sandboxing is required.

**Windows note** - Windows does not have the same process-level sandboxing as Linux/macOS, so Hermes uses Windows Sandbox as a local VM-backed isolation boundary.

---

### 5. **File Tools**

#### FileReadTool
```typescript
type FileReadToolInput = {
  file_path: string  // Absolute path
  offset?: number    // Line number to start from
  limit?: number     // Number of lines to read
}
```

**Special handling**:
- Images (PNG, JPG): Presented visually to multimodal LLM
- PDFs: Processed page by page
- `.ipynb` files: Redirected to NotebookEditTool
- Large files: Default 2000 lines, truncates at 30000 chars

#### FileWriteTool
```typescript
type FileWriteToolInput = {
  file_path: string  // Absolute path
  content: string    // Complete file content
}
```

**Safety checks**:
1. Read-before-write enforcement (tracks `readFileState`)
2. Directory creation if needed
3. Team memory protection (blocks writes to secret files)
4. Deny rules check
5. LF line endings (platform-independent)
6. LSP client notification on success

#### FileEditTool
```typescript
type FileEditToolInput = {
  file_path: string
  old_string: string
  new_string: string
  replace_all?: boolean
}
```

**Key features**:
- Uniqueness validation (fails if multiple occurrences)
- Quote normalization (`findActualString()` handles straight/curly quotes)
- Preserve quote style (`preserveQuoteStyle()`)
- LSP client notification

---

### 6. **Search Tools**

#### GlobTool
```typescript
type GlobToolInput = {
  pattern: string  // e.g., "**/*.ts", "src/**/*.rs"
  path?: string    // Directory to search (defaults to CWD)
}
```

**Behavior**:
- Returns files sorted by modification time
- Truncates at 100 files
- Works with any codebase size
- Faster than `bash find`

#### GrepTool
```typescript
type GrepToolInput = {
  pattern: string   // Ripgrep regex
  path?: string     // Directory to search
  include?: string  // File pattern (e.g., "*.js")
  output_mode?: 'content' | 'files_with_matches' | 'count'
  -B?: number       // Lines before match
  -A?: number       // Lines after match
  -C?: number       // Lines before/after
  -i?: boolean      // Case insensitive
  -n?: boolean      // Show line numbers
  type?: string     // File type (js, py, rust, go, java)
  head_limit?: number  // Limit results
  offset?: number   // Skip first N
  multiline?: boolean
}
```

**Built on ripgrep** - modern agentic systems typically bundle `rg`

---

### 7. **Agent/Multi-Agent Tools**

#### AgentTool
```typescript
type AgentToolInput = {
  prompt: string
  description?: string  // 3-5 words
  run_in_background?: boolean
  name?: string         // Named agent for messaging
  team_name?: string    // Associate with team
  mode?: string         // Permission mode override
  isolation?: 'worktree' | 'remote'
  cwd?: string          // Working directory (Kairos only)
}
```

**Isolation strategies**:
- `worktree`: Git worktree isolation
- `remote`: Remote execution (requires safety check)

#### Task Management (V2)
- `TaskCreate` - Create a task
- `TaskGet` - Get task details
- `TaskUpdate` - Update task
- `TaskList` - List all tasks
- `TaskStop` - Stop running task
- `TaskOutput` - Get task output

Replaces TodoWrite/TodoRead for complex workflows

---

### 8. **Special Systems**

#### KAIROS Mode
A continuously-running proactive assistant mode:
- Observes development environment
- Takes autonomous action during idle time
- Backed by append-only log system
- Hidden from external builds

#### ULTRAPLAN Mode
- Offloads complex planning to remote cloud container
- Runs Opus-class model
- Allocates up to 30 minutes of reasoning time
- Browser-based approval workflows

#### Buddy System (Tamagotchi!)
- Deterministic gacha system
- Species rarity, shiny variants
- Procedurally generated stats
- Mulberry32 PRNG seeded from userId
- Same user always gets same buddy

---

### 9. **Tool Execution Flow**

```
1. User sends message
2. LLM selects tool + generates input
3. Tool execution pipeline:
   a. validateInput() - Schema validation
   b. checkPermissions() - Permission check
      - If 'deny' → return error
      - If 'ask' → show UI dialog, wait for user
      - If 'allow' → continue
   c. onPermissionRequest() callback
   d. onToolCallStart() hook
   e. call() - Execute tool
   f. onToolCallEnd() hook
   g. renderToolResultMessage() - Format output
   h. mapToolResultToToolResultBlockParam() - Convert for LLM
4. Return result to LLM
5. LLM continues conversation
```

---

### 10. **Shared Utilities**

#### Git Operation Tracking
```typescript
function trackGitOperations(
  command: string,
  exitCode: number,
  startTime: number,
  endTime: number,
): void
```
- Fires analytics events
- Tracks OTLP counters
- Works for both BashTool and PowerShellTool

#### Read-Before-Write Enforcement
```typescript
type ReadFileState = Map<string, { mtime: number; content: string }>
```
- Tracks which files were read before editing
- Enforced in FileWriteTool/FileEditTool
- Prevents accidental overwrites

---

## 🚀 Implementation Priorities for Hermes.C#

### Phase 1: Core Tools (DONE ✅)
- [x] BashTool (with Windows console fix)
- [x] ReadFileTool
- [x] WriteFileTool
- [x] EditFileTool
- [x] GlobTool
- [x] GrepTool

### Phase 2: Permission System (NEXT)
- [ ] ToolPermissionContext
- [ ] PermissionDecision type
- [ ] PermissionRule DSL
- [ ] checkPermissions() implementation
- [ ] Permission modes (default, auto, bypass, acceptEdits)

### Phase 3: Advanced Tools
- [ ] PowerShellTool (Windows-native)
- [ ] AgentTool (sub-agent spawning)
- [ ] TaskCreate/Get/Update/List (V2 task system)
- [ ] WebFetchTool
- [ ] WebSearchTool
- [ ] NotebookEditTool
- [ ] ToolSearchTool

### Phase 4: Special Features
- [ ] Read-before-write enforcement
- [ ] Git operation tracking
- [ ] Auto-background thresholds
- [ ] Progress reporting
- [ ] LSP integration
- [ ] MCP client

### Phase 5: Polish
- [ ] Sandbox abstraction (Windows Job Objects?)
- [ ] UI rendering (terminal UI?)
- [ ] Analytics/telemetry
- [ ] KAIROS-like proactive mode
- [ ] Buddy system (for fun!)

---

## 📝 Key Design Patterns to Copy

### 1. **Tool Interface with Generics**
```csharp
public interface ITool<in TIn, out TOut>
{
    string Name { get; }
    JsonElement InputSchema { get; }  // Or use System.Text.Json schema gen
    Task<ToolResult<TOut>> CallAsync(TIn input, ToolUseContext context);
    Task<PermissionDecision> CheckPermissionsAsync(TIn input, ToolPermissionContext permCtx);
    bool IsReadOnly(TIn input);
    bool IsConcurrencySafe(TIn input);
}
```

### 2. **Permission Decision Flow**
```csharp
public enum PermissionBehavior { Allow, Ask, Deny }

public sealed class PermissionDecision
{
    public PermissionBehavior Behavior { get; init; }
    public object? UpdatedInput { get; init; }  // For input modification
    public string? Message { get; init; }
    public string? DecisionReason { get; init; }
}
```

### 3. **Tool Use Context**
```csharp
public sealed class ToolUseContext
{
    public CancellationToken CancellationToken { get; init; }
    public ToolPermissionContext PermissionContext { get; init; }
    public string WorkingDirectory { get; init; }
    public Dictionary<string, object> AppState { get; init; }
    public Func<PermissionRequest, Task<PermissionDecision>> OnPermissionRequest { get; init; }
    public Action<string, object> OnToolCallStart { get; init; }
    public Action<string, object> OnToolCallEnd { get; init; }
}
```

### 4. **Auto-Background Pattern**
```csharp
private const int AUTO_BACKGROUND_THRESHOLD_MS = 120_000;
private const int PROGRESS_THRESHOLD_MS = 2_000;

if (elapsedMs > AUTO_BACKGROUND_THRESHOLD_MS)
{
    return AutoBackground(command);
}
else if (elapsedMs > PROGRESS_THRESHOLD_MS)
{
    ShowProgress(command);
}
```

---

## 🔒 Security Considerations

### Windows Sandbox
The reference architecture originally had **no sandbox on Windows**. Hermes.C# now supports a Windows Sandbox backend and can still evaluate other Windows-native boundaries:
1. **Windows Sandbox** - Built-in local VM-backed sandbox using generated `.wsb` configs
2. **Windows Job Objects** - Process isolation, resource limits
3. **AppContainer** - Windows Store app sandboxing (complex)
4. **Hyper-V containers** - Heavy but secure

### Permission System is Critical
When OS-level sandboxing is unavailable or disabled, the permission system becomes the primary security boundary:
- Conservative defaults (ask before executing)
- Pattern-based rules (allow `git *` but ask for `rm *`)
- Path-based restrictions (only allow writes in workspace)
- Read-before-write enforcement

---

## Reference Materials

### Core Specifications
- Tool system design - Complete tool specifications
- Components, agents, and permissions design - Permission UI design
- Constants and type definitions

### Architecture Reference
- Core entry and query pipeline
- Services, context, and state management
- Implementation notes

---

**Next Step**: Implement the permission system and advanced tools based on these specs!
