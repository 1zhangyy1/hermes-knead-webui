namespace Hermes.Agent.Wiki;

/// <summary>
/// Configuration for the wiki data layer.
/// </summary>
public sealed class WikiConfig
{
    public string WikiPath { get; init; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "wiki");
    public int MaxPageLines { get; init; } = 200;
    public int LogRotationThreshold { get; init; } = 500;
}
