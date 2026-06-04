namespace Hermes.Agent.Wiki;

/// <summary>
/// Reads/writes SCHEMA.md at the wiki root.
/// Defines the domain, tag taxonomy, and conventions for the wiki.
/// </summary>
public sealed class WikiSchema
{
    public string Domain { get; set; } = "";
    public List<string> TagTaxonomy { get; set; } = new();
    public string Conventions { get; set; } = "";

    /// <summary>
    /// Parse schema from SCHEMA.md markdown content.
    /// Expected sections: ## Domain, ## Tags, ## Conventions
    /// </summary>
    public static WikiSchema ParseFromMarkdown(string content)
    {
        var schema = new WikiSchema();

        if (string.IsNullOrWhiteSpace(content))
            return schema;

        var currentSection = "";
        var conventionLines = new List<string>();

        foreach (var line in content.Split('\n'))
        {
            var trimmed = line.Trim();

            if (trimmed.StartsWith("## ", StringComparison.Ordinal))
            {
                // Flush conventions if we were in that section
                if (currentSection == "conventions" && conventionLines.Count > 0)
                    schema.Conventions = string.Join('\n', conventionLines).Trim();

                var heading = trimmed.Substring(3).Trim().ToLowerInvariant();
                currentSection = heading;
                conventionLines.Clear();
                continue;
            }

            if (string.IsNullOrWhiteSpace(trimmed) && currentSection != "conventions")
                continue;

            switch (currentSection)
            {
                case "domain":
                    if (!string.IsNullOrWhiteSpace(trimmed))
                        schema.Domain = trimmed;
                    break;

                case "tags":
                    // Expect lines like "- tag-name"
                    if (trimmed.StartsWith("- "))
                    {
                        var tag = trimmed.Substring(2).Trim();
                        if (!string.IsNullOrEmpty(tag))
                            schema.TagTaxonomy.Add(tag);
                    }
                    break;

                case "conventions":
                    conventionLines.Add(line);
                    break;
            }
        }

        // Flush trailing conventions
        if (currentSection == "conventions" && conventionLines.Count > 0)
            schema.Conventions = string.Join('\n', conventionLines).Trim();

        return schema;
    }

    /// <summary>
    /// Serialize to SCHEMA.md format.
    /// </summary>
    public string SerializeToMarkdown()
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("# Wiki Schema");
        sb.AppendLine();
        sb.AppendLine("## Domain");
        sb.AppendLine(Domain);
        sb.AppendLine();
        sb.AppendLine("## Tags");
        foreach (var tag in TagTaxonomy)
            sb.AppendLine($"- {tag}");
        sb.AppendLine();
        sb.AppendLine("## Conventions");
        sb.AppendLine(Conventions);
        return sb.ToString();
    }

    /// <summary>
    /// Check if a tag is in the defined taxonomy.
    /// Returns true if no taxonomy is defined (permissive mode).
    /// </summary>
    public bool IsTagValid(string tag)
    {
        if (TagTaxonomy.Count == 0)
            return true;
        return TagTaxonomy.Contains(tag, StringComparer.OrdinalIgnoreCase);
    }
}
