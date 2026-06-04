namespace Hermes.Agent.Execution;

using System.Diagnostics;
using System.Security;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

/// <summary>
/// Windows Sandbox execution backend.
/// Uses the built-in Windows Sandbox optional feature through generated .wsb files.
/// </summary>
public sealed class WindowsSandboxBackend : IExecutionBackend
{
    private const string ControlFolderInSandbox = @"C:\HermesControl";
    private const string WorkspaceFolderInSandbox = @"C:\HermesWorkspace";
    private readonly ExecutionConfig _config;

    public WindowsSandboxBackend(ExecutionConfig config) => _config = config;
    public ExecutionBackendType Type => ExecutionBackendType.WindowsSandbox;

    public async Task<ExecutionResult> ExecuteAsync(
        string command,
        string? workingDirectory,
        int? timeoutMs,
        bool background,
        CancellationToken ct)
    {
        if (!OperatingSystem.IsWindows())
        {
            return new ExecutionResult
            {
                Output = "Windows Sandbox backend is only available on Windows.",
                ExitCode = 1,
                DurationMs = 0,
                Error = "Unsupported OS"
            };
        }

        var sandboxExe = FindWindowsSandboxExecutable();
        if (sandboxExe is null)
        {
            return new ExecutionResult
            {
                Output = "Windows Sandbox is not available. Enable the 'Windows Sandbox' optional feature and restart Windows.",
                ExitCode = 1,
                DurationMs = 0,
                Error = "WindowsSandbox.exe not found"
            };
        }

        var timeout = timeoutMs ?? _config.DefaultTimeoutMs;
        var sw = Stopwatch.StartNew();
        var runId = "hermes-wsb-" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var sessionDir = Path.Combine(Path.GetTempPath(), "Hermes", "WindowsSandbox", runId);
        Directory.CreateDirectory(sessionDir);

        var workspace = ResolveWorkspace(workingDirectory);
        var commandPath = Path.Combine(sessionDir, "command.txt");
        var scriptPath = Path.Combine(sessionDir, "run.ps1");
        var resultPath = Path.Combine(sessionDir, "result.json");
        var wsbPath = Path.Combine(sessionDir, "Hermes.WindowsSandbox.wsb");

        await File.WriteAllTextAsync(commandPath, command, Encoding.UTF8, ct);
        await File.WriteAllTextAsync(scriptPath, BuildRunnerScript(), new UTF8Encoding(false), ct);
        await File.WriteAllTextAsync(
            wsbPath,
            BuildSandboxConfiguration(
                sessionDir,
                workspace,
                _config.WindowsSandboxReadOnlyWorkspace,
                _config.WindowsSandboxNetworking,
                _config.WindowsSandboxVGpu),
            new UTF8Encoding(false),
            ct);

        var psi = new ProcessStartInfo
        {
            FileName = sandboxExe,
            Arguments = $"\"{wsbPath}\"",
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using var sandboxProcess = Process.Start(psi);
        if (sandboxProcess is null)
        {
            return new ExecutionResult
            {
                Output = "Failed to start Windows Sandbox.",
                ExitCode = 1,
                DurationMs = sw.ElapsedMilliseconds,
                Error = "Process.Start returned null"
            };
        }

        if (background)
        {
            sw.Stop();
            return new ExecutionResult
            {
                Output = $"Windows Sandbox launched. Session: {sessionDir}",
                ExitCode = 0,
                DurationMs = sw.ElapsedMilliseconds,
                BackgroundProcessId = sandboxProcess.Id.ToString()
            };
        }

        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeoutCts.CancelAfter(timeout);

        try
        {
            while (!File.Exists(resultPath))
            {
                await Task.Delay(500, timeoutCts.Token);
            }

            var resultJson = await File.ReadAllTextAsync(resultPath, timeoutCts.Token);
            var result = JsonSerializer.Deserialize<SandboxCommandResult>(resultJson) ?? new SandboxCommandResult();
            sw.Stop();

            var output = string.IsNullOrWhiteSpace(result.Output) ? "(no output)" : result.Output;
            output = OutputTruncator.Truncate(output, _config.MaxOutputChars);

            return new ExecutionResult
            {
                Output = output,
                ExitCode = result.ExitCode,
                ExitCodeMeaning = ExitCodeInterpreter.Interpret(command, result.ExitCode),
                DurationMs = sw.ElapsedMilliseconds
            };
        }
        catch (OperationCanceledException)
        {
            sw.Stop();
            return new ExecutionResult
            {
                Output = $"Windows Sandbox command timed out after {timeout}ms. Session files remain at: {sessionDir}",
                ExitCode = 124,
                ExitCodeMeaning = "Timed out",
                DurationMs = sw.ElapsedMilliseconds
            };
        }
    }

    public ValueTask DisposeAsync() => ValueTask.CompletedTask;

    public static string BuildSandboxConfiguration(
        string controlHostFolder,
        string workspaceHostFolder,
        bool readOnlyWorkspace,
        bool networking,
        bool vgpu)
    {
        return $"""
            <Configuration>
              <VGpu>{(vgpu ? "Enable" : "Disable")}</VGpu>
              <Networking>{(networking ? "Enable" : "Disable")}</Networking>
              <MappedFolders>
                <MappedFolder>
                  <HostFolder>{EscapeXml(controlHostFolder)}</HostFolder>
                  <SandboxFolder>{ControlFolderInSandbox}</SandboxFolder>
                  <ReadOnly>false</ReadOnly>
                </MappedFolder>
                <MappedFolder>
                  <HostFolder>{EscapeXml(workspaceHostFolder)}</HostFolder>
                  <SandboxFolder>{WorkspaceFolderInSandbox}</SandboxFolder>
                  <ReadOnly>{(readOnlyWorkspace ? "true" : "false")}</ReadOnly>
                </MappedFolder>
              </MappedFolders>
              <LogonCommand>
                <Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File {ControlFolderInSandbox}\run.ps1</Command>
              </LogonCommand>
            </Configuration>
            """;
    }

    private string ResolveWorkspace(string? workingDirectory)
    {
        var configured = _config.WindowsSandboxMappedWorkspace;
        var workspace = string.IsNullOrWhiteSpace(configured)
            ? workingDirectory
            : configured;

        workspace = string.IsNullOrWhiteSpace(workspace)
            ? Directory.GetCurrentDirectory()
            : workspace;

        var fullPath = Path.GetFullPath(Environment.ExpandEnvironmentVariables(workspace));
        if (!Directory.Exists(fullPath))
        {
            throw new DirectoryNotFoundException($"Windows Sandbox workspace does not exist: {fullPath}");
        }

        return fullPath;
    }

    private static string? FindWindowsSandboxExecutable()
    {
        var systemRoot = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        var candidates = new[]
        {
            Path.Combine(systemRoot, "System32", "WindowsSandbox.exe"),
            Path.Combine(systemRoot, "Sysnative", "WindowsSandbox.exe")
        };

        return candidates.FirstOrDefault(File.Exists);
    }

    private static string BuildRunnerScript()
    {
        return """
            $ErrorActionPreference = 'Continue'
            $control = 'C:\HermesControl'
            $workspace = 'C:\HermesWorkspace'
            $commandFile = Join-Path $control 'command.txt'
            $stdoutFile = Join-Path $control 'stdout.txt'
            $stderrFile = Join-Path $control 'stderr.txt'
            $resultFile = Join-Path $control 'result.json'
            $command = Get-Content -LiteralPath $commandFile -Raw

            if (Test-Path -LiteralPath $workspace) {
                Set-Location -LiteralPath $workspace
            } else {
                Set-Location -LiteralPath $control
            }

            $process = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d', '/s', '/c', $command) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
            $stdout = if (Test-Path -LiteralPath $stdoutFile) { Get-Content -LiteralPath $stdoutFile -Raw } else { '' }
            $stderr = if (Test-Path -LiteralPath $stderrFile) { Get-Content -LiteralPath $stderrFile -Raw } else { '' }
            $output = if ([string]::IsNullOrEmpty($stderr)) { $stdout } else { "$stdout`n$stderr" }

            [pscustomobject]@{
                exitCode = $process.ExitCode
                output = $output
            } | ConvertTo-Json -Compress | Set-Content -LiteralPath $resultFile -Encoding UTF8

            Start-Process -FilePath 'shutdown.exe' -ArgumentList '/s', '/t', '0'
            """;
    }

    private static string EscapeXml(string value) => SecurityElement.Escape(value) ?? value;

    private sealed class SandboxCommandResult
    {
        [JsonPropertyName("exitCode")]
        public int ExitCode { get; set; } = 1;

        [JsonPropertyName("output")]
        public string Output { get; set; } = "";
    }
}
