using Hermes.Agent.Analytics;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace HermesDesktop.Tests.Analytics;

[TestClass]
public class InsightsDreamerTests
{
    private string _tempDir = "";
    private InsightsService _service = null!;

    [TestInitialize]
    public void SetUp()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"insights-dreamer-tests-{Guid.NewGuid():N}");
        Directory.CreateDirectory(_tempDir);
        _service = new InsightsService(_tempDir);
    }

    [TestCleanup]
    public void TearDown()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    // ── DreamerInsightStats initialised lazily ──

    [TestMethod]
    public void GetInsights_BeforeAnyDreamerCalls_DreamerIsNull()
    {
        var data = _service.GetInsights();
        Assert.IsNull(data.Dreamer, "Dreamer stats should be null until first bump");
    }

    // ── RecordDreamerWalk ──

    [TestMethod]
    public void RecordDreamerWalk_FirstCall_InitializesDreamerAndSetsWalksTo1()
    {
        _service.RecordDreamerWalk();

        var data = _service.GetInsights();
        Assert.IsNotNull(data.Dreamer);
        Assert.AreEqual(1L, data.Dreamer!.Walks);
    }

    [TestMethod]
    public void RecordDreamerWalk_MultipleCalls_AccumulatesWalks()
    {
        _service.RecordDreamerWalk();
        _service.RecordDreamerWalk();
        _service.RecordDreamerWalk();

        Assert.AreEqual(3L, _service.GetInsights().Dreamer!.Walks);
    }

    [TestMethod]
    public void RecordDreamerWalk_DoesNotAffectOtherCounters()
    {
        _service.RecordDreamerWalk();

        var dreamer = _service.GetInsights().Dreamer!;
        Assert.AreEqual(0L, dreamer.Digests);
        Assert.AreEqual(0L, dreamer.Builds);
        Assert.AreEqual(0L, dreamer.Signals);
    }

    // ── RecordDreamerDigest ──

    [TestMethod]
    public void RecordDreamerDigest_FirstCall_InitializesDreamerAndSetsDigestsTo1()
    {
        _service.RecordDreamerDigest();

        var data = _service.GetInsights();
        Assert.IsNotNull(data.Dreamer);
        Assert.AreEqual(1L, data.Dreamer!.Digests);
    }

    [TestMethod]
    public void RecordDreamerDigest_MultipleCalls_AccumulatesDigests()
    {
        _service.RecordDreamerDigest();
        _service.RecordDreamerDigest();

        Assert.AreEqual(2L, _service.GetInsights().Dreamer!.Digests);
    }

    [TestMethod]
    public void RecordDreamerDigest_DoesNotAffectWalks()
    {
        _service.RecordDreamerDigest();

        Assert.AreEqual(0L, _service.GetInsights().Dreamer!.Walks);
    }

    // ── RecordDreamerBuild ──

    [TestMethod]
    public void RecordDreamerBuild_FirstCall_InitializesDreamerAndSetsBuildsTo1()
    {
        _service.RecordDreamerBuild();

        var data = _service.GetInsights();
        Assert.IsNotNull(data.Dreamer);
        Assert.AreEqual(1L, data.Dreamer!.Builds);
    }

    [TestMethod]
    public void RecordDreamerBuild_MultipleCalls_AccumulatesBuilds()
    {
        _service.RecordDreamerBuild();
        _service.RecordDreamerBuild();
        _service.RecordDreamerBuild();
        _service.RecordDreamerBuild();

        Assert.AreEqual(4L, _service.GetInsights().Dreamer!.Builds);
    }

    // ── RecordDreamerSignal ──

    [TestMethod]
    public void RecordDreamerSignal_FirstCall_InitializesDreamerAndSetsSignalsTo1()
    {
        _service.RecordDreamerSignal();

        var data = _service.GetInsights();
        Assert.IsNotNull(data.Dreamer);
        Assert.AreEqual(1L, data.Dreamer!.Signals);
    }

    [TestMethod]
    public void RecordDreamerSignal_MultipleCalls_AccumulatesSignals()
    {
        _service.RecordDreamerSignal();
        _service.RecordDreamerSignal();

        Assert.AreEqual(2L, _service.GetInsights().Dreamer!.Signals);
    }

    // ── Mixed usage ──

    [TestMethod]
    public void AllDreamerCounters_MixedCalls_AllCountersIndependent()
    {
        _service.RecordDreamerWalk();
        _service.RecordDreamerWalk();
        _service.RecordDreamerDigest();
        _service.RecordDreamerBuild();
        _service.RecordDreamerBuild();
        _service.RecordDreamerBuild();
        _service.RecordDreamerSignal();
        _service.RecordDreamerSignal();
        _service.RecordDreamerSignal();
        _service.RecordDreamerSignal();

        var dreamer = _service.GetInsights().Dreamer!;
        Assert.AreEqual(2L, dreamer.Walks);
        Assert.AreEqual(1L, dreamer.Digests);
        Assert.AreEqual(3L, dreamer.Builds);
        Assert.AreEqual(4L, dreamer.Signals);
    }

    // ── BumpDreamer initialises Dreamer lazily (even when called on fresh data) ──

    [TestMethod]
    public void BumpDreamer_AlwaysInitialisesIfNull_ThenBumps()
    {
        // Call each method on a fresh service with no prior data
        _service.RecordDreamerWalk();
        _service.RecordDreamerDigest();
        _service.RecordDreamerBuild();
        _service.RecordDreamerSignal();

        var dreamer = _service.GetInsights().Dreamer;
        Assert.IsNotNull(dreamer);
        Assert.IsTrue(dreamer!.Walks > 0);
        Assert.IsTrue(dreamer.Digests > 0);
        Assert.IsTrue(dreamer.Builds > 0);
        Assert.IsTrue(dreamer.Signals > 0);
    }

    // ── Persistence via Save/Load ──

    [TestMethod]
    public void RecordDreamerWalk_ThenSave_PersistedAcrossReload()
    {
        _service.RecordDreamerWalk();
        _service.RecordDreamerWalk();
        _service.Save();

        // New instance loaded from same directory
        var reloaded = new InsightsService(_tempDir);
        Assert.AreEqual(2L, reloaded.GetInsights().Dreamer!.Walks);
    }

    [TestMethod]
    public void AllDreamerCounters_SaveAndReload_RoundTrip()
    {
        _service.RecordDreamerWalk();
        _service.RecordDreamerDigest();
        _service.RecordDreamerBuild();
        _service.RecordDreamerSignal();
        _service.Save();

        var reloaded = new InsightsService(_tempDir);
        var dreamer = reloaded.GetInsights().Dreamer!;

        Assert.AreEqual(1L, dreamer.Walks);
        Assert.AreEqual(1L, dreamer.Digests);
        Assert.AreEqual(1L, dreamer.Builds);
        Assert.AreEqual(1L, dreamer.Signals);
    }

    // ── Thread safety ──

    [TestMethod]
    public void RecordDreamerWalk_ConcurrentCalls_DoesNotCorruptCounter()
    {
        const int threadCount = 50;
        var tasks = Enumerable.Range(0, threadCount)
            .Select(_ => Task.Run(() => _service.RecordDreamerWalk()))
            .ToArray();

        Task.WaitAll(tasks);

        Assert.AreEqual(threadCount, _service.GetInsights().Dreamer!.Walks);
    }

    [TestMethod]
    public void AllDreamerRecorders_ConcurrentCalls_AllCountersAccurate()
    {
        const int callsPerMethod = 20;
        var tasks = Enumerable.Range(0, callsPerMethod).SelectMany(_ => new[]
        {
            Task.Run(() => _service.RecordDreamerWalk()),
            Task.Run(() => _service.RecordDreamerDigest()),
            Task.Run(() => _service.RecordDreamerBuild()),
            Task.Run(() => _service.RecordDreamerSignal())
        }).ToArray();

        Task.WaitAll(tasks);

        var dreamer = _service.GetInsights().Dreamer!;
        Assert.AreEqual(callsPerMethod, dreamer.Walks);
        Assert.AreEqual(callsPerMethod, dreamer.Digests);
        Assert.AreEqual(callsPerMethod, dreamer.Builds);
        Assert.AreEqual(callsPerMethod, dreamer.Signals);
    }

    // ── DreamerInsightStats data model ──

    [TestMethod]
    public void DreamerInsightStats_DefaultValues_AllZero()
    {
        var stats = new DreamerInsightStats();

        Assert.AreEqual(0L, stats.Walks);
        Assert.AreEqual(0L, stats.Digests);
        Assert.AreEqual(0L, stats.Builds);
        Assert.AreEqual(0L, stats.Signals);
    }

    [TestMethod]
    public void InsightsData_DreamerProperty_NullableAndSettable()
    {
        var data = new InsightsData();
        Assert.IsNull(data.Dreamer);

        data.Dreamer = new DreamerInsightStats { Walks = 5, Builds = 2 };
        Assert.IsNotNull(data.Dreamer);
        Assert.AreEqual(5L, data.Dreamer.Walks);
        Assert.AreEqual(2L, data.Dreamer.Builds);
    }
}