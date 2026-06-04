using Hermes.Agent.Core;
using Hermes.Agent.Dreamer;
using Hermes.Agent.LLM;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Moq;

namespace HermesDesktop.Tests.Dreamer;

[TestClass]
public class EchoDetectorTests
{
    private Mock<IChatClient> _mockClient = null!;
    private EchoDetector _detector = null!;

    [TestInitialize]
    public void SetUp()
    {
        _mockClient = new Mock<IChatClient>();
        _detector = new EchoDetector(_mockClient.Object, NullLogger<EchoDetector>.Instance);
    }

    // ── Basic scoring ──

    [TestMethod]
    public async Task ScoreEchoAsync_LlmReturns1_Returns1()
    {
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync("1");

        var result = await _detector.ScoreEchoAsync("new walk", null, CancellationToken.None);

        Assert.AreEqual(1, result);
    }

    [TestMethod]
    public async Task ScoreEchoAsync_LlmReturns5_Returns5()
    {
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync("5");

        var result = await _detector.ScoreEchoAsync("new walk", "prior walk", CancellationToken.None);

        Assert.AreEqual(5, result);
    }

    [TestMethod]
    public async Task ScoreEchoAsync_LlmReturns3WithExtraText_ReturnsFirstDigit()
    {
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync("Score: 3 out of 5");

        var result = await _detector.ScoreEchoAsync("new walk", "prior", CancellationToken.None);

        Assert.AreEqual(3, result);
    }

    [TestMethod]
    public async Task ScoreEchoAsync_LlmReturnsOnlyNonDigits_ReturnsNeutral3()
    {
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync("no digits here");

        var result = await _detector.ScoreEchoAsync("new walk", "prior", CancellationToken.None);

        Assert.AreEqual(3, result);
    }

    [TestMethod]
    public async Task ScoreEchoAsync_LlmReturnsOutOfRangeDigit0_ReturnsNeutral3()
    {
        // '0' is not in 1-5 range, should fall through to neutral
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync("0");

        var result = await _detector.ScoreEchoAsync("new walk", null, CancellationToken.None);

        Assert.AreEqual(3, result);
    }

    [TestMethod]
    public async Task ScoreEchoAsync_LlmReturnsDigit6_ReturnsNeutral3()
    {
        // '6' is not in 1-5 range
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync("6");

        var result = await _detector.ScoreEchoAsync("new walk", null, CancellationToken.None);

        Assert.AreEqual(3, result);
    }

    // ── Fallback on exception ──

    [TestMethod]
    public async Task ScoreEchoAsync_LlmThrowsException_ReturnsNeutral3()
    {
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ThrowsAsync(new HttpRequestException("network error"));

        var result = await _detector.ScoreEchoAsync("new walk", null, CancellationToken.None);

        Assert.AreEqual(3, result);
    }

    [TestMethod]
    public async Task ScoreEchoAsync_LlmThrowsTimeoutException_ReturnsNeutral3()
    {
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ThrowsAsync(new TimeoutException("timed out"));

        var result = await _detector.ScoreEchoAsync("new walk", "prior", CancellationToken.None);

        Assert.AreEqual(3, result);
    }

    // ── Cancellation propagation ──

    [TestMethod]
    public async Task ScoreEchoAsync_CancellationToken_OperationCanceledException_IsRethrown()
    {
        using var cts = new CancellationTokenSource();
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ThrowsAsync(new OperationCanceledException());

        await Assert.ThrowsExceptionAsync<OperationCanceledException>(
            () => _detector.ScoreEchoAsync("walk", null, cts.Token));
    }

    [TestMethod]
    public async Task ScoreEchoAsync_TaskCanceledException_IsRethrown()
    {
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .ThrowsAsync(new TaskCanceledException("task was cancelled"));

        await Assert.ThrowsExceptionAsync<TaskCanceledException>(
            () => _detector.ScoreEchoAsync("walk", null, CancellationToken.None));
    }

    // ── Null / empty prior walk ──

    [TestMethod]
    public async Task ScoreEchoAsync_NullPriorWalk_IncludesNonePlaceholderInPrompt()
    {
        string capturedPrompt = "";
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .Callback<IEnumerable<Message>, CancellationToken>((msgs, _) =>
                   {
                       capturedPrompt = msgs.First().Content ?? "";
                   })
                   .ReturnsAsync("2");

        await _detector.ScoreEchoAsync("new walk text", null, CancellationToken.None);

        Assert.IsTrue(capturedPrompt.Contains("(none)"), "Prompt should contain '(none)' for null prior walk");
    }

    [TestMethod]
    public async Task ScoreEchoAsync_EmptyPriorWalk_IncludesNonePlaceholderInPrompt()
    {
        string capturedPrompt = "";
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .Callback<IEnumerable<Message>, CancellationToken>((msgs, _) =>
                   {
                       capturedPrompt = msgs.First().Content ?? "";
                   })
                   .ReturnsAsync("2");

        await _detector.ScoreEchoAsync("new walk", "   ", CancellationToken.None);

        Assert.IsTrue(capturedPrompt.Contains("(none)"), "Prompt should contain '(none)' for whitespace prior walk");
    }

    // ── Prompt contains walk text ──

    [TestMethod]
    public async Task ScoreEchoAsync_SendsMessageWithUserRole()
    {
        IEnumerable<Message>? capturedMessages = null;
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .Callback<IEnumerable<Message>, CancellationToken>((msgs, _) => capturedMessages = msgs)
                   .ReturnsAsync("2");

        await _detector.ScoreEchoAsync("walk content", "prior", CancellationToken.None);

        Assert.IsNotNull(capturedMessages);
        Assert.AreEqual("user", capturedMessages!.First().Role);
    }

    // ── Long inputs are truncated ──

    [TestMethod]
    public async Task ScoreEchoAsync_LongWalkText_TruncatedTo6000Chars()
    {
        var longWalk = new string('W', 10_000);
        int capturedPromptLength = 0;
        _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                   .Callback<IEnumerable<Message>, CancellationToken>((msgs, _) =>
                   {
                       capturedPromptLength = msgs.First().Content?.Length ?? 0;
                   })
                   .ReturnsAsync("1");

        await _detector.ScoreEchoAsync(longWalk, null, CancellationToken.None);

        // Prompt length should be well below 10000 chars (walk truncated to 6000)
        Assert.IsTrue(capturedPromptLength < 10_000, $"Prompt too long: {capturedPromptLength}");
    }

    // ── Return value range ──

    [TestMethod]
    public async Task ScoreEchoAsync_AllValidResponses_ReturnCorrectValues()
    {
        for (int expected = 1; expected <= 5; expected++)
        {
            var localExpected = expected;
            _mockClient.Setup(c => c.CompleteAsync(It.IsAny<IEnumerable<Message>>(), It.IsAny<CancellationToken>()))
                       .ReturnsAsync(localExpected.ToString());

            var result = await _detector.ScoreEchoAsync("walk", "prior", CancellationToken.None);
            Assert.AreEqual(localExpected, result, $"Expected {localExpected}, got {result}");
        }
    }
}