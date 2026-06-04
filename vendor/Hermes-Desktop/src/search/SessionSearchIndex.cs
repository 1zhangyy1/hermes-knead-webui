namespace Hermes.Agent.Search;

using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;

// ══════════════════════════════════════════════
// FTS5 Session Search Index
// ══════════════════════════════════════════════
//
// Upstream ref: tools/session_search_tool.py
// SQLite FTS5 full-text search of past sessions.
// Boolean syntax (AND/OR/NOT/phrase), ranked by relevance.

/// <summary>
/// SQLite FTS5-backed full-text search index for session transcripts.
/// Indexes messages on save, enables fast cross-session recall.
/// </summary>
public sealed class SessionSearchIndex : IDisposable
{
    private readonly SqliteConnection _db;
    private readonly ILogger<SessionSearchIndex> _logger;
    private bool _disposed;

    public SessionSearchIndex(string dbPath, ILogger<SessionSearchIndex> logger)
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
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content, session_id UNINDEXED, role UNINDEXED,
                content='messages', content_rowid='id',
                tokenize='porter unicode61'
            );
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content, session_id, role)
                VALUES (new.id, new.content, new.session_id, new.role);
            END;
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content, session_id, role)
                VALUES ('delete', old.id, old.content, old.session_id, old.role);
            END;";
        cmd.ExecuteNonQuery();
    }

    /// <summary>
    /// Index a message for full-text search.
    /// Called by TranscriptStore on save.
    /// </summary>
    public void IndexMessage(string sessionId, string role, string content, DateTime timestamp)
    {
        if (string.IsNullOrWhiteSpace(content)) return;

        try
        {
            using var cmd = _db.CreateCommand();
            cmd.CommandText = "INSERT INTO messages (session_id, role, content, timestamp) VALUES ($sid, $role, $content, $ts)";
            cmd.Parameters.AddWithValue("$sid", sessionId);
            cmd.Parameters.AddWithValue("$role", role);
            cmd.Parameters.AddWithValue("$content", content);
            cmd.Parameters.AddWithValue("$ts", timestamp.ToString("O"));
            cmd.ExecuteNonQuery();
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to index message for session {SessionId}", sessionId);
        }
    }

    /// <summary>
    /// Search indexed sessions using FTS5 query syntax.
    /// Supports: AND, OR, NOT, "phrase", prefix*
    /// </summary>
    public List<SearchResult> Search(string query, int maxResults = 10)
    {
        var results = new List<SearchResult>();

        try
        {
            using var cmd = _db.CreateCommand();
            cmd.CommandText = @"
                SELECT m.session_id, m.role, snippet(messages_fts, 0, '»', '«', '...', 40) as snippet,
                       rank, m.timestamp
                FROM messages_fts
                JOIN messages m ON messages_fts.rowid = m.id
                WHERE messages_fts MATCH $query
                ORDER BY rank
                LIMIT $limit";
            cmd.Parameters.AddWithValue("$query", SanitizeQuery(query));
            cmd.Parameters.AddWithValue("$limit", maxResults);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                results.Add(new SearchResult
                {
                    SessionId = reader.GetString(0),
                    Role = reader.GetString(1),
                    Snippet = reader.GetString(2),
                    Rank = reader.GetDouble(3),
                    Timestamp = reader.GetString(4)
                });
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "FTS5 search failed for query: {Query}", query);
        }

        return results;
    }

    /// <summary>Delete all entries for a session.</summary>
    public void DeleteSession(string sessionId)
    {
        using var cmd = _db.CreateCommand();
        cmd.CommandText = "DELETE FROM messages WHERE session_id = $sid";
        cmd.Parameters.AddWithValue("$sid", sessionId);
        cmd.ExecuteNonQuery();
    }

    /// <summary>Total indexed message count.</summary>
    public long MessageCount()
    {
        using var cmd = _db.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM messages";
        return (long)(cmd.ExecuteScalar() ?? 0);
    }

    /// <summary>Sanitize user query for FTS5 — escape special chars.</summary>
    private static string SanitizeQuery(string query)
    {
        // FTS5 special chars that need quoting if used literally
        // Allow AND/OR/NOT and "phrases" through
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

public sealed class SearchResult
{
    public required string SessionId { get; init; }
    public required string Role { get; init; }
    public required string Snippet { get; init; }
    public required double Rank { get; init; }
    public required string Timestamp { get; init; }
}
