namespace Hermes.Agent.Wiki;

using Microsoft.Extensions.Logging;

/// <summary>
/// Statistics about the wiki.
/// </summary>
public sealed class WikiStats
{
    public int TotalPages { get; init; }
    public long TotalSizeBytes { get; init; }
    public DateTime LastUpdated { get; init; }
    public Dictionary<WikiPageType, int> PagesByType { get; init; } = new();
}

/// <summary>
/// Top-level facade that orchestrates all wiki operations.
/// Pure data layer — no LLM calls, no UI.
/// </summary>
public sealed class WikiManager
{
    private readonly IWikiStorage _storage;
    private readonly WikiConfig _config;
    private readonly WikiSearchIndex _searchIndex;
    private readonly WikiLog _log;
    private readonly ILogger<WikiManager> _logger;

    public WikiManager(
        IWikiStorage storage,
        WikiConfig config,
        WikiSearchIndex searchIndex,
        ILogger<WikiManager> logger)
    {
        _storage = storage;
        _config = config;
        _searchIndex = searchIndex;
        _log = new WikiLog(storage, config);
        _logger = logger;
    }

    /// <summary>
    /// Initialize a new wiki: create standard directories, SCHEMA.md, index.md, log.md.
    /// </summary>
    public async Task InitializeWikiAsync(string domain, CancellationToken ct = default)
    {
        _logger.LogInformation("Initializing wiki for domain: {Domain}", domain);

        // Create standard directories
        var dirs = new[] { "entities", "concepts", "systems", "patterns", "queries" };
        foreach (var dir in dirs)
            _storage.CreateDirectory(dir);

        // Write SCHEMA.md
        var schema = new WikiSchema
        {
            Domain = domain,
            TagTaxonomy = new List<string>(),
            Conventions = "Pages use markdown with YAML frontmatter.\nOne concept per page.\nLink related pages with relative paths."
        };
        await _storage.WriteFileAsync("SCHEMA.md", schema.SerializeToMarkdown(), ct);

        // Write empty index.md
        var index = new WikiIndex();
        await _storage.WriteFileAsync("index.md", index.SerializeToMarkdown(), ct);

        // Write initial log.md
        await _storage.WriteFileAsync("log.md", "# Wiki Log\n", ct);

        await _log.AppendEntryAsync(WikiLogAction.Create, "wiki", $"Initialized wiki for domain: {domain}", ct);

        _logger.LogInformation("Wiki initialized with directories: {Dirs}", string.Join(", ", dirs));
    }

    /// <summary>
    /// Check if the wiki has been initialized (SCHEMA.md exists).
    /// </summary>
    public bool IsInitialized()
    {
        return _storage.FileExists("SCHEMA.md");
    }

    /// <summary>
    /// Read and parse a wiki page by relative path.
    /// </summary>
    public async Task<WikiPage?> GetPageAsync(string relativePath, CancellationToken ct = default)
    {
        var content = await _storage.ReadFileAsync(relativePath, ct);
        if (content is null)
            return null;

        return WikiPage.Parse(content, relativePath);
    }

    /// <summary>
    /// Save a wiki page: write file, update index, update search index, append log.
    /// </summary>
    public async Task SavePageAsync(WikiPage page, CancellationToken ct = default)
    {
        page.Updated = DateTime.UtcNow;

        var isNew = !_storage.FileExists(page.FilePath);

        // 1. Write file to disk first (crash-safe via storage layer)
        await _storage.WriteFileAsync(page.FilePath, page.Serialize(), ct);

        // 2. Update index
        var index = await LoadIndexAsync(ct);
        index.UpdateEntry(new WikiIndexEntry
        {
            Title = page.Title,
            RelativePath = page.FilePath,
            Summary = ExtractSummary(page.Content),
            LastUpdated = page.Updated,
            Type = page.Type
        });
        await _storage.WriteFileAsync("index.md", index.SerializeToMarkdown(), ct);

        // 3. Update search index
        await _searchIndex.IndexPageAsync(page, ct);

        // 4. Append log
        var action = isNew ? WikiLogAction.Create : WikiLogAction.Update;
        await _log.AppendEntryAsync(action, page.Title, page.FilePath, ct);

        _logger.LogInformation("Saved wiki page: {Title} at {Path}", page.Title, page.FilePath);
    }

