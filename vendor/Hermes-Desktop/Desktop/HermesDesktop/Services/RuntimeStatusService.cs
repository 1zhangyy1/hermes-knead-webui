using System;
using System.Threading;
using System.Threading.Tasks;
using Hermes.Agent.LLM;

namespace HermesDesktop.Services;

internal enum RuntimeConnectionState
{
    Checking = 0,
    Connected = 1,
    Offline = 2,
    Error = 3,
}

internal sealed record RuntimeStatusSnapshot(
    string Provider,
    string Model,
    string BaseUrl,
    string DisplayProvider,
    string DisplayModel,
    string DisplayBaseUrl,
    RuntimeConnectionState ConnectionState,
    string ConnectionDetail);

/// <summary>
/// Unified source for model/provider/connection runtime status used by desktop pages.
/// </summary>
internal sealed class RuntimeStatusService
{
    private readonly HermesChatService _chatService;
    private readonly ChatClientFactory _chatClientFactory;

    public RuntimeStatusService(
        HermesChatService chatService,
        ChatClientFactory chatClientFactory)
    {
        _chatService = chatService;
        _chatClientFactory = chatClientFactory;
    }

    public RuntimeStatusSnapshot GetConfiguredSnapshot()
    {
        return CreateSnapshot(RuntimeConnectionState.Checking, string.Empty);
    }

    public async Task<RuntimeStatusSnapshot> RefreshAsync(CancellationToken ct)
    {
        var configured = CreateSnapshot(RuntimeConnectionState.Checking, string.Empty);

        try
        {
            var (isHealthy, detail) = await _chatService.CheckHealthAsync(ct).ConfigureAwait(false);
            return configured with
            {
                ConnectionState = isHealthy ? RuntimeConnectionState.Connected : RuntimeConnectionState.Offline,
                ConnectionDetail = detail ?? string.Empty,
            };
        }
        catch (Exception ex)
        {
            return configured with
            {
                ConnectionState = RuntimeConnectionState.Error,
                ConnectionDetail = ex.Message,
            };
        }
    }

    private RuntimeStatusSnapshot CreateSnapshot(RuntimeConnectionState state, string detail)
    {
        var runtimeConfig = _chatClientFactory.CurrentConfig;
        var provider = NormalizeProvider(runtimeConfig.Provider);
        var model = string.IsNullOrWhiteSpace(runtimeConfig.Model)
            ? HermesEnvironment.DefaultModel
            : runtimeConfig.Model;
        var baseUrl = string.IsNullOrWhiteSpace(runtimeConfig.BaseUrl)
            ? HermesEnvironment.ModelBaseUrl
            : runtimeConfig.BaseUrl;

        return new RuntimeStatusSnapshot(
            Provider: provider,
            Model: model,
            BaseUrl: baseUrl,
            DisplayProvider: HermesEnvironment.PrivacyModeEnabled ? "configured" : provider,
            DisplayModel: HermesEnvironment.PrivacyModeEnabled ? "configured local model" : model,
            DisplayBaseUrl: HermesEnvironment.PrivacyModeEnabled ? "Configured local endpoint" : baseUrl,
            ConnectionState: state,
            ConnectionDetail: detail);
    }

    private static string NormalizeProvider(string provider)
    {
        return string.Equals(provider, "custom", StringComparison.OrdinalIgnoreCase)
            ? "local"
            : provider;
    }
}
