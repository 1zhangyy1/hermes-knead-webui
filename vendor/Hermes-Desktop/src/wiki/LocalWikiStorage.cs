namespace Hermes.Agent.Wiki;

/// <summary>
/// Filesystem-backed wiki storage.
/// Resolves all paths against WikiConfig.WikiPath with path-traversal prevention.
/// Uses the same WriteThrough pattern as TranscriptStore for crash-safe writes.
/// </summary>
public sealed class LocalWikiStorage : IWikiStorage
{
    private readonly string _rootPath;
    private readonly SemaphoreSlim _writeLock = new(1, 1);

    public LocalWikiStorage(WikiConfig config)
    {
        _rootPath = Path.GetFullPath(config.WikiPath);
        Directory.CreateDirectory(_rootPath);
    }

    public async Task<string?> ReadFileAsync(string relativePath, CancellationToken ct = default)
    {
        var fullPath = ResolveSafe(relativePath);
        if (!File.Exists(fullPath))
            return null;

        return await File.ReadAllTextAsync(fullPath, ct);
    }

    public async Task WriteFileAsync(string relativePath, string content, CancellationToken ct = default)
    {
        var fullPath = ResolveSafe(relativePath);

        // Ensure parent directory exists
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);

        var bytes = System.Text.Encoding.UTF8.GetBytes(content);

        // WriteThrough pattern from TranscriptStore — data hits disk immediately
        await _writeLock.WaitAsync(ct);
        try
        {
            using var fs = new FileStream(
                fullPath,
                FileMode.Create,
                FileAccess.Write,
                FileShare.Read,
                bufferSize: 4096,
                FileOptions.WriteThrough | FileOptions.SequentialScan);
            await fs.WriteAsync(bytes, ct);
            await fs.FlushAsync(ct);
        }
        finally
        {
            _writeLock.Release();
        }
    }

    public Task<IReadOnlyList<string>> ListFilesAsync(string subdir = "", CancellationToken ct = default)
    {
        var searchDir = string.IsNullOrEmpty(subdir)
            ? _rootPath
            : ResolveSafe(subdir);

        if (!Directory.Exists(searchDir))
            return Task.FromResult<IReadOnlyList<string>>(Array.Empty<string>());

        var files = Directory.EnumerateFiles(searchDir, "*.md", SearchOption.AllDirectories)
            .Select(f => Path.GetRelativePath(_rootPath, f).Replace('\\', '/'))
            .OrderBy(f => f)
            .ToList();

        return Task.FromResult<IReadOnlyList<string>>(files);
    }

    public bool FileExists(string relativePath)
    {
        var fullPath = ResolveSafe(relativePath);
        return File.Exists(fullPath);
    }

    public async Task DeleteFileAsync(string relativePath, CancellationToken ct = default)
    {
        var fullPath = ResolveSafe(relativePath);
        if (File.Exists(fullPath))
        {
            await _writeLock.WaitAsync(ct);
            try
            {
                File.Delete(fullPath);
            }
            finally
            {
                _writeLock.Release();
            }
        }
    }

    public void CreateDirectory(string relativePath)
    {
        var fullPath = ResolveSafe(relativePath);
        Directory.CreateDirectory(fullPath);
    }

    /// <summary>
    /// Resolve a relative path against the wiki root with path-traversal prevention.
    /// Throws if the resolved path escapes the wiki root directory.
    /// </summary>
    private string ResolveSafe(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath))
            throw new ArgumentException("Path cannot be empty.", nameof(relativePath));

        // Normalize and resolve
        var combined = Path.Combine(_rootPath, relativePath);
        var fullPath = Path.GetFullPath(combined);

        // Path traversal check: resolved path must start with root
        if (!fullPath.StartsWith(_rootPath, StringComparison.OrdinalIgnoreCase))
            throw new UnauthorizedAccessException(
                $"Path traversal detected: '{relativePath}' resolves outside wiki root.");

        return fullPath;
    }
}
