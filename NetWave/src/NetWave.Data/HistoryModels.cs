using Microsoft.EntityFrameworkCore;

namespace NetWave.Data;

public enum MessageDirection { Incoming = 0, Outgoing = 1, System = 2 }
public enum MessageKind { Private = 0, Chat = 1, Admin = 2, FileEvent = 3, SoundSession = 4 }

/// <summary>Сохранённое сообщение (история диалогов и глобального чата).</summary>
public class StoredMessage
{
    public long Id { get; set; }
    public ulong PeerUin { get; set; }          // собеседник (0 — для системных)
    public string PeerName { get; set; } = "";
    public MessageDirection Direction { get; set; }
    public MessageKind Kind { get; set; }
    public string Text { get; set; } = "";
    public DateTimeOffset Timestamp { get; set; }
    public bool Ignored { get; set; }           // проигнорировано (клиент/ключ. слова) — не показывать
}

/// <summary>Окно чата: позиция/размер для восстановления после перезапуска.</summary>
public class WindowState
{
    public string Key { get; set; } = "";       // "chat:{uin}" или "main" / "globalchat"
    public double X { get; set; }
    public double Y { get; set; }
    public double Width { get; set; }
    public double Height { get; set; }
    public bool Maximized { get; set; }
}

/// <summary>Запись звуковой сессии (звуковая история).</summary>
public class SoundHistoryEntry
{
    public long Id { get; set; }
    public ulong PeerUin { get; set; }
    public string PeerName { get; set; } = "";
    public MessageDirection Direction { get; set; }
    public string FilePath { get; set; } = "";   // WAV (PCM / IMA ADPCM / MS ADPCM)
    public DateTimeOffset Timestamp { get; set; }
    public int DurationSec { get; set; }
}

public sealed class NetWaveDbContext(string dbPath) : DbContext
{
    public DbSet<StoredMessage> Messages => Set<StoredMessage>();
    public DbSet<WindowState> Windows => Set<WindowState>();
    public DbSet<SoundHistoryEntry> SoundHistory => Set<SoundHistoryEntry>();

    protected override void OnConfiguring(DbContextOptionsBuilder options)
        => options.UseSqlite($"Data Source={dbPath}");

    protected override void OnModelCreating(ModelBuilder mb)
    {
        mb.Entity<StoredMessage>().HasIndex(m => new { m.PeerUin, m.Timestamp });
        mb.Entity<WindowState>().HasKey(w => w.Key);
    }

    public async Task InitAsync() => await Database.EnsureCreatedAsync();
}
