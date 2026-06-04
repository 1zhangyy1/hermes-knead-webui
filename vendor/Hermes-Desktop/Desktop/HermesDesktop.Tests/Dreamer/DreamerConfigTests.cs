using Hermes.Agent.Dreamer;
using Hermes.Agent.LLM;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace HermesDesktop.Tests.Dreamer;

[TestClass]
public class DreamerConfigTests
{
    private string _tempDir = "";

    [TestInitialize]
    public void SetUp()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"dreamer-cfg-tests-{Guid.NewGuid():N}");
        Directory.CreateDirectory(_tempDir);
    }

    [TestCleanup]
    public void TearDown()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    private string WriteCfg(string content)
    {
        var path = Path.Combine(_tempDir, "config.yaml");
        File.WriteAllText(path, content);
        return path;
    }

    // ── Defaults when file absent ──

    [TestMethod]
    public void Load_FileDoesNotExist_ReturnsDefaults()
    {
        var c = DreamerConfig.Load(Path.Combine(_tempDir, "nonexistent.yaml"));

        Assert.IsFalse(c.Enabled);
        Assert.AreEqual("ollama", c.WalkProvider);
        Assert.AreEqual("qwen3.5:latest", c.WalkModel);
        Assert.AreEqual("http://127.0.0.1:11434/v1", c.WalkBaseUrl);
        Assert.AreEqual(1.1, c.WalkTemperature);
        Assert.AreEqual(2048, c.WalkMaxTokens);
        Assert.AreEqual(30, c.WalkIntervalMinutes);
        Assert.AreEqual(7.0, c.TriggerThreshold);
        Assert.AreEqual(4, c.MinWalksToTrigger);
        Assert.AreEqual("full", c.Autonomy);
        Assert.IsTrue(c.InputTranscripts);
        Assert.IsTrue(c.InputInbox);
        Assert.AreEqual("", c.DiscordChannelId);
        Assert.AreEqual(0, c.RssFeeds.Count);
    }

    // ── Defaults when dreamer: section absent ──

    [TestMethod]
    public void Load_NoDreamerSection_ReturnsDefaults()
    {
        var path = WriteCfg("llm:\n  model: gpt-4\n\nother:\n  key: value\n");
        var c = DreamerConfig.Load(path);

        Assert.IsFalse(c.Enabled);
        Assert.AreEqual("ollama", c.WalkProvider);
        Assert.AreEqual(30, c.WalkIntervalMinutes);
    }

    // ── Full section loading ──

    [TestMethod]
    public void Load_ValidDreamerSection_ParsesAllFields()
    {
        var path = WriteCfg("""
            agent:
              name: hermes
            dreamer:
              enabled: true
              walk_provider: ollama
              walk_model: llama3:8b
              walk_base_url: http://localhost:1234/v1
              walk_temperature: 0.9
              walk_max_tokens: 1024
              build_provider: openai
              build_model: gpt-4o-mini
              walk_interval_minutes: 15
              digest_times: 08:00,20:00
              discord_channel_id: 1234567890
              trigger_threshold: 5.5
              min_walks_to_trigger: 3
              autonomy: drafts
              input_transcripts: false
              input_inbox: false
              rss_feeds: https://example.com/feed.xml,https://other.com/rss
            other_section:
              foo: bar
            """);

        var c = DreamerConfig.Load(path);

        Assert.IsTrue(c.Enabled);
        Assert.AreEqual("ollama", c.WalkProvider);
        Assert.AreEqual("llama3:8b", c.WalkModel);
        Assert.AreEqual("http://localhost:1234/v1", c.WalkBaseUrl);
        Assert.AreEqual(0.9, c.WalkTemperature, 0.001);
        Assert.AreEqual(1024, c.WalkMaxTokens);
        Assert.AreEqual("openai", c.BuildProvider);
        Assert.AreEqual("gpt-4o-mini", c.BuildModel);
        Assert.AreEqual(15, c.WalkIntervalMinutes);
        Assert.AreEqual(2, c.DigestTimes.Count);
        Assert.AreEqual("08:00", c.DigestTimes[0]);
        Assert.AreEqual("20:00", c.DigestTimes[1]);
        Assert.AreEqual("1234567890", c.DiscordChannelId);
        Assert.AreEqual(5.5, c.TriggerThreshold, 0.001);
        Assert.AreEqual(3, c.MinWalksToTrigger);
        Assert.AreEqual("drafts", c.Autonomy);
        Assert.IsFalse(c.InputTranscripts);
        Assert.IsFalse(c.InputInbox);
        Assert.AreEqual(2, c.RssFeeds.Count);
        Assert.AreEqual("https://example.com/feed.xml", c.RssFeeds[0]);
    }

    // ── ParseBool variants ──

    [TestMethod]
    public void Load_EnabledTrue_Recognized()
    {
        var path = WriteCfg("dreamer:\n  enabled: true\n");
        Assert.IsTrue(DreamerConfig.Load(path).Enabled);
    }

    [TestMethod]
    public void Load_EnabledYes_Recognized()
    {
        var path = WriteCfg("dreamer:\n  enabled: yes\n");
        Assert.IsTrue(DreamerConfig.Load(path).Enabled);
    }

    [TestMethod]
    public void Load_EnabledOne_Recognized()
    {
        var path = WriteCfg("dreamer:\n  enabled: 1\n");
        Assert.IsTrue(DreamerConfig.Load(path).Enabled);
    }

    [TestMethod]
    public void Load_EnabledFalse_Recognized()
    {
        var path = WriteCfg("dreamer:\n  enabled: false\n");
        Assert.IsFalse(DreamerConfig.Load(path).Enabled);
    }

    [TestMethod]
    public void Load_InputTranscriptsCaseInsensitive_Parsed()
    {
        var path = WriteCfg("dreamer:\n  input_transcripts: TRUE\n");
        Assert.IsTrue(DreamerConfig.Load(path).InputTranscripts);
    }

    // ── WalkIntervalMinutes clamping ──

    [TestMethod]
    public void Load_WalkIntervalMinutes_ClampedToMinimumOne()
    {
        var path = WriteCfg("dreamer:\n  walk_interval_minutes: 0\n");
        Assert.AreEqual(1, DreamerConfig.Load(path).WalkIntervalMinutes);
    }

    [TestMethod]
    public void Load_WalkIntervalMinutes_ClampedToMaximum1440()
    {
        var path = WriteCfg("dreamer:\n  walk_interval_minutes: 9999\n");
        Assert.AreEqual(24 * 60, DreamerConfig.Load(path).WalkIntervalMinutes);
    }

    [TestMethod]
    public void Load_WalkIntervalMinutes_ValidValueRetained()
    {
        var path = WriteCfg("dreamer:\n  walk_interval_minutes: 60\n");
        Assert.AreEqual(60, DreamerConfig.Load(path).WalkIntervalMinutes);
    }

    // ── DigestTimes validation ──

    [TestMethod]
    public void Load_DigestTimes_InvalidFormatsFiltered()
    {
        var path = WriteCfg("dreamer:\n  digest_times: 08:00,notaTime,25:00,08:61,12:00\n");
        var c = DreamerConfig.Load(path);

        // Only "08:00" and "12:00" are valid
        Assert.AreEqual(2, c.DigestTimes.Count);
        CollectionAssert.Contains(c.DigestTimes.ToList(), "08:00");
        CollectionAssert.Contains(c.DigestTimes.ToList(), "12:00");
    }

    [TestMethod]
    public void Load_DigestTimes_EmptyValue_KeepsDefaults()
    {
        var path = WriteCfg("dreamer:\n  enabled: true\n");
        var c = DreamerConfig.Load(path);
        // Default digest times preserved when key not present
        Assert.AreEqual(3, c.DigestTimes.Count);
    }

    // ── MinWalksToTrigger floor ──

    [TestMethod]
    public void Load_MinWalksToTrigger_ZeroClampedToOne()
    {
        var path = WriteCfg("dreamer:\n  min_walks_to_trigger: 0\n");
        Assert.AreEqual(1, DreamerConfig.Load(path).MinWalksToTrigger);
    }

    [TestMethod]
    public void Load_MinWalksToTrigger_NegativeClampedToOne()
    {
        var path = WriteCfg("dreamer:\n  min_walks_to_trigger: -5\n");
        Assert.AreEqual(1, DreamerConfig.Load(path).MinWalksToTrigger);
    }

    // ── Comment and whitespace handling ──

    [TestMethod]
    public void Load_CommentsAreIgnored()
    {
        var path = WriteCfg("""
            # top-level comment
            dreamer:
              # this is a comment
              enabled: true
              walk_model: test-model
            """);

        var c = DreamerConfig.Load(path);
        Assert.IsTrue(c.Enabled);
        Assert.AreEqual("test-model", c.WalkModel);
    }

    [TestMethod]
    public void Load_QuotedValues_StripsQuotes()
    {
        var path = WriteCfg("dreamer:\n  walk_model: \"my-model\"\n");
        Assert.AreEqual("my-model", DreamerConfig.Load(path).WalkModel);
    }

    [TestMethod]
    public void Load_SingleQuotedValues_StripsQuotes()
    {
        var path = WriteCfg("dreamer:\n  walk_model: 'my-model'\n");
        Assert.AreEqual("my-model", DreamerConfig.Load(path).WalkModel);
    }

    // ── Section stops at next top-level key ──

    [TestMethod]
    public void Load_StopsReadingAtNextTopLevelSection()
    {
        var path = WriteCfg("""
            dreamer:
              enabled: true
              walk_model: dreamer-model
            other:
              walk_model: should-not-bleed
            """);

        var c = DreamerConfig.Load(path);
        Assert.AreEqual("dreamer-model", c.WalkModel);
    }

    // ── ToWalkLlmConfig ──

    [TestMethod]
    public void ToWalkLlmConfig_MapsFieldsCorrectly()
    {
        var c = new DreamerConfig
        {
            WalkProvider = "ollama",
            WalkModel = "mymodel",
            WalkBaseUrl = "http://localhost:11434/v1",
            WalkTemperature = 0.9,
            WalkMaxTokens = 512
        };

        var cfg = c.ToWalkLlmConfig();

        Assert.AreEqual("ollama", cfg.Provider);
        Assert.AreEqual("mymodel", cfg.Model);
        Assert.AreEqual("http://localhost:11434/v1", cfg.BaseUrl);
        Assert.AreEqual(0.9, cfg.Temperature, 0.001);
        Assert.AreEqual(512, cfg.MaxTokens);
        Assert.AreEqual("none", cfg.AuthMode);
        Assert.AreEqual("", cfg.ApiKey);
    }

    // ── ToEchoLlmConfig ──

    [TestMethod]
    public void ToEchoLlmConfig_OverridesTemperatureAndMaxTokens()
    {
        var c = new DreamerConfig
        {
            WalkProvider = "ollama",
            WalkModel = "mymodel",
            WalkBaseUrl = "http://localhost:11434/v1",
            WalkTemperature = 1.1,
            WalkMaxTokens = 2048
        };

        var cfg = c.ToEchoLlmConfig();

        Assert.AreEqual("ollama", cfg.Provider);
        Assert.AreEqual("mymodel", cfg.Model);
        Assert.AreEqual(0.2, cfg.Temperature, 0.001);
        Assert.AreEqual(1024, cfg.MaxTokens);
        Assert.AreEqual("none", cfg.AuthMode);
    }

    [TestMethod]
    public void ToEchoLlmConfig_SharedProviderAndModel_WithWalkConfig()
    {
        var c = new DreamerConfig { WalkProvider = "custom", WalkModel = "custom-model" };
        var echo = c.ToEchoLlmConfig();
        var walk = c.ToWalkLlmConfig();

        Assert.AreEqual(walk.Provider, echo.Provider);
        Assert.AreEqual(walk.Model, echo.Model);
    }

    // ── ResolveHermesHome ──

    [TestMethod]
    public void ResolveHermesHome_UsesHermesHomeEnvVar_WhenSet()
    {
        var original = Environment.GetEnvironmentVariable("HERMES_HOME");
        try
        {
            Environment.SetEnvironmentVariable("HERMES_HOME", "/custom/hermes");
            var result = DreamerConfig.ResolveHermesHome();
            Assert.AreEqual("/custom/hermes", result);
        }
        finally
        {
            Environment.SetEnvironmentVariable("HERMES_HOME", original);
        }
    }

    [TestMethod]
    public void ResolveHermesHome_FallsBackToLocalAppData_WhenEnvVarEmpty()
    {
        var original = Environment.GetEnvironmentVariable("HERMES_HOME");
        try
        {
            Environment.SetEnvironmentVariable("HERMES_HOME", "");
            var result = DreamerConfig.ResolveHermesHome();
            Assert.IsTrue(result.EndsWith("hermes", StringComparison.OrdinalIgnoreCase));
            Assert.IsTrue(result.Length > 6);
        }
        finally
        {
            Environment.SetEnvironmentVariable("HERMES_HOME", original);
        }
    }

    // ── build_base_url (optional) ──

    [TestMethod]
    public void Load_BuildBaseUrl_ParsedWhenPresent()
    {
        var path = WriteCfg("dreamer:\n  build_base_url: https://api.example.com/v1\n");
        var c = DreamerConfig.Load(path);
        Assert.AreEqual("https://api.example.com/v1", c.BuildBaseUrl);
    }

    [TestMethod]
    public void Load_BuildBaseUrl_NullWhenAbsent()
    {
        var path = WriteCfg("dreamer:\n  enabled: true\n");
        var c = DreamerConfig.Load(path);
        Assert.IsNull(c.BuildBaseUrl);
    }
}