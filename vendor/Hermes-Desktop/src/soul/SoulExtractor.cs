namespace Hermes.Agent.Soul;

using Hermes.Agent.Core;
using Hermes.Agent.LLM;
using Microsoft.Extensions.Logging;
using System.Text.RegularExpressions;

/// <summary>
/// LLM-powered extractor that analyzes transcripts for mistakes, habits,
/// and user profile signals. Used by the Dream consolidation service.
/// </summary>
public sealed class SoulExtractor
{
    private readonly IChatClient _chatClient;
    private readonly ILogger<SoulExtractor> _logger;

    public SoulExtractor(IChatClient chatClient, ILogger<SoulExtractor> logger)
    {
        _chatClient = chatClient;
        _logger = logger;
    }

    /// <summary>
    /// Analyze transcript text for soul signals: mistakes, habits, and user profile updates.
    /// </summary>
    public async Task<SoulExtractionResult> ExtractAsync(
        string transcriptText,
        string? existingUserProfile,
        CancellationToken ct)
    {
        var prompt = BuildExtractionPrompt(transcriptText, existingUserProfile);

        try
        {
            var response = await _chatClient.CompleteAsync(
                [new Message { Role = "user", Content = prompt }], ct);

            return ParseExtractionResponse(response);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Soul extraction failed");
            return new SoulExtractionResult();
        }
    }

    private static string BuildExtractionPrompt(string transcriptText, string? existingUserProfile)
    {
        var userProfileSection = string.IsNullOrWhiteSpace(existingUserProfile)
            ? "(no existing user profile)"
            : existingUserProfile;

        return $@"You are a behavioral analyst for an AI agent. Analyze this conversation transcript and extract behavioral signals.

## Existing User Profile
{userProfileSection}

## Recent Transcript
{transcriptText}

## Your Task
Identify these patterns in the conversation:

### MISTAKES
When the agent did something wrong and the user corrected it. Look for:
- ""No, that's wrong"", ""don't do that"", ""that's not right""
- User providing a correction after agent output
- Failed tool calls that the user had to guide

### HABITS
When the agent did something right and the user confirmed it. Look for:
- ""Perfect"", ""exactly"", ""that's great"", ""nice""
- User expressing satisfaction with an approach
- Successful patterns the agent should repeat

### USER PROFILE
New signals about who the user is:
- Technical skill level (novice/intermediate/expert)
- Preferred tools or approaches
- Communication style preferences
- Domain expertise

## Response Format
Return EXACTLY this format (include sections even if empty):

## MISTAKES
For each mistake:
```
CONTEXT: what was happening
MISTAKE: what went wrong
CORRECTION: what the user said/did to fix it
LESSON: what to do differently next time
```

## HABITS
For each habit:
```
CONTEXT: what was happening
HABIT: the good practice
FEEDBACK: what the user said
```

## USER_PROFILE_UPDATE
If there are significant new signals about the user, write a brief paragraph update.
Write NONE if no significant new signals.";
    }

    private SoulExtractionResult ParseExtractionResponse(string response)
    {
        var result = new SoulExtractionResult();

        // Parse mistakes
        var mistakeSection = ExtractSection(response, "## MISTAKES", "## ");
        if (mistakeSection is not null)
        {
            var blocks = Regex.Split(mistakeSection, @"(?=CONTEXT:)").Where(b => b.Trim().Length > 0);
            foreach (var block in blocks)
            {
                var context = ExtractField(block, "CONTEXT");
                var mistake = ExtractField(block, "MISTAKE");
                var correction = ExtractField(block, "CORRECTION");
                var lesson = ExtractField(block, "LESSON");

                if (lesson is not null)
                {
                    result.Mistakes.Add(new MistakeEntry
                    {
                        Context = context ?? "unknown",
                        Mistake = mistake ?? "unknown",
                        Correction = correction ?? "unknown",
                        Lesson = lesson
                    });
                }
            }
        }

        // Parse habits
        var habitSection = ExtractSection(response, "## HABITS", "## ");
        if (habitSection is not null)
        {
            var blocks = Regex.Split(habitSection, @"(?=CONTEXT:)").Where(b => b.Trim().Length > 0);
            foreach (var block in blocks)
            {
                var context = ExtractField(block, "CONTEXT");
                var habit = ExtractField(block, "HABIT");
                var feedback = ExtractField(block, "FEEDBACK");

                if (habit is not null)
                {
                    result.Habits.Add(new HabitEntry
                    {
                        Context = context ?? "unknown",
                        Habit = habit,
                        PositiveFeedback = feedback ?? "confirmed"
                    });
                }
            }
        }

        // Parse user profile update
        var profileSection = ExtractSection(response, "## USER_PROFILE_UPDATE", "## ");
        if (profileSection is not null)
        {
            var trimmed = profileSection.Trim();
            if (!string.Equals(trimmed, "NONE", StringComparison.OrdinalIgnoreCase)
                && trimmed.Length > 10)
            {
                result = new SoulExtractionResult
                {
                    Mistakes = result.Mistakes,
                    Habits = result.Habits,
                    UserProfileUpdate = trimmed
                };
            }
        }

        _logger.LogInformation(
            "Soul extraction: {Mistakes} mistakes, {Habits} habits, profile update: {HasProfile}",
            result.Mistakes.Count, result.Habits.Count, result.UserProfileUpdate is not null);

        return result;
    }

    private static string? ExtractSection(string text, string header, string nextHeaderPrefix)
    {
        var start = text.IndexOf(header, StringComparison.OrdinalIgnoreCase);
        if (start < 0) return null;
        start += header.Length;

        var end = text.IndexOf(nextHeaderPrefix, start);
        while (end >= 0 && end == start)
            end = text.IndexOf(nextHeaderPrefix, end + 1);

        return end > 0 ? text[start..end].Trim() : text[start..].Trim();
    }

    private static string? ExtractField(string block, string fieldName)
    {
        var pattern = $@"{fieldName}:\s*(.+?)(?:\n[A-Z_]+:|$)";
        var match = Regex.Match(block, pattern, RegexOptions.Singleline);
        return match.Success ? match.Groups[1].Value.Trim() : null;
    }
}
