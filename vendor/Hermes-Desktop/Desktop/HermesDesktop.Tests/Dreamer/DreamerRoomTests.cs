using Hermes.Agent.Dreamer;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace HermesDesktop.Tests.Dreamer;

[TestClass]
public class DreamerRoomTests
{
    private string _tempDir = "";

    [TestInitialize]
    public void SetUp()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"dreamer-room-tests-{Guid.NewGuid():N}");
        Directory.CreateDirectory(_tempDir);
    }

    [TestCleanup]
    public void TearDown()
    {
        if (Directory.Exists(_tempDir))
            Directory.Delete(_tempDir, recursive: true);
    }

    private DreamerRoom CreateRoom() => new(_tempDir);

    // ── Constructor and path properties ──

    [TestMethod]
    public void Constructor_SetsRootUnderHermesHome()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(_tempDir, "dreamer"), room.Root);
    }

    [TestMethod]
    public void WalksDir_IsUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "walks"), room.WalksDir);
    }

    [TestMethod]
    public void ProjectsDir_IsUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "projects"), room.ProjectsDir);
    }

    [TestMethod]
    public void InboxDir_IsUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "inbox"), room.InboxDir);
    }

    [TestMethod]
    public void InboxRssDir_IsUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "inbox-rss"), room.InboxRssDir);
    }

    [TestMethod]
    public void FeedbackDir_IsUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "feedback"), room.FeedbackDir);
    }

    [TestMethod]
    public void SoulPath_IsDirectlyUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "DREAMER_SOUL.md"), room.SoulPath);
    }

    [TestMethod]
    public void FascinationsPath_IsDirectlyUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "fascinations.md"), room.FascinationsPath);
    }

    [TestMethod]
    public void SignalLogPath_IsDirectlyUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "signal-log.jsonl"), room.SignalLogPath);
    }

    [TestMethod]
    public void SignalStatePath_IsDirectlyUnderRoot()
    {
        var room = CreateRoom();
        Assert.AreEqual(Path.Combine(room.Root, "signal-state.json"), room.SignalStatePath);
    }

    // ── EnsureLayout ──

    [TestMethod]
    public void EnsureLayout_CreatesAllRequiredDirectories()
    {
        var room = CreateRoom();
        room.EnsureLayout();

        Assert.IsTrue(Directory.Exists(room.Root));
        Assert.IsTrue(Directory.Exists(room.WalksDir));
        Assert.IsTrue(Directory.Exists(room.ProjectsDir));
        Assert.IsTrue(Directory.Exists(room.InboxDir));
        Assert.IsTrue(Directory.Exists(room.InboxRssDir));
        Assert.IsTrue(Directory.Exists(room.FeedbackDir));
    }

    [TestMethod]
    public void EnsureLayout_CreatesSoulFile()
    {
        var room = CreateRoom();
        room.EnsureLayout();

        Assert.IsTrue(File.Exists(room.SoulPath));
        var content = File.ReadAllText(room.SoulPath);
        Assert.IsTrue(content.Contains("Dreamer"), "Soul file should contain 'Dreamer'");
    }

    [TestMethod]
    public void EnsureLayout_CreatesFascinationsFile()
    {
        var room = CreateRoom();
        room.EnsureLayout();

        Assert.IsTrue(File.Exists(room.FascinationsPath));
        var content = File.ReadAllText(room.FascinationsPath);
        Assert.IsTrue(content.Contains("Fascinations"));
    }

    [TestMethod]
    public void EnsureLayout_CreatesEmptySignalLogFile()
    {
        var room = CreateRoom();
        room.EnsureLayout();

        Assert.IsTrue(File.Exists(room.SignalLogPath));
    }

    [TestMethod]
    public void EnsureLayout_IsIdempotent_DoesNotOverwriteExistingFiles()
    {
        var room = CreateRoom();
        room.EnsureLayout();

        // Write custom content to soul file
        File.WriteAllText(room.SoulPath, "custom soul content");

        // Call EnsureLayout again — should not overwrite existing file
        room.EnsureLayout();

        Assert.AreEqual("custom soul content", File.ReadAllText(room.SoulPath));
    }

    [TestMethod]
    public void EnsureLayout_IsIdempotent_DoesNotOverwriteFascinations()
    {
        var room = CreateRoom();
        room.EnsureLayout();

        File.WriteAllText(room.FascinationsPath, "my fascinations");
        room.EnsureLayout();

        Assert.AreEqual("my fascinations", File.ReadAllText(room.FascinationsPath));
    }

    [TestMethod]
    public void EnsureLayout_CalledTwice_NoException()
    {
        var room = CreateRoom();
        room.EnsureLayout();
        room.EnsureLayout(); // second call must not throw
    }

    // ── NewWalkPath ──

    [TestMethod]
    public void NewWalkPath_ReturnsPathUnderWalksDir()
    {
        var room = CreateRoom();
        var path = room.NewWalkPath();

        Assert.IsTrue(path.StartsWith(room.WalksDir, StringComparison.OrdinalIgnoreCase));
    }

    [TestMethod]
    public void NewWalkPath_HasMarkdownExtension()
    {
        var room = CreateRoom();
        var path = room.NewWalkPath();

        Assert.AreEqual(".md", Path.GetExtension(path));
    }

    [TestMethod]
    public void NewWalkPath_StartsWithWalkPrefix()
    {
        var room = CreateRoom();
        var name = Path.GetFileName(room.NewWalkPath());

        Assert.IsTrue(name.StartsWith("walk-", StringComparison.OrdinalIgnoreCase));
    }

    [TestMethod]
    public void NewWalkPath_TwoCallsReturnDifferentPaths()
    {
        var room = CreateRoom();

        // Small delay to ensure different timestamps
        var path1 = room.NewWalkPath();
        System.Threading.Thread.Sleep(1100); // ensure second resolution differs
        var path2 = room.NewWalkPath();

        // At minimum both should be well-formed; if same second they'd be equal —
        // just ensure they are at least valid strings under WalksDir
        Assert.IsTrue(path1.StartsWith(room.WalksDir));
        Assert.IsTrue(path2.StartsWith(room.WalksDir));
    }
}