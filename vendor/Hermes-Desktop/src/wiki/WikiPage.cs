namespace Hermes.Agent.Wiki;

/// <summary>
/// Wiki page types — determines storage directory and index section.
/// </summary>
public enum WikiPageType
{
    Entity,
    Concept,
    Comparison,
    Query,
    Summary,
    System,
    Pattern
}

/// <summary>
/// A single wiki page with YAML-like frontmatter and markdown body.
/// Follows the same manual frontmatter parsing pattern as SkillManager.
/// </summary>
public sealed class WikiPage
{
    public string Title { get; set; } = "";
    public DateTime Created { get; set; } = DateTime.UtcNow;
    public DateTime Updated { get; set; } = DateTime.UtcNow;
    public WikiPageType Type { get; set; } = WikiPageType.Entity;
    public List<string> Tags { get; set; } = new();
    public List<string> Sources { get; set; } = new();
    public string Content { get; set; } = "";
    public string FilePath { get; set; } = "";

    /// <summary>
    /// Parse a wiki page from raw markdown with optional YAML frontmatter.
    /// Handles missing frontmatter gracefully — returns page with just content.
    /// </summary>
    public static WikiPage Parse(string raw, string filePath)
    {
        var page = new WikiPage { FilePath = filePath };

        if (string.IsNullOrWhiteSpace(raw))
            return page;

        // Check for frontmatter delimiter
        if (!raw.StartsWith("---"))
        {
            page.Content = raw.Trim();
            page.Title = InferTitleFromContent(raw);
            return page;
        }

        var endIndex = raw.IndexOf("---", 3, StringComparison.Ordinal);
        if (endIndex == -1)
        {
            // Malformed frontmatter — treat everything as content
            page.Content = raw.Trim();
            page.Title = InferTitleFromContent(raw);
            return page;
        }

        var yamlContent = raw.Substring(3, endIndex - 3).Trim();
        page.Content = raw.Substring(endIndex + 3).Trim();

        // Parse frontmatter key-value pairs (same pattern as SkillManager.ParseYamlFrontmatter)
        foreach (var line in yamlContent.Split('\n'))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith('#'))
                continue;

            var colonIndex = trimmed.IndexOf(':');
            if (colonIndex == -1)
                continue;

            var key = trimmed.Substring(0, colonIndex).Trim().ToLowerInvariant();
            var value = trimmed.Substring(colonIndex + 1).Trim().Trim('"', '\'');

            switch (key)
            {
                case "title":
                    page.Title = value;
                    break;
                case "created":
                    if (DateTime.TryParse(value, out var created))
                        page.Created = created;
                    break;
                case "updated":
                    if (DateTime.TryParse(value, out var updated))
                        page.Updated = updated;
                    break;
                case "type":
                    if (Enum.TryParse<WikiPageType>(value, ignoreCase: true, out var pageType))
                        page.Type = pageType;
                    break;
                case "tags":
                    page.Tags = ParseCsvList(value);
                    break;
                case "sources":
                    page.Sources = ParseCsvList(value);
                    break;
            }
        }

        // Fallback title from filename if not in frontmatter
        if (string.IsNullOrWhiteSpace(page.Title))
            page.Title = InferTitleFromPath(filePath);

        return page;
    }

    /// <summary>
    /// Serialize the page back to markdown with frontmatter.
    /// </summary>
    public string Serialize()
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("---");
        sb.AppendLine($"title: {Title}");
        sb.AppendLine($"created: {Created:O}");
        sb.AppendLine($"updated: {Updated:O}");
        sb.AppendLine($"type: {Type}");
        if (Tags.Count > 0)
            sb.AppendLine($"tags: {string.Join(", ", Tags)}");
        if (Sources.Count > 0)
            sb.AppendLine($"sources: {string.Join(", ", Sources)}");
        sb.AppendLine("---");
        sb.AppendLine();
        sb.Append(Content);
        return sb.ToString();
    }

    private static List<string> ParseCsvList(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return new List<string>();

        return value.Split(',')
            .Select(t => t.Trim())
            .Where(t => !string.IsNullOrEmpty(t))
            .ToList();
    }

    private static string InferTitleFromContent(string content)
    {
        // Try to grab first markdown heading
        foreach (var line in content.Split('\n'))
        {
            var trimmed = line.TrimStart();
            if (trimmed.StartsWith('#'))
                return trimmed.TrimStart('#').Trim();
        }
        return "";
    }

    private static string InferTitleFromPath(string filePath)
    {
        if (string.IsNullOrEmpty(filePath))
            return "";
        var name = Path.GetFileNameWithoutExtension(filePath);
        return name.Replace('-', ' ').Replace('_', ' ');
    }
}
