using Hermes.Agent.Execution;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace HermesDesktop.Tests.Services;

[TestClass]
public sealed class WindowsSandboxBackendTests
{
    [TestMethod]
    public void BuildSandboxConfiguration_UsesWindowsSandboxMappedFolders()
    {
        var xml = WindowsSandboxBackend.BuildSandboxConfiguration(
            @"C:\Temp\Hermes&Control",
            @"C:\Repos\Hermes.CS",
            readOnlyWorkspace: true,
            networking: false,
            vgpu: false);

        StringAssert.Contains(xml, "<Networking>Disable</Networking>");
        StringAssert.Contains(xml, "<VGpu>Disable</VGpu>");
        StringAssert.Contains(xml, @"<SandboxFolder>C:\HermesControl</SandboxFolder>");
        StringAssert.Contains(xml, @"<SandboxFolder>C:\HermesWorkspace</SandboxFolder>");
        StringAssert.Contains(xml, @"<HostFolder>C:\Temp\Hermes&amp;Control</HostFolder>");
        StringAssert.Contains(xml, "<ReadOnly>true</ReadOnly>");
        StringAssert.Contains(xml, @"powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\HermesControl\run.ps1");
    }
}
