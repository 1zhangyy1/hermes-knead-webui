# Hermes.C# Tools Implementation Status

## ✅ Implemented Tools (6/19)

### Shell Execution
1. **bash** ✅ - Shell command execution with timeout, background support, proper Windows console
   - File: `src/Tools/BashTool.cs`
   - Features: cmd.exe/PowerShell detection, console window creation, timeout, background mode
   - **FIXES the "No Windows console found" error from Python Hermes!**

### File Operations
2. **read_file** ✅ - Read files with offset/limit
   - File: `src/Tools/ReadFileTool.cs`
   - Features: Text files, images (placeholder), PDFs (placeholder), Jupyter notebooks
   - Output: `cat -n` format with line numbers

3. **write_file** ✅ - Create/overwrite files
   - File: `src/Tools/WriteFileTool.cs`
   - Features: Directory creation, structured patch output
   - Output: JSON with status, action, path, lines, structured_patch

4. **edit_file** ✅ - Precise string replacement
   - File: `src/Tools/EditFileTool.cs`
   - Features: Uniqueness validation, replace_all option, diff output
   - Safety: Fails if multiple occurrences found without replace_all

### Search & Discovery
5. **glob** ✅ - File pattern matching
   - File: `src/Tools/GlobTool.cs`
   - Features: Glob patterns (**/*.cs), recursive search, sorted by mtime
   - Limit: 100 files max

6. **grep** ✅ - Content search with ripgrep
   - File: `src/Tools/GrepTool.cs`
   - Features: ripgrep integration, regex support, multiple output modes
   - Modes: files_with_matches, content, count
   - **Auto-detects ripgrep installation**

---

## 📋 Remaining Tools (13/19)

### File Operations (1 more)
- [ ] **notebook_edit** - Jupyter notebook cell editing

### Search & Discovery (2 more)
- [ ] **ls** - List directory contents
- [ ] **ToolSearch** - Deferred tool discovery

### Web (2 tools)
- [ ] **WebFetch** - Fetch URL content
- [ ] **WebSearch** - Web search with domain filtering

### Task Management (2 tools)
- [ ] **TodoWrite** - Task list management
- [ ] **TodoRead** - Read current todo list

### Agent & Skills (3 tools)
- [ ] **Agent** - Launch sub-agents
- [ ] **Skill** - Load skill definitions
- [ ] **Config** - Get/set agent configuration

### Utilities (3 tools)
- [ ] **Sleep** - Wait without holding shell
- [ ] **SendUserMessage** - Message user with attachments
- [ ] **StructuredOutput** - Return machine-parseable JSON

### Windows-Specific
- [ ] **PowerShell** - Windows-native shell (could merge with bash tool)

---

## 🔧 Tool Architecture

### ITool Interface
```csharp
public interface ITool
{
    string Name { get; }
    string Description { get; }
    Type ParametersType { get; }
    Task<ToolResult> ExecuteAsync(object parameters, CancellationToken ct);
}
```

### Tool Registration
Tools are registered in Program.cs via dependency injection:
```csharp
services.AddSingleton<ITool, BashTool>();
services.AddSingleton<ITool, ReadFileTool>();
services.AddSingleton<ITool, WriteFileTool>();
services.AddSingleton<ITool, EditFileTool>();
services.AddSingleton<ITool, GlobTool>();
services.AddSingleton<ITool, GrepTool>();
```

### ToolResult Pattern
```csharp
public sealed class ToolResult
{
    public bool Success { get; init; }
    public required string Content { get; init; }
    public Exception? Error { get; init; }
    
    public static ToolResult Ok(string content) => new() { Success = true, Content = content };
    public static ToolResult Fail(string error, Exception? ex = null) => new() { Success = false, Content = error, Error = ex };
}
```

---

## 🎯 Key Improvements vs Python Hermes

### 1. **Native Windows Console Support**
The BashTool explicitly creates console windows:
```csharp
CreateNoWindow = false  // Give it a console window
```
This **fixes the "No Windows console found" error** from Python Hermes!

### 2. **Type Safety**
All tools have strongly-typed parameter classes:
```csharp
public sealed class BashParameters
{
    public required string Command { get; init; }
    public string? WorkingDirectory { get; init; }
    public int TimeoutMs { get; init; } = 120000;
    public bool RunInBackground { get; init; }
    public string? Description { get; init; }
}
```

### 3. **Async First**
All I/O is async with proper CancellationToken support

### 4. **Better Error Handling**
ToolResult pattern provides clear success/failure semantics

---

## 📊 Comparison with Claw Code

| Feature | Claw Code (Python/Rust) | Hermes.C# |
|---------|------------------------|-----------|
| **Languages** | Python 27%, Rust 73% | 100% C# |
| **Tools** | 19 built-in | 6 implemented, 13 planned |
| **Shell** | bash + PowerShell | bash (PowerShell auto-detect) |
| **File Ops** | read, write, edit, glob | ✅ All 4 implemented |
| **Search** | grep (ripgrep), ls | ✅ grep, glob (ls planned) |
| **Web** | WebFetch, WebSearch | ❌ Not yet |
| **Tasks** | TodoWrite, TodoRead | ❌ Not yet |
| **Agent** | Agent, Skill, Config | ❌ Not yet |
| **Utilities** | Sleep, SendUserMessage, StructuredOutput | ❌ Not yet |
| **Permissions** | 3-tier (ReadOnly, WorkspaceWrite, DangerFullAccess) | ❌ Not yet |
| **Sandbox** | Yes (configurable) | ❌ Not yet |

---

## 🚀 Next Steps

### Priority 1: Core Workflow Tools
1. **ls** - Directory listing (needed for exploration)
2. **WebFetch** - Fetch URLs (needed for docs/API calls)
3. **TodoWrite/TodoRead** - Task tracking (needed for multi-step work)

### Priority 2: Agent Features
4. **Agent** - Sub-agent spawning
5. **Skill** - Skill loading
6. **Config** - Configuration management

### Priority 3: Polish
7. **StructuredOutput** - Machine-readable responses
8. **SendUserMessage** - User communication
9. **Sleep** - Background waiting
10. **Permissions** - Permission system
11. **Sandbox** - Command sandboxing

---

## 📝 Notes

### Ripgrep Dependency
The grep tool requires ripgrep (`rg`) to be installed. Auto-detection checks:
- PATH environment variable
- `C:\Program Files\ripgrep\rg.exe`
- `C:\Program Files (x86)\ripgrep\rg.exe`
- Scoop installation

### Console Window Fix
The key fix for Python Hermes' "No Windows console found" error:
```csharp
CreateNoWindow = false  // NOT true!
```
This gives bash commands a real console window, which Windows LLM SDKs need.

### Future Enhancements
- **libgit2sharp** integration for real git diffs in write_file
- **Microsoft.Playwright** for browser automation
- **Microsoft.Extensions.FileSystemGlobbing** for proper glob matching
- **System.Security.Principal** for sandbox enforcement
- **Windows Job Objects** for process isolation

---

**Created**: 2026-04-03  
**Status**: 6/19 tools implemented (32%)  
**Build**: ✅ Successful
