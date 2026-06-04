using Hermes.Agent.Security;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace HermesDesktop.Tests.Security;

[TestClass]
public class ShellSecurityAnalyzerTests
{
    [TestMethod]
    public void Analyze_SimpleReadCommand_IsSafe()
    {
        var analyzer = new ShellSecurityAnalyzer();

        var result = analyzer.Analyze("ls -la");

        Assert.AreEqual(SecurityClassification.Safe, result.Classification);
    }

    [TestMethod]
    public void Analyze_WriteCommand_WhenWritesDisabled_IsDangerous()
    {
        var analyzer = new ShellSecurityAnalyzer();
        var context = new ShellContext
        {
            AllowFileSystemWrite = false
        };

        var result = analyzer.Analyze("mkdir output", context);

        Assert.AreEqual(SecurityClassification.Dangerous, result.Classification);
        StringAssert.Contains(result.Reason ?? string.Empty, "Filesystem writes are disabled");
    }

    [TestMethod]
    public void Analyze_SubprocessCommand_WhenSubprocessDisabled_IsDangerous()
    {
        var analyzer = new ShellSecurityAnalyzer();
        var context = new ShellContext
        {
            AllowSubprocess = false
        };

        var result = analyzer.Analyze("python script.py", context);

        Assert.AreEqual(SecurityClassification.Dangerous, result.Classification);
        StringAssert.Contains(result.Reason ?? string.Empty, "Subprocess execution not allowed");
    }

    [TestMethod]
    public void Analyze_SensitivePathWrite_IsDangerous()
    {
        var analyzer = new ShellSecurityAnalyzer();

        var result = analyzer.Analyze("touch /etc/shadow");

        Assert.AreEqual(SecurityClassification.Dangerous, result.Classification);
        StringAssert.Contains(result.Reason ?? string.Empty, "sensitive filesystem location");
    }

    [TestMethod]
    public void Analyze_PathTraversalPattern_IsNeedsReview()
    {
        var analyzer = new ShellSecurityAnalyzer();

        var result = analyzer.Analyze("cp artifact.txt ../../secret.txt");

        Assert.AreEqual(SecurityClassification.NeedsReview, result.Classification);
        Assert.IsTrue(
            (result.Reason ?? string.Empty).Contains("Path traversal", StringComparison.Ordinal) ||
            (result.Warnings?.Any(w => w.Contains("Path traversal", StringComparison.Ordinal)) ?? false));
    }
}
