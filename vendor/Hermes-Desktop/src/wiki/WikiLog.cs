namespace Hermes.Agent.Wiki;

/// <summary>
/// Actions that can be recorded in the wiki log.
/// </summary>
public enum WikiLogAction
{
    Ingest,
    Update,
    Query,
    Lint,
    Create,
    Archive,
    Delete
}

/// <summary>
/// Append-only log.md writer for wiki operations.
/// Format: "- [YYYY-MM-DD HH:mm] ACTION | subject — detail"
/// Supports rotation when line count exceeds threshold.
/// </summary>
public sealed class WikiLog
{
    private readonly IWikiStorage _storage;
    private readonly WikiConfig _config;
    private const string LogFileName = "log.md";

    public WikiLog(IWikiStorage storage, WikiConfig config)
    {
        _storage = storage;
        _config = config;
    }

    /// <summary>
    /// Append a log entry. Uses append-style write: reads existing, appends, writes back.
    /// </summary>
    public async Task AppendEntryAsync(
        WikiLogAction action,
        string subject,
        string detail,
        CancellationToken ct = default)
    {
        var timestamp = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm");
        var entry = $"- [{timestamp}] {action.ToString().ToUpperInvariant()} | {subject} — {detail}";

        var existing = await _storage.ReadFileAsync(LogFileName, ct) ?? "# Wiki Log\n";

        // Append entry
        var content = existing.TrimEnd() + "\n" + entry + "\n";

        await _storage.WriteFileAsync(LogFileName, content, ct);
    }

    /// <summary>
    /// Get the most recent log entries as a string.
    /// </summary>
    public async Task<string> GetRecentEntriesAsync(int count = 30, CancellationToken ct = default)
    {
        var content = await _storage.ReadFileAsync(LogFileName, ct);
        if (string.IsNullOrWhiteSpace(content))
            return "";

        var lines = content.Split('\n')
            .Where(l => l.TrimStart().StartsWith("- ["))
            .ToList();

        var recent = lines
            .Skip(Math.Max(0, lines.Count - count))
            .ToList();

        return string.Join('\n', recent);
    }

    /// <summary>
    /// Check if the log file exceeds the rotation threshold.
    /// </summary>
    public async Task<bool> CheckRotationNeededAsync(CancellationToken ct = default)
    {
        var content = await _storage.ReadFileAsync(LogFileName, ct);
        if (string.IsNullOrWhiteSpace(content))
            return false;

        var lineCount = content.Split('\n').Length;
        return lineCount > _config.LogRotationThreshold;
    }

    /// <summary>
    /// Rotate the log: rename current to log-{year}.md and start fresh.
    /// </summary>
    public async Task RotateAsync(CancellationToken ct = default)
    {
        var content = await _storage.ReadFileAsync(LogFileName, ct);
        if (string.IsNullOrWhiteSpace(content))
            return;

        // Write archive
        var archiveName = $"log-{DateTime.UtcNow.Year}.md";
        var existingArchive = await _storage.ReadFileAsync(archiveName, ct);

        if (existingArchive is not null)
        {
            // Append to existing archive
            await _storage.WriteFileAsync(archiveName, existingArchive.TrimEnd() + "\n" + content, ct);
        }
        else
        {
            await _storage.WriteFileAsync(archiveName, content, ct);
        }

        // Start fresh log
        await _storage.WriteFileAsync(LogFileName, "# Wiki Log\n", ct);
    }
}
