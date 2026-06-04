namespace Hermes.Agent.Security;

using System.Text.RegularExpressions;

/// <summary>
/// Scans text for API keys, tokens, passwords, and other secrets.
/// Matches the patterns from the official Hermes Agent redact.py.
/// </summary>
public static class SecretScanner
{
    /// <summary>Known API key prefix patterns (from redact.py).</summary>
    private static readonly string[] PrefixPatterns =
    {
        @"sk-[A-Za-z0-9_-]{10,}",           // OpenAI / OpenRouter / Anthropic
        @"ghp_[A-Za-z0-9]{10,}",            // GitHub PAT (classic)
        @"github_pat_[A-Za-z0-9_]{10,}",    // GitHub PAT (fine-grained)
        @"gho_[A-Za-z0-9]{10,}",            // GitHub OAuth
        @"ghu_[A-Za-z0-9]{10,}",            // GitHub user-to-server
        @"ghs_[A-Za-z0-9]{10,}",            // GitHub server-to-server
        @"ghr_[A-Za-z0-9]{10,}",            // GitHub refresh token
        @"xox[baprs]-[A-Za-z0-9-]{10,}",    // Slack tokens
        @"AIza[A-Za-z0-9_-]{30,}",          // Google API keys
        @"pplx-[A-Za-z0-9]{10,}",           // Perplexity
        @"AKIA[A-Z0-9]{16}",                // AWS Access Key ID
        @"sk_live_[A-Za-z0-9]{10,}",        // Stripe live
        @"sk_test_[A-Za-z0-9]{10,}",        // Stripe test
        @"rk_live_[A-Za-z0-9]{10,}",        // Stripe restricted
        @"SG\.[A-Za-z0-9_-]{10,}",          // SendGrid
        @"hf_[A-Za-z0-9]{10,}",             // HuggingFace
        @"r8_[A-Za-z0-9]{10,}",             // Replicate
        @"npm_[A-Za-z0-9]{10,}",            // npm
        @"pypi-[A-Za-z0-9_-]{10,}",         // PyPI
        @"tvly-[A-Za-z0-9]{10,}",           // Tavily
        @"exa_[A-Za-z0-9]{10,}",            // Exa search
    };

    private static readonly Regex PrefixRegex = new(
        @"(?<![A-Za-z0-9_-])(" + string.Join("|", PrefixPatterns) + @")(?![A-Za-z0-9_-])",
        RegexOptions.Compiled);

    /// <summary>Authorization header pattern.</summary>
    private static readonly Regex AuthHeaderRegex = new(
        @"(Authorization:\s*Bearer\s+)(\S+)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    /// <summary>JSON field patterns for secret values.</summary>
    private static readonly Regex JsonFieldRegex = new(
        @"(""(?:api_?[Kk]ey|token|secret|password|access_token|refresh_token|auth_token|bearer)"")\s*:\s*""([^""]+)""",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    /// <summary>Private key blocks.</summary>
    private static readonly Regex PrivateKeyRegex = new(
        @"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----",
        RegexOptions.Compiled);

    /// <summary>Database connection string passwords.</summary>
    private static readonly Regex DbConnStrRegex = new(
        @"((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:]+:)([^@]+)(@)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    /// <summary>URLs with embedded credentials (user:pass@host).</summary>
    private static readonly Regex UrlCredentialRegex = new(
        @"(https?://[^:]+:)([^@]+)(@[^/\s]+)",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    /// <summary>Check if text contains any detectable secrets.</summary>
    public static bool ContainsSecrets(string? text)
    {
        if (string.IsNullOrEmpty(text)) return false;

        return PrefixRegex.IsMatch(text)
            || AuthHeaderRegex.IsMatch(text)
            || JsonFieldRegex.IsMatch(text)
            || PrivateKeyRegex.IsMatch(text)
            || DbConnStrRegex.IsMatch(text)
            || UrlCredentialRegex.IsMatch(text);
    }

    /// <summary>
    /// Redact all detected secrets in the text, replacing them with [REDACTED].
    /// Safe to call on any string. Non-matching text passes through unchanged.
    /// </summary>
    public static string RedactSecrets(string? text)
    {
        if (string.IsNullOrEmpty(text)) return text ?? "";

        // Known prefix patterns
        text = PrefixRegex.Replace(text, m => MaskToken(m.Value));

        // Authorization headers
        text = AuthHeaderRegex.Replace(text, m => $"{m.Groups[1].Value}[REDACTED]");

        // JSON fields
        text = JsonFieldRegex.Replace(text, m => $"{m.Groups[1].Value}: \"[REDACTED]\"");

        // Private keys
        text = PrivateKeyRegex.Replace(text, "[REDACTED PRIVATE KEY]");

        // Database connection strings
        text = DbConnStrRegex.Replace(text, m => $"{m.Groups[1].Value}[REDACTED]{m.Groups[3].Value}");

        // URL credentials
        text = UrlCredentialRegex.Replace(text, m => $"{m.Groups[1].Value}[REDACTED]{m.Groups[3].Value}");

        return text;
    }

    /// <summary>
    /// Scan a URL for embedded credentials. Returns true if credentials are found.
    /// </summary>
    public static bool UrlContainsCredentials(string? url)
    {
        if (string.IsNullOrEmpty(url)) return false;
        return UrlCredentialRegex.IsMatch(url) || DbConnStrRegex.IsMatch(url);
    }

    private static string MaskToken(string token)
    {
        if (token.Length < 18)
            return "[REDACTED]";
        return $"{token[..6]}...[REDACTED]";
    }
}
