namespace Hermes.Agent.Mcp;

using System.Text.Json;
using Microsoft.Extensions.Logging;

/// <summary>
/// Manages multiple MCP server connections and provides unified tool discovery.
/// </summary>
public sealed class McpManager : IAsyncDisposable
{
    private readonly ILogger<McpManager> _logger;
    private readonly Dictionary<string, McpServerConnection> _connections = new();
    private readonly Dictionary<string, McpToolWrapper> _tools = new();
    private readonly List<McpServerConfig> _configs = new();
    private readonly List<McpConfigLoadIssue> _loadIssues = new();
    private string[] _bootstrapConfigSearchPaths = Array.Empty<string>();

    private static readonly JsonSerializerOptions McpConfigJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    public IReadOnlyDictionary<string, McpServerConnection> Connections => _connections;
    public IReadOnlyDictionary<string, McpToolWrapper> Tools => _tools;
    public int ServerCount => _connections.Count;
    public int ConfiguredServerCount => _configs.Count;

    /// <summary>Servers or entries skipped while loading <c>mcp.json</c> (policy, invalid URL, etc.).</summary>
    public IReadOnlyList<McpConfigLoadIssue> ConfigLoadIssues => _loadIssues;

    /// <summary>
    /// The <c>mcp.json</c> search paths the last <see cref="McpBootstrap.AttachAsync"/> call
    /// was asked to inspect, in their original order. Empty until bootstrap runs. Dashboards
    /// must prefer this snapshot over rebuilding the list locally so they cannot drift from
    /// what App.xaml.cs actually used at startup.
    /// </summary>
    public IReadOnlyList<string> BootstrapConfigSearchPaths => _bootstrapConfigSearchPaths;

    public McpManager(ILogger<McpManager> logger)
    {
        _logger = logger;
    }

    /// <summary>Clears accumulated config before a bootstrap pass loads one or more files.</summary>
    public void PrepareForBootstrapAttach()
    {
        _configs.Clear();
        _loadIssues.Clear();
    }

    /// <summary>
    /// Records the exact ordered list of <c>mcp.json</c> search paths a bootstrap caller will
    /// inspect. Whitespace-only entries are dropped; remaining entries are trimmed but left
    /// otherwise verbatim (resolution to absolute paths is the caller's responsibility).
    /// </summary>
    internal void RecordBootstrapConfigSearchPaths(IEnumerable<string> paths)
    {
        ArgumentNullException.ThrowIfNull(paths);
        _bootstrapConfigSearchPaths = paths
            .Where(static p => !string.IsNullOrWhiteSpace(p))
            .Select(static p => p.Trim())
            .ToArray();
    }

    /// <summary>Runtime view for dashboards (no URLs or secrets).</summary>
    public IReadOnlyList<McpServerRuntimeStatus> GetRuntimeStatuses()
    {
        var list = new List<McpServerRuntimeStatus>(_configs.Count);
        foreach (var config in _configs)
            list.Add(ToRuntimeStatus(config));

        return list;
    }

    private McpServerRuntimeStatus ToRuntimeStatus(McpServerConfig config)
    {
        bool connected = _connections.TryGetValue(config.Name, out var conn) && conn.IsConnected;
        return new McpServerRuntimeStatus(
            config.Name,
            GetTransportLabel(config),
            connected,
            CountToolsForServer(config.Name));
    }

    private static string GetTransportLabel(McpServerConfig config) => config switch
    {
        McpStdioConfig => "stdio",
        McpHttpConfig => "http_sse",
        McpWebSocketConfig => "websocket",
        _ => "unknown",
    };

    private int CountToolsForServer(string serverName)
    {
        var prefix = $"mcp__{serverName}__";
        return _tools.Count(kvp => kvp.Key.StartsWith(prefix, StringComparison.Ordinal));
    }
    
    /// <summary>
    /// Load MCP server configurations from config file.
    /// </summary>
    public async Task LoadFromConfigAsync(string configPath, CancellationToken ct = default)
    {
        if (!File.Exists(configPath))
        {
            _logger.LogDebug("MCP config file not found: {Path}", configPath);
            return;
        }
        
        var json = await File.ReadAllTextAsync(configPath, ct);
        var config = JsonSerializer.Deserialize<McpConfigFile>(json, McpConfigJsonOptions);
        
        if (config?.McpServers is null) return;
        
        foreach (var (name, serverConfig) in config.McpServers)
        {
            if (TryCreateServerConfig(name, serverConfig, out var mcpConfig))
                _configs.Add(mcpConfig);
        }
    }
    
