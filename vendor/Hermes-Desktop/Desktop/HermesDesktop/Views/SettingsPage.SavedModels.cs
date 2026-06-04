using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Hermes.Agent.LLM;
using HermesDesktop.Services;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace HermesDesktop.Views;

/// <summary>
/// Bundle E.7 — SavedModelProfile registry surfaced inside SettingsPage.
/// Pure CRUD over <see cref="SavedModelStore"/>. "Set active" writes the profile
/// into the model section of <c>config.yaml</c> so the rest of the agent picks it up
/// the same way the existing model picker does.
/// </summary>
public sealed partial class SettingsPage
{
    private ObservableCollection<SavedModelRow> _savedModelRows = new();
    private string? _editingProfileId;

    private SavedModelStore Store => App.Services.GetRequiredService<SavedModelStore>();

    private void RefreshSavedModelProfiles()
    {
        try
        {
            _savedModelRows = new ObservableCollection<SavedModelRow>(
                Store.List().Select(SavedModelRow.From));
            SavedModelsList.ItemsSource = _savedModelRows;
            ClearProfileForm();
        }
        catch (Exception ex)
        {
            SetProfileStatus($"Failed to load profiles: {ex.Message}", isError: true);
        }
    }

    private void SavedModels_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (SavedModelsList.SelectedItem is not SavedModelRow row)
        {
            DeleteProfileBtn.IsEnabled = false;
            SetActiveProfileBtn.IsEnabled = false;
            return;
        }

        _editingProfileId = row.Id;
        ProfileNameBox.Text = row.Name;
        ProfileProviderBox.Text = row.Provider;
        ProfileModelIdBox.Text = row.ModelId;
        ProfileBaseUrlBox.Text = row.BaseUrl ?? string.Empty;
        ProfileApiKeyEnvBox.Text = row.ApiKeyEnvVar ?? string.Empty;
        ProfileContextBox.Value = row.ContextLength ?? double.NaN;
        ProfileFavoriteSwitch.IsOn = row.IsFavorite;

