namespace Hermes.Agent.Wiki;

/// <summary>
/// Storage abstraction for wiki files.
/// Enables testing without touching the real filesystem.
/// </summary>
public interface IWikiStorage
{
    Task<string?> ReadFileAsync(string relativePath, CancellationToken ct = default);
    Task WriteFileAsync(string relativePath, string content, CancellationToken ct = default);
    Task<IReadOnlyList<string>> ListFilesAsync(string subdir = "", CancellationToken ct = default);
    bool FileExists(string relativePath);
    Task DeleteFileAsync(string relativePath, CancellationToken ct = default);
    void CreateDirectory(string relativePath);
}
