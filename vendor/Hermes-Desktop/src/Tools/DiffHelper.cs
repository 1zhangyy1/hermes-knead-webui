namespace Hermes.Agent.Tools;

/// <summary>
/// Simple unified diff utility matching the official Hermes Agent file_operations.py _unified_diff.
/// Takes old and new content, produces a unified diff string showing added/removed lines.
/// </summary>
public static class DiffHelper
{
    /// <summary>
    /// Generate a unified diff between old and new content.
    /// Returns a string in unified diff format (--- a/file, +++ b/file, @@ hunks).
    /// </summary>
    public static string UnifiedDiff(string oldContent, string newContent, string filename)
    {
        var oldLines = (oldContent ?? "").Split('\n');
        var newLines = (newContent ?? "").Split('\n');

        var sb = new System.Text.StringBuilder();
        sb.AppendLine($"--- a/{filename}");
        sb.AppendLine($"+++ b/{filename}");

        // Simple diff algorithm: find contiguous chunks of changes
        var hunks = ComputeHunks(oldLines, newLines);

        foreach (var hunk in hunks)
        {
            sb.AppendLine($"@@ -{hunk.OldStart + 1},{hunk.OldCount} +{hunk.NewStart + 1},{hunk.NewCount} @@");
            foreach (var line in hunk.Lines)
            {
                sb.AppendLine(line);
            }
        }

        return sb.ToString();
    }

    private sealed class Hunk
    {
        public int OldStart { get; set; }
        public int OldCount { get; set; }
        public int NewStart { get; set; }
        public int NewCount { get; set; }
        public List<string> Lines { get; } = new();
    }

    private static List<Hunk> ComputeHunks(string[] oldLines, string[] newLines)
    {
        // Use a simple LCS-based diff approach
        var lcs = ComputeLcs(oldLines, newLines);
        var hunks = new List<Hunk>();

        int oi = 0, ni = 0, li = 0;
        Hunk? currentHunk = null;
        int contextLines = 3;

        while (oi < oldLines.Length || ni < newLines.Length)
        {
            if (li < lcs.Count && oi < oldLines.Length && ni < newLines.Length &&
                lcs[li].OldIndex == oi && lcs[li].NewIndex == ni)
            {
                // Lines match — context
                if (currentHunk is not null)
                {
                    currentHunk.Lines.Add($" {oldLines[oi]}");
                    currentHunk.OldCount++;
                    currentHunk.NewCount++;
                }
                oi++;
                ni++;
                li++;
            }
            else
            {
                // Lines differ — start or extend a hunk
                if (currentHunk is null)
                {
                    currentHunk = new Hunk
                    {
                        OldStart = Math.Max(0, oi - contextLines),
                        NewStart = Math.Max(0, ni - contextLines),
                    };

                    // Add context before
                    var contextStart = Math.Max(0, oi - contextLines);
                    for (int c = contextStart; c < oi; c++)
                    {
                        currentHunk.Lines.Add($" {oldLines[c]}");
                        currentHunk.OldCount++;
                        currentHunk.NewCount++;
                    }
                }

                // Add removed lines from old until next LCS match or end
                while (oi < oldLines.Length &&
                       (li >= lcs.Count || lcs[li].OldIndex != oi))
                {
                    currentHunk.Lines.Add($"-{oldLines[oi]}");
                    currentHunk.OldCount++;
                    oi++;
                }

                // Add added lines from new until next LCS match or end
                while (ni < newLines.Length &&
                       (li >= lcs.Count || lcs[li].NewIndex != ni))
                {
                    currentHunk.Lines.Add($"+{newLines[ni]}");
                    currentHunk.NewCount++;
                    ni++;
                }

                // Check if we should close the hunk (no more changes coming soon)
                if (li < lcs.Count && currentHunk is not null)
                {
                    // If the next matching pair is far away, close the hunk
                    var nextOld = lcs[li].OldIndex;
                    if (nextOld - oi > contextLines * 2)
                    {
                        // Add trailing context
                        for (int c = 0; c < contextLines && oi + c < oldLines.Length && li + c < lcs.Count; c++)
                        {
                            if (lcs[li + c].OldIndex != oi + c) break;
                            currentHunk.Lines.Add($" {oldLines[oi + c]}");
                            currentHunk.OldCount++;
                            currentHunk.NewCount++;
                        }
                        hunks.Add(currentHunk);
                        currentHunk = null;
                    }
                }
            }
        }

        if (currentHunk is not null && currentHunk.Lines.Count > 0)
        {
            hunks.Add(currentHunk);
        }

        // If no hunks were created but content differs, create a simple full diff
        if (hunks.Count == 0 && !string.Join("\n", oldLines).Equals(string.Join("\n", newLines)))
        {
            var hunk = new Hunk { OldStart = 0, NewStart = 0 };
            foreach (var line in oldLines)
            {
                hunk.Lines.Add($"-{line}");
                hunk.OldCount++;
            }
            foreach (var line in newLines)
            {
                hunk.Lines.Add($"+{line}");
                hunk.NewCount++;
            }
            hunks.Add(hunk);
        }

        return hunks;
    }

    private sealed record LcsEntry(int OldIndex, int NewIndex);

    private static List<LcsEntry> ComputeLcs(string[] oldLines, string[] newLines)
    {
        // Standard LCS with DP for reasonable-size files, patience for large files
        if (oldLines.Length > 500 || newLines.Length > 500)
            return ComputeLcsGreedy(oldLines, newLines);

        var m = oldLines.Length;
        var n = newLines.Length;
        var dp = new int[m + 1, n + 1];

        for (int i = m - 1; i >= 0; i--)
        {
            for (int j = n - 1; j >= 0; j--)
            {
                if (oldLines[i] == newLines[j])
                    dp[i, j] = dp[i + 1, j + 1] + 1;
                else
                    dp[i, j] = Math.Max(dp[i + 1, j], dp[i, j + 1]);
            }
        }

        var result = new List<LcsEntry>();
        int oi = 0, ni = 0;
        while (oi < m && ni < n)
        {
            if (oldLines[oi] == newLines[ni])
            {
                result.Add(new LcsEntry(oi, ni));
                oi++;
                ni++;
            }
            else if (dp[oi + 1, ni] >= dp[oi, ni + 1])
                oi++;
            else
                ni++;
        }

        return result;
    }

    /// <summary>Greedy LCS for large files (O(n) approximation).</summary>
    private static List<LcsEntry> ComputeLcsGreedy(string[] oldLines, string[] newLines)
    {
        // Build index of new lines
        var newIndex = new Dictionary<string, List<int>>();
        for (int i = 0; i < newLines.Length; i++)
        {
            if (!newIndex.TryGetValue(newLines[i], out var list))
            {
                list = new List<int>();
                newIndex[newLines[i]] = list;
            }
            list.Add(i);
        }

        var result = new List<LcsEntry>();
        int lastNi = -1;
        for (int oi = 0; oi < oldLines.Length; oi++)
        {
            if (newIndex.TryGetValue(oldLines[oi], out var positions))
            {
                // Find the first position after lastNi
                var next = positions.FirstOrDefault(p => p > lastNi, -1);
                if (next >= 0)
                {
                    result.Add(new LcsEntry(oi, next));
                    lastNi = next;
                }
            }
        }

        return result;
    }
}