        DeleteProfileBtn.IsEnabled = true;
        SetActiveProfileBtn.IsEnabled = true;
    }

    private async void SaveProfile_Click(object sender, RoutedEventArgs e)
    {
        var draft = ReadProfileFormDraft();
        var validationError = ValidateProfileForm(draft);
        if (validationError is not null)
        {
            SetProfileStatus(validationError, isError: true);
            return;
        }

        var profile = BuildProfileFromDraft(draft);

        try
        {
            SaveProfileBtn.IsEnabled = false;
            await Store.UpsertAsync(profile, CancellationToken.None);
            _editingProfileId = profile.Id;
            RefreshSavedModelProfiles();
            SelectRowById(profile.Id);
            SetProfileStatus("Profile saved.", isError: false);
        }
        catch (Exception ex)
        {
            SetProfileStatus($"Save failed: {ex.Message}", isError: true);
        }
        finally
        {
            SaveProfileBtn.IsEnabled = true;
        }
    }

    private ProfileFormDraft ReadProfileFormDraft()
    {
        int? context = double.IsNaN(ProfileContextBox.Value) || ProfileContextBox.Value <= 0
            ? null
            : (int)ProfileContextBox.Value;

        return new ProfileFormDraft(
            (ProfileNameBox.Text ?? string.Empty).Trim(),
            (ProfileProviderBox.Text ?? string.Empty).Trim().ToLowerInvariant(),
            (ProfileModelIdBox.Text ?? string.Empty).Trim(),
            NullIfEmpty((ProfileBaseUrlBox.Text ?? string.Empty).Trim()),
            NullIfEmpty((ProfileApiKeyEnvBox.Text ?? string.Empty).Trim()),
            context,
            ProfileFavoriteSwitch.IsOn);
    }

    private static string? ValidateProfileForm(ProfileFormDraft draft)
    {
        if (string.IsNullOrWhiteSpace(draft.Name))
            return "Name is required.";
        if (string.IsNullOrWhiteSpace(draft.Provider))
            return "Provider is required.";
        if (string.IsNullOrWhiteSpace(draft.ModelId))
            return "Model ID is required.";
        if (draft.BaseUrl is not null && !IsValidEndpointUrl(draft.BaseUrl))
            return "Base URL must be an absolute http:// or https:// URL.";
        return null;
    }

    private SavedModelProfile BuildProfileFromDraft(ProfileFormDraft draft) =>
        _editingProfileId is null
            ? SavedModelProfile.Create(
                draft.Name, draft.Provider, draft.ModelId,
                draft.BaseUrl, draft.ApiKeyEnv, draft.Context, draft.Favorite)
            : new SavedModelProfile(
                _editingProfileId, draft.Name, draft.Provider, draft.ModelId,
                draft.BaseUrl, draft.ApiKeyEnv, draft.Context, draft.Favorite);

    private readonly record struct ProfileFormDraft(
        string Name,
        string Provider,
        string ModelId,
        string? BaseUrl,
        string? ApiKeyEnv,
        int? Context,
        bool Favorite);

    private void NewProfile_Click(object sender, RoutedEventArgs e)
    {
        SavedModelsList.SelectedItem = null;
        ClearProfileForm();
    }

    private async void DeleteProfile_Click(object sender, RoutedEventArgs e)
    {
        if (_editingProfileId is null) return;

        var confirm = new ContentDialog
        {
            Title = "Delete profile?",
            Content = "This removes the saved profile. Existing chats that already use the model continue normally.",
            PrimaryButtonText = "Delete",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
            XamlRoot = XamlRoot
        };
        var res = await confirm.ShowAsync();
        if (res != ContentDialogResult.Primary) return;

        try
        {
            await Store.DeleteAsync(_editingProfileId);
            RefreshSavedModelProfiles();
            SetProfileStatus("Profile deleted.", isError: false);
        }
        catch (Exception ex)
        {
            SetProfileStatus($"Delete failed: {ex.Message}", isError: true);
        }
    }

    private async void SetActiveProfile_Click(object sender, RoutedEventArgs e)
    {
        if (_editingProfileId is null) return;
        var profile = Store.Get(_editingProfileId);
        if (profile is null)
        {
            SetProfileStatus("Profile no longer exists. Refresh.", isError: true);
            return;
        }

        try
        {
            var settings = new Dictionary<string, string>
            {
                ["provider"] = profile.Provider,
                ["default"] = profile.ModelId,
            };
            if (!string.IsNullOrWhiteSpace(profile.BaseUrl))
                settings["base_url"] = profile.BaseUrl!;
            if (!string.IsNullOrWhiteSpace(profile.ApiKeyEnvVar))
            {
                settings["auth_mode"] = "api_key_env";
                settings["api_key_env"] = profile.ApiKeyEnvVar!;
            }

            await HermesEnvironment.SaveConfigSectionAsync("model", settings);
            // Reload the regular Model section so the user sees the change reflected.
            LoadModelSettings();
            await RefreshRuntimeStatusAsync();
            SetProfileStatus($"Activated {profile.Name}.", isError: false);
        }
        catch (Exception ex)
        {
            SetProfileStatus($"Activation failed: {ex.Message}", isError: true);
        }
    }

    private void ClearProfileForm()
    {
        _editingProfileId = null;
        ProfileNameBox.Text = string.Empty;
        ProfileProviderBox.Text = string.Empty;
        ProfileModelIdBox.Text = string.Empty;
        ProfileBaseUrlBox.Text = string.Empty;
        ProfileApiKeyEnvBox.Text = string.Empty;
        ProfileContextBox.Value = double.NaN;
        ProfileFavoriteSwitch.IsOn = false;
        DeleteProfileBtn.IsEnabled = false;
        SetActiveProfileBtn.IsEnabled = false;
    }

    private void SelectRowById(string id)
    {
        var row = _savedModelRows.FirstOrDefault(r => r.Id == id);
        if (row is not null) SavedModelsList.SelectedItem = row;
    }

    private void SetProfileStatus(string message, bool isError)
    {
        ProfileStatusText.Text = message;
        ProfileStatusText.Foreground = isError
            ? new SolidColorBrush(Windows.UI.Color.FromArgb(255, 0xE0, 0x70, 0x70))
            : new SolidColorBrush(Windows.UI.Color.FromArgb(255, 0x60, 0xE0, 0x90));
    }

    private static string? NullIfEmpty(string? s) =>
        string.IsNullOrWhiteSpace(s) ? null : s;

    /// <summary>
    /// Returns true if <paramref name="url"/> parses as an absolute URI and uses
    /// http or https. Anything else (relative paths, file://, javascript:,
    /// arbitrary schemes, malformed input) is rejected so it cannot reach the
    /// runtime config and produce opaque connection failures later.
    /// </summary>
    private static bool IsValidEndpointUrl(string url)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var parsed)) return false;
        return parsed.Scheme == Uri.UriSchemeHttps || parsed.Scheme == Uri.UriSchemeHttp;
    }
}

/// <summary>Display projection for the <see cref="ListView"/> bound to saved profiles.</summary>
public sealed class SavedModelRow
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Provider { get; set; } = "";
    public string ModelId { get; set; } = "";
    public string? BaseUrl { get; set; }
    public string? ApiKeyEnvVar { get; set; }
    public int? ContextLength { get; set; }
    public bool IsFavorite { get; set; }

    public string ProviderModelLine => $"{Provider} · {ModelId}";
    public string ContextLabel => ContextLength is { } c && c > 0 ? $"{c:N0} ctx" : "";
    public string FavoriteGlyph => IsFavorite ? "\uE735" : "\uE734";
    public SolidColorBrush FavoriteBrush => IsFavorite
        ? new SolidColorBrush(Windows.UI.Color.FromArgb(255, 0xE6, 0xBE, 0x3C))
        : new SolidColorBrush(Windows.UI.Color.FromArgb(255, 0x80, 0x80, 0x80));

    public static SavedModelRow From(SavedModelProfile p) => new()
    {
        Id = p.Id,
        Name = p.Name,
        Provider = p.Provider,
        ModelId = p.ModelId,
        BaseUrl = p.BaseUrl,
        ApiKeyEnvVar = p.ApiKeyEnvVar,
        ContextLength = p.ContextLength,
        IsFavorite = p.IsFavorite,
    };
}
