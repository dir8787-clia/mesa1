using Microsoft.EntityFrameworkCore;

namespace NetWave.Data;

/// <summary>Репозиторий истории сообщений / состояний окон / звуковой истории (SQLite + EF Core).</summary>
public sealed class HistoryRepository(string dbPath) : IAsyncDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly NetWaveDbContext _db = new(dbPath);

    public async Task InitAsync() => await _db.InitAsync();

    public async Task<long> AddMessageAsync(StoredMessage m)
    {
        await _gate.WaitAsync();
        try
        {
            _db.Messages.Add(m);
            await _db.SaveChangesAsync();
            return m.Id;
        }
        finally { _gate.Release(); }
    }

    public async Task<List<StoredMessage>> GetHistoryAsync(ulong peerUin, int take = 200)
    {
        await _gate.WaitAsync();
        try
        {
            return await _db.Messages
                .Where(m => m.PeerUin == peerUin && !m.Ignored)
                .OrderByDescending(m => m.Timestamp)
                .Take(take)
                .ToListAsync();
        }
        finally { _gate.Release(); }
    }

    public async Task SaveWindowStateAsync(WindowState w)
    {
        await _gate.WaitAsync();
        try
        {
            var existing = await _db.Windows.FindAsync(w.Key);
            if (existing is null) _db.Windows.Add(w);
            else _db.Entry(existing).CurrentValues.SetValues(w);
            await _db.SaveChangesAsync();
        }
        finally { _gate.Release(); }
    }

    public async Task<WindowState?> LoadWindowStateAsync(string key)
    {
        await _gate.WaitAsync();
        try { return await _db.Windows.FindAsync(key); }
        finally { _gate.Release(); }
    }

    public async Task AddSoundHistoryAsync(SoundHistoryEntry e)
    {
        await _gate.WaitAsync();
        try
        {
            _db.SoundHistory.Add(e);
            await _db.SaveChangesAsync();
        }
        finally { _gate.Release(); }
    }

    /// <summary>Воспроизведение в хронологическом порядке (ТЗ 3.8).</summary>
    public async Task<List<SoundHistoryEntry>> GetSoundHistoryAsync(int take = 100)
    {
        await _gate.WaitAsync();
        try
        {
            return await _db.SoundHistory.OrderBy(s => s.Timestamp).Take(take).ToListAsync();
        }
        finally { _gate.Release(); }
    }

    public ValueTask DisposeAsync()
    {
        _db.Dispose();
        _gate.Dispose();
        return ValueTask.CompletedTask;
    }
}
