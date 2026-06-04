namespace Hermes.Agent.Wiki;

/// <summary>
/// A single entry in the wiki index catalog.
/// </summary>
public sealed class WikiIndexEntry
{
    public string Title { get; set; } = "";
    public string RelativePath { get; set; } = "";
    public string Summary { get; set; } = "";
    public DateTime LastUpdated { get; set; } = DateTime.UtcNow;
    public WikiPageType Type { get; set; } = WikiPageType.Entity;
}

/// <summary>
/// Reads/writes index.md — the catalog of all wiki pages.
/// In-memory dictionary keyed by page type for fast access.
/// </summary>
public sealed class WikiIndex
{
    private readonly Dictionary<WikiPageType, List<WikiIndexEntry>> _entries = new();

    public WikiIndex()
    {
        // Pre-populate all page type buckets
        foreach (var type in Enum.GetValues<WikiPageType>())
            _entries[type] = new List<WikiIndexEntry>();
    }

    public IReadOnlyDictionary<WikiPageType, List<WikiIndexEntry>> Entries => _entries;

    /// <summary>
    /// Parse index.md from markdown.
    /// Expected format: sections like "## Entities", "## Concepts", etc.
    /// Each entry: "- [Title](path) — Summary (updated: YYYY-MM-DD)"
    /// </summary>
    public static WikiIndex ParseFromMarkdown(string content)
    {
        var index = new WikiIndex();

        if (string.IsNullOrWhiteSpace(content))
            return index;

        WikiPageType? currentType = null;

        foreach (var line in content.Split('\n'))
        {
            var trimmed = line.Trim();

            if (trimmed.StartsWith("## ", StringComparison.Ordinal))
            {
                var heading = trimmed.Substring(3).Trim();
                currentType = ParseSectionType(heading);
                continue;
            }

            if (currentType is null || !trimmed.StartsWith("- "))
                continue;

            var entry = ParseEntryLine(trimmed, currentType.Value);
            if (entry is not null)
                index._entries[currentType.Value].Add(entry);
        }

        return index;
    }

    /// <summary>
    /// Add an entry to the index. Replaces existing entry with same path.
    /// </summary>
    public void AddEntry(WikiIndexEntry entry)
    {
        RemoveEntry(entry.RelativePath);
        _entries[entry.Type].Add(entry);
    }

    /// <summary>
    /// Remove an entry by relative path.
    /// </summary>
    public bool RemoveEntry(string relativePath)
    {
        foreach (var bucket in _entries.Values)
        {
            var existing = bucket.FindIndex(e =>
                string.Equals(e.RelativePath, relativePath, StringComparison.OrdinalIgnoreCase));
            if (existing >= 0)
            {
                bucket.RemoveAt(existing);
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// Update an existing entry or add it if not found.
    /// </summary>
    public void UpdateEntry(WikiIndexEntry entry)
    {
        AddEntry(entry); // AddEntry already replaces
    }

    /// <summary>
    /// Find an entry by title (case-insensitive).
    /// </summary>
    public WikiIndexEntry? FindByTitle(string title)
    {
        return _entries.Values
            .SelectMany(b => b)
            .FirstOrDefault(e => string.Equals(e.Title, title, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// Find an entry by relative path (case-insensitive).
    /// </summary>
    public WikiIndexEntry? FindByPath(string relativePath)
    {
        return _entries.Values
            .SelectMany(b => b)
            .FirstOrDefault(e => string.Equals(e.RelativePath, relativePath, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// Get total count of all entries across all types.
    /// </summary>
    public int GetTotalCount()
    {
        return _entries.Values.Sum(b => b.Count);
    }

    /// <summary>
    /// Rebuild index.md as markdown.
    /// </summary>
    public string SerializeToMarkdown()
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("# Wiki Index");
        sb.AppendLine();

        foreach (var type in Enum.GetValues<WikiPageType>())
        {
            var entries = _entries[type];
            if (entries.Count == 0)
                continue;

            sb.AppendLine($"## {TypeToSectionName(type)}");
            sb.AppendLine();

            foreach (var entry in entries.OrderBy(e => e.Title))
            {
                var summary = string.IsNullOrEmpty(entry.Summary) ? "" : $" — {entry.Summary}";
                sb.AppendLine($"- [{entry.Title}]({entry.RelativePath}){summary} (updated: {entry.LastUpdated:yyyy-MM-dd})");
            }

            sb.AppendLine();
        }

        return sb.ToString();
    }

    // ── Helpers ──

    private static WikiPageType? ParseSectionType(string heading)
    {
        return heading.ToLowerInvariant() switch
        {
            "entities" => WikiPageType.Entity,
            "concepts" => WikiPageType.Concept,
            "comparisons" => WikiPageType.Comparison,
            "queries" => WikiPageType.Query,
            "summaries" => WikiPageType.Summary,
            "systems" => WikiPageType.System,
            "patterns" => WikiPageType.Pattern,
            _ => null
        };
    }

    private static string TypeToSectionName(WikiPageType type) => type switch
    {
        WikiPageType.Entity => "Entities",
        WikiPageType.Concept => "Concepts",
        WikiPageType.Comparison => "Comparisons",
        WikiPageType.Query => "Queries",
        WikiPageType.Summary => "Summaries",
        WikiPageType.System => "Systems",
        WikiPageType.Pattern => "Patterns",
        _ => type.ToString()
    };

    /// <summary>
    /// Parse a single entry line: "- [Title](path) — Summary (updated: YYYY-MM-DD)"
    /// </summary>
    private static WikiIndexEntry? ParseEntryLine(string line, WikiPageType type)
    {
        // Strip leading "- "
        var text = line.Substring(2).Trim();

        // Extract [Title](path)
        if (!text.StartsWith('['))
            return null;

        var titleEnd = text.IndexOf(']');
        if (titleEnd < 0)
            return null;

        var title = text.Substring(1, titleEnd - 1);

        var pathStart = text.IndexOf('(', titleEnd);
        var pathEnd = text.IndexOf(')', pathStart + 1);
        if (pathStart < 0 || pathEnd < 0)
            return null;

        var path = text.Substring(pathStart + 1, pathEnd - pathStart - 1);

        // Extract summary and date from remainder
        var remainder = text.Substring(pathEnd + 1).Trim();
        var summary = "";
        var lastUpdated = DateTime.UtcNow;

        if (remainder.StartsWith("—") || remainder.StartsWith("-"))
        {
            remainder = remainder.TrimStart('—', '-').Trim();

            // Try to pull (updated: YYYY-MM-DD) from the end
            var dateStart = remainder.LastIndexOf("(updated:", StringComparison.OrdinalIgnoreCase);
            if (dateStart >= 0)
            {
                var dateEnd = remainder.IndexOf(')', dateStart);
                if (dateEnd > dateStart)
                {
                    var dateStr = remainder.Substring(dateStart + 9, dateEnd - dateStart - 9).Trim();
                    if (DateTime.TryParse(dateStr, out var parsed))
                        lastUpdated = parsed;
                    summary = remainder.Substring(0, dateStart).Trim();
                }
                else
                {
                    summary = remainder;
                }
            }
            else
            {
                summary = remainder;
            }
        }

        return new WikiIndexEntry
        {
            Title = title,
            RelativePath = path,
            Summary = summary,
            LastUpdated = lastUpdated,
            Type = type
        };
    }
}