    /// <summary>
    /// Delete a wiki page: remove file, update index, remove from search, log.
    /// </summary>
    public async Task DeletePageAsync(string relativePath, CancellationToken ct = default)
    {
        var page = await GetPageAsync(relativePath, ct);
        var title = page?.Title ?? relativePath;

        // 1. Delete file
        await _storage.DeleteFileAsync(relativePath, ct);

        // 2. Update index
        var index = await LoadIndexAsync(ct);
        index.RemoveEntry(relativePath);
        await _storage.WriteFileAsync("index.md", index.SerializeToMarkdown(), ct);

        // 3. Remove from search index
        await _searchIndex.RemovePageAsync(relativePath, ct);

        // 4. Log
        await _log.AppendEntryAsync(WikiLogAction.Delete, title, relativePath, ct);

        _logger.LogInformation("Deleted wiki page: {Path}", relativePath);
    }

    /// <summary>
    /// Full-text search across the wiki.
    /// </summary>
    public async Task<List<WikiSearchResult>> SearchAsync(string query, int limit = 10, CancellationToken ct = default)
    {
        await _log.AppendEntryAsync(WikiLogAction.Query, query, $"limit={limit}", ct);
        return await _searchIndex.SearchAsync(query, limit, ct);
    }

    /// <summary>
    /// Get the current wiki index.
    /// </summary>
    public async Task<WikiIndex> GetIndexAsync(CancellationToken ct = default)
    {
        return await LoadIndexAsync(ct);
    }

    /// <summary>
    /// Get the current wiki schema.
    /// </summary>
    public async Task<WikiSchema> GetSchemaAsync(CancellationToken ct = default)
    {
        var content = await _storage.ReadFileAsync("SCHEMA.md", ct);
        if (content is null)
            return new WikiSchema();

        return WikiSchema.ParseFromMarkdown(content);
    }

    /// <summary>
    /// Get recent log entries.
    /// </summary>
    public async Task<string> GetRecentLogAsync(int lines = 30, CancellationToken ct = default)
    {
        return await _log.GetRecentEntriesAsync(lines, ct);
    }

    /// <summary>
    /// Get wiki statistics: page count, size, last updated, by-type breakdown.
    /// </summary>
    public async Task<WikiStats> GetStatsAsync(CancellationToken ct = default)
    {
        var files = await _storage.ListFilesAsync("", ct);
        var index = await LoadIndexAsync(ct);

        long totalSize = 0;
        var lastUpdated = DateTime.MinValue;
        var pagesByType = new Dictionary<WikiPageType, int>();

        foreach (var type in Enum.GetValues<WikiPageType>())
            pagesByType[type] = 0;

        foreach (var file in files)
        {
            var content = await _storage.ReadFileAsync(file, ct);
            if (content is null) continue;

            totalSize += System.Text.Encoding.UTF8.GetByteCount(content);

            var page = WikiPage.Parse(content, file);
            pagesByType[page.Type]++;

            if (page.Updated > lastUpdated)
                lastUpdated = page.Updated;
        }

        return new WikiStats
        {
            TotalPages = files.Count,
            TotalSizeBytes = totalSize,
            LastUpdated = lastUpdated == DateTime.MinValue ? DateTime.UtcNow : lastUpdated,
            PagesByType = pagesByType
        };
    }

    // ── Helpers ──

    private async Task<WikiIndex> LoadIndexAsync(CancellationToken ct)
    {
        var content = await _storage.ReadFileAsync("index.md", ct);
        if (content is null)
            return new WikiIndex();

        return WikiIndex.ParseFromMarkdown(content);
    }

    /// <summary>
    /// Extract the first non-empty, non-heading line as a summary.
    /// </summary>
    private static string ExtractSummary(string content, int maxLength = 120)
    {
        if (string.IsNullOrWhiteSpace(content))
            return "";

        foreach (var line in content.Split('\n'))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith('#'))
                continue;

            return trimmed.Length > maxLength
                ? trimmed.Substring(0, maxLength) + "..."
                : trimmed;
        }

        return "";
    }
}
