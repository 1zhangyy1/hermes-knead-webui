namespace Hermes.Agent.Skills;

using Microsoft.Extensions.Logging;
using System.Net.Http.Json;
using System.Text.Json;

// ══════════════════════════════════════════════
// Skills Hub Client
// ══════════════════════════════════════════════
//
// Upstream ref: tools/skills_hub.py
// Multi-source skill marketplace: GitHub repos, skills.sh,
// community sharing. Quarantine scanning before install.

/// <summary>
/// Client for discovering and installing skills from remote sources.
/// Sources: GitHub repos, well-known URLs, community hubs.
/// All installed skills are security-scanned before activation.
/// </summary>
public sealed class SkillsHub
{
    private readonly SkillManager _skillManager;
    private readonly HttpClient _http;
    private readonly ILogger<SkillsHub> _logger;
    private readonly string _quarantineDir;

    public SkillsHub(SkillManager skillManager, string quarantineDir, ILogger<SkillsHub> logger)
    {
        _skillManager = skillManager;
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        _logger = logger;
        _quarantineDir = quarantineDir;
        Directory.CreateDirectory(quarantineDir);
    }

    /// <summary>
    /// Search for skills from a GitHub repository.
    /// Format: owner/repo or full GitHub URL.
    /// </summary>
    public async Task<List<RemoteSkill>> SearchGitHubAsync(string repoPath, CancellationToken ct)
    {
        var results = new List<RemoteSkill>();

        try
        {
            // Normalize repo path
            if (repoPath.Contains("github.com"))
            {
                var uri = new Uri(repoPath);
                repoPath = uri.AbsolutePath.Trim('/');
            }

            var apiUrl = $"https://api.github.com/repos/{repoPath}/contents/skills";
            _http.DefaultRequestHeaders.UserAgent.TryParseAdd("HermesDesktop/1.0");

            var response = await _http.GetAsync(apiUrl, ct);
            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("GitHub API returned {Status} for {Repo}", response.StatusCode, repoPath);
                return results;
            }

            var json = await response.Content.ReadAsStringAsync(ct);
            using var doc = JsonDocument.Parse(json);

            foreach (var item in doc.RootElement.EnumerateArray())
            {
                var name = item.GetProperty("name").GetString();
                var type = item.GetProperty("type").GetString();
                var downloadUrl = item.TryGetProperty("download_url", out var dlEl) ? dlEl.GetString() : null;

                if (type == "file" && name?.EndsWith(".md") == true && downloadUrl is not null)
                {
                    results.Add(new RemoteSkill
                    {
                        Name = Path.GetFileNameWithoutExtension(name),
                        Source = $"github:{repoPath}",
                        DownloadUrl = downloadUrl
                    });
                }
                else if (type == "dir")
                {
                    // Skill category directory — recurse one level
                    results.Add(new RemoteSkill
                    {
                        Name = name ?? "unknown",
                        Source = $"github:{repoPath}/{name}",
                        DownloadUrl = null, // Directory — needs further listing
                        IsCategory = true
                    });
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to search GitHub repo: {Repo}", repoPath);
        }

        return results;
    }

    /// <summary>
    /// Install a skill from a remote URL.
    /// Downloads to quarantine, scans, then moves to skills directory.
    /// </summary>
    public async Task<InstallResult> InstallAsync(string name, string downloadUrl, CancellationToken ct)
    {
        try
        {
            // Download to quarantine
            var quarantinePath = Path.Combine(_quarantineDir, $"{name}.md");
            var content = await _http.GetStringAsync(downloadUrl, ct);
            await File.WriteAllTextAsync(quarantinePath, content, ct);

            // Security scan
            if (Agent.Security.SecretScanner.ContainsSecrets(content))
            {
                File.Delete(quarantinePath);
                _logger.LogWarning("Skill '{Name}' from {Url} failed security scan — quarantined and deleted", name, downloadUrl);
                return new InstallResult { Success = false, Error = "Skill contains secrets — blocked for security." };
            }

            // Parse to validate it's a proper skill
            if (!content.StartsWith("---"))
            {
                File.Delete(quarantinePath);
                return new InstallResult { Success = false, Error = "Invalid skill format — missing YAML frontmatter." };
            }

            // Install via SkillManager (handles validation + atomic write)
            var endIndex = content.IndexOf("---", 3, StringComparison.Ordinal);
            if (endIndex < 0)
            {
                File.Delete(quarantinePath);
                return new InstallResult { Success = false, Error = "Invalid YAML frontmatter." };
            }

            var body = content[(endIndex + 3)..].Trim();
            var skill = await _skillManager.CreateSkillAsync(
                name, $"Installed from {downloadUrl}", body,
                new List<string>(), null, "community", ct);

            // Clean quarantine
            File.Delete(quarantinePath);

            _logger.LogInformation("Installed skill '{Name}' from {Source}", name, downloadUrl);
            return new InstallResult { Success = true, Skill = skill };
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to install skill '{Name}'", name);
            return new InstallResult { Success = false, Error = ex.Message };
        }
    }
}

public sealed class RemoteSkill
{
    public required string Name { get; init; }
    public required string Source { get; init; }
    public string? DownloadUrl { get; init; }
    public bool IsCategory { get; init; }
}

public sealed class InstallResult
{
    public bool Success { get; init; }
    public string? Error { get; init; }
    public Skill? Skill { get; init; }
}
