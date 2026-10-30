namespace NetWave.Data;

/// <summary>Тонкий адаптер для индекса звуковой истории (отделяет Core от EF-репозитория).</summary>
public sealed class SoundHistoryRepositoryAdapter(HistoryRepository repo)
{
    public Task AddAsync(string filePath, ulong peerUin, string peerName,
                        MessageDirection direction, int durationSec) =>
        repo.AddSoundHistoryAsync(new SoundHistoryEntry
        {
            FilePath = filePath,
            PeerUin = peerUin,
            PeerName = peerName,
            Direction = direction,
            Timestamp = DateTimeOffset.UtcNow,
            DurationSec = durationSec,
        });
}

/// <summary>Стандартные пути приложения (кроссплатформенные, Windows-ориентированные по умолчанию).</summary>
public static class ConfigPaths
{
    private static string? _override;

    /// <summary>Переопределение корня данных (для тестов и portable-режима).</summary>
    public static void OverrideRoot(string root) => _override = root;

    public static string GetRoot()
    {
        if (_override is not null) return _override;
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        if (string.IsNullOrEmpty(appData))
            appData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".config");
        return Path.Combine(appData, "NetWave");
    }

    public static string GetConfigPath() => Path.Combine(GetRoot(), "default.ini");
    public static string GetDbPath() => Path.Combine(GetRoot(), "history.db");
    public static string ThemesDir => Path.Combine(GetRoot(), "Themes");
    public static string ColorsDir => Path.Combine(GetRoot(), "Colors");
    public static string SmilesDir => Path.Combine(GetRoot(), "Smiles");
    public static string AvatarsDir => Path.Combine(GetRoot(), "Avatars");
    public static string LanguagesDir => Path.Combine(GetRoot(), "Languages");
    public static string SoundsDir => Path.Combine(GetRoot(), "Sounds");

    public static void EnsureDirs()
    {
        foreach (var d in new[] { GetRoot(), ThemesDir, ColorsDir, SmilesDir, AvatarsDir, LanguagesDir, SoundsDir })
            Directory.CreateDirectory(d);
    }
}
