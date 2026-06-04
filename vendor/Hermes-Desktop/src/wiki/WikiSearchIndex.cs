namespace Hermes.Agent.Wiki;

using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;

/// <summary>
/// A search result from the wiki FTS5 index.
/// </summary>
public sealed class WikiSearchResult
{
    public required string RelativePath { get; init; }
    public required string Title { get; init; }
    public required string Snippet { get; init; }
    public required double Score { get; init; }
}

/// <summary>
/// SQLite FTS5-backed full-text search index for wiki pages.
/// Stored at {WikiPath}/.wiki-search.db.
/// Follows the same pattern as SessionSearchIndex.
/// </summary>
public sealed class WikiSearchIndex : IDisposable
{
    private readonly SqliteConnection _db;
    private readonly ILogger<WikiSearchIndex> _logger;
    private bool _disposed;

    public WikiSearchIndex(string dbPath, ILogger<WikiSearchIndex> logger)
    {
        _logger = logger;
        Directory.CreateDirectory(Path.GetDirectoryName(dbPath) ?? ".");

        _db = new SqliteConnection($"Data Source={dbPath}");
        _db.Open();
        InitializeSchema();
    }

    private void InitializeSchema()
    {
        using var cmd = _db.CreateCommand();
        cmd.CommandText = @"
            CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
                path UNINDEXED, title, tags, content,
                tokenize='porter unicode61'
            );";
        cmd.ExecuteNonQuery();
    }

    /// <summary>
    /// Index a wiki page. Removes any existing entry for the same path first.
    /// </summary>
    public async Task IndexPageAsync(WikiPage page, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(page.FilePath) && string.IsNullOrWhiteSpace(page.Content))
            return;

        try
        {
            await RemovePageAsync(page.FilePath, ct);

            using var cmd = _db.CreateCommand();
            cmd.CommandText = "INSERT INTO wiki_fts (path, title, tags, content) VALUES ($path, $title, $tags, $content)";
            cmd.Parameters.AddWithValue("$path", page.FilePath);
            cmd.Parameters.AddWithValue("$title", page.Title);
            cmd.Parameters.AddWithValue("$tags", string.Join(' ', page.Tags));
            cmd.Parameters.AddWithValue("$content", page.Content);
            cmd.ExecuteNonQuery();
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to index wiki page {Path}", page.FilePath);
        }
    }

    /// <summary>
    /// Remove a page from the search index by its relative path.
    /// </summary>
    public Task RemovePageAsync(string relativePath, CancellationToken ct = default)
    {
        try
        {
            using var cmd = _db.CreateCommand();
            cmd.CommandText = "DELETE FROM wiki_fts WHERE path = $path";
            cmd.Parameters.AddWithValue("$path", relativePath);
            cmd.ExecuteNonQuery();
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to remove wiki page {Path} from index", relativePath);
        }

        return Task.CompletedTask;
    }

    /// <summary>
    /// Search the wiki using FTS5 query syntax.
    /// Supports: AND, OR, NOT, "phrase", prefix*
    /// </summary>
    public Task<List<WikiSearchResult>> SearchAsync(string query, int limit = 10, CancellationToken ct = default)
    {
        var results = new List<WikiSearchResult>();

        try
        {
            using var cmd = _db.CreateCommand();
            cmd.CommandText = @"
                SELECT path, title,
                       snippet(wiki_fts, 3, '»', '«', '...', 40) as snippet,
                       rank
                FROM wiki_fts
                WHERE wiki_fts MATCH $query
                ORDER BY rank
                LIMIT $limit";
            cmd.Parameters.AddWithValue("$query", SanitizeQuery(query));
            cmd.Parameters.AddWithValue("$limit", limit);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                results.Add(new WikiSearchResult
                {
                    RelativePath = reader.GetString(0),
                    Title = reader.GetString(1),
                    Snippet = reader.GetString(2),
                    Score = reader.GetDouble(3)
                });
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Wiki FTS5 search failed for query: {Query}", query);
        }

        return Task.FromResult(results);
    }

    /// <summary>
    /// Rebuild the entire search index by scanning all .md files from storage.
    /// </summary>
    public async Task RebuildIndexAsync(IWikiStorage storage, CancellationToken ct = default)
    {
        _logger.LogInformation("Rebuilding wiki search index...");

        // Clear existing index
        using (var cmd = _db.CreateCommand())
        {
            cmd.CommandText = "DELETE FROM wiki_fts";
            cmd.ExecuteNonQuery();
        }

        var files = await storage.ListFilesAsync("", ct);
        var indexed = 0;

        foreach (var file in files)
        {
            if (ct.IsCancellationRequested) break;

            try
            {
                var content = await storage.ReadFileAsync(file, ct);
                if (content is null) continue;

                var page = WikiPage.Parse(content, file);
                await IndexPageAsync(page, ct);
                indexed++;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to index file {File} during rebuild", file);
            }
        }

        _logger.LogInformation("Wiki search index rebuilt: {Count} pages indexed", indexed);
    }

    /// <summary>
    /// Total indexed page count.
    /// </summary>
    public long PageCount()
    {
        using var cmd = _db.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM wiki_fts";
        return (long)(cmd.ExecuteScalar() ?? 0);
    }

    /// <summary>Sanitize user query for FTS5 — escape special chars.</summary>
    private static string SanitizeQuery(string query)
    {
        return query
            .Replace("(", "")
            .Replace(")", "")
            .Replace(":", " ");
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _db.Close();
        _db.Dispose();
    }
}
