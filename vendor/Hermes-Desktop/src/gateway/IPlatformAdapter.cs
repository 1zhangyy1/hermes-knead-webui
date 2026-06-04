namespace Hermes.Agent.Gateway;

// ══════════════════════════════════════════════
// Platform Adapter Interface
// ══════════════════════════════════════════════
//
// Upstream ref: gateway/run.py BasePlatformAdapter
// 5 methods: connect, send, disconnect, set_message_handler, set_fatal_error_handler

/// <summary>
/// Interface for messaging platform adapters.
/// Each platform (Telegram, Discord, etc.) implements this to bridge
/// between platform-specific APIs and the unified gateway message pipeline.
/// </summary>
public interface IPlatformAdapter : IAsyncDisposable
{
    /// <summary>Which platform this adapter handles.</summary>
    Platform Platform { get; }

    /// <summary>Whether currently connected and receiving messages.</summary>
    bool IsConnected { get; }

    /// <summary>
    /// Authenticate and establish connection to the platform.
    /// Returns true on success. Failed connections are queued for retry.
    /// </summary>
    Task<bool> ConnectAsync(CancellationToken ct);

    /// <summary>
    /// Send a message to a specific chat on this platform.
    /// Handles chunking, format conversion, and media delivery.
    /// </summary>
    Task<DeliveryResult> SendAsync(OutboundMessage message, CancellationToken ct);

    /// <summary>
    /// Graceful disconnect — stop receiving messages, close connections.
    /// </summary>
    Task DisconnectAsync();

    /// <summary>
    /// Register the callback that handles incoming messages.
    /// The gateway sets this during startup before calling ConnectAsync.
    /// </summary>
    void SetMessageHandler(Func<MessageEvent, Task<string?>> handler);

    /// <summary>
    /// Register callback for fatal errors that require gateway attention.
    /// </summary>
    void SetErrorHandler(Action<Platform, Exception> handler);
}