    /// <summary>
    /// Add a server configuration programmatically.
    /// </summary>
    public void AddServer(McpServerConfig config)
    {
        if (config is McpHttpConfig http &&
            !McpRemoteEndpointValidator.TryValidateRemoteUri(http.Url, out var httpErr))
        {
            _logger.LogWarning("MCP AddServer rejected {Name}: {Reason}", config.Name, httpErr);
            return;
        }

        if (config is McpWebSocketConfig ws &&
            !McpRemoteEndpointValidator.TryValidateRemoteUri(ws.Url, out var wsErr))
        {
            _logger.LogWarning("MCP AddServer rejected {Name}: {Reason}", config.Name, wsErr);
            return;
        }

        _configs.Add(config);
    }
    
    /// <summary>
    /// Connect to all configured MCP servers.
    /// </summary>
    public async Task ConnectAllAsync(CancellationToken ct = default)
    {
        var tasks = _configs.Select(c => ConnectServerAsync(c, ct)).ToList();
        await Task.WhenAll(tasks);
    }
    
    private bool TryCreateServerConfig(
        string name,
        McpServerConfigEntry entry,
        out McpServerConfig config)
    {
        if (entry.Command is not null)
        {
            config = new McpStdioConfig(name, entry.Command, entry.Args, entry.Env);
            return true;
        }

        if (entry.Url is null)
        {
            config = null!;
            return false;
        }

        if (!Uri.TryCreate(entry.Url, UriKind.Absolute, out var absUrl))
        {
            RecordConfigSkip(name, "Invalid MCP URL.", "invalid URL");
            config = null!;
            return false;
        }

        if (!McpRemoteEndpointValidator.TryValidateRemoteUri(absUrl, out var urlError))
        {
            RecordConfigSkip(name, urlError ?? "URL rejected by policy.", urlError ?? "URL rejected by policy");
            config = null!;
            return false;
        }

        config = new McpHttpConfig(name, absUrl, entry.Headers);
        return true;
    }

    private void RecordConfigSkip(string name, string issueMessage, string logReason)
    {
        _loadIssues.Add(new McpConfigLoadIssue(name, issueMessage));
        _logger.LogWarning("MCP server {Name} skipped: {Reason}", name, logReason);
    }

    private async Task ConnectServerAsync(McpServerConfig config, CancellationToken ct)
    {
        try
        {
            _logger.LogInformation("Connecting to MCP server: {Name}", config.Name);
            
            var connection = new McpServerConnection(config);
            await connection.ConnectAsync(ct);
            
            _connections[config.Name] = connection;
            
            // Register tools
            foreach (var tool in connection.Tools)
            {
                var wrapper = new McpToolWrapper(connection, tool);
                _tools[wrapper.Name] = wrapper;
                _logger.LogDebug("Registered MCP tool: {Name}", wrapper.Name);
            }
            
            _logger.LogInformation("Connected to MCP server {Name} with {Count} tools", 
                config.Name, connection.Tools.Count);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to connect to MCP server: {Name}", config.Name);
        }
    }
    
    /// <summary>
    /// Get a tool by normalized name.
    /// </summary>
    public McpToolWrapper? GetTool(string normalizedName)
    {
        return _tools.TryGetValue(normalizedName, out var tool) ? tool : null;
    }
    
    /// <summary>
    /// Get all tool names (normalized).
    /// </summary>
    public IEnumerable<string> GetToolNames() => _tools.Keys;
    
    /// <summary>
    /// Disconnect a specific server.
    /// </summary>
    public async Task DisconnectAsync(string name, CancellationToken ct = default)
    {
        if (_connections.TryGetValue(name, out var connection))
        {
            // Remove tools from this server
            var toolsToRemove = _tools
                .Where(kvp => kvp.Key.StartsWith($"mcp__{name}__", StringComparison.Ordinal))
                .Select(kvp => kvp.Key)
                .ToList();
            
            foreach (var toolName in toolsToRemove)
            {
                _tools.Remove(toolName);
            }
            
            _connections.Remove(name);
            await connection.DisposeAsync();
        }
    }

    public async ValueTask DisposeAsync()
    {
        foreach (var connection in _connections.Values)
        {
            await connection.DisposeAsync();
        }
        
        _connections.Clear();
        _tools.Clear();
        _configs.Clear();
    }
}

/// <summary>
/// MCP configuration file format.
/// </summary>
public sealed class McpConfigFile
{
    public Dictionary<string, McpServerConfigEntry>? McpServers { get; init; }
}

/// <summary>
/// MCP server configuration entry from config file.
/// </summary>
public sealed class McpServerConfigEntry
{
    public string? Command { get; init; }
    public IReadOnlyList<string>? Args { get; init; }
    public IReadOnlyDictionary<string, string>? Env { get; init; }
    public string? Url { get; init; }
    public IReadOnlyDictionary<string, string>? Headers { get; init; }
}
