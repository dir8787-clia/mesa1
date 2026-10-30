using NetWave.Data.Config;
using NetWave.Protocol;
using static NetWave.Protocol.Wire;

namespace NetWave.Core;

/// <summary>Удалённый бан-менеджер на стороне клиента: применяет команды сервера.</summary>
public sealed class BanManager(ClientManager clients)
{
    public void Apply(ulong targetUin, BanKind kind, DateTimeOffset? until)
    {
        var peer = clients.Find(targetUin);
        if (peer is null) return;
        switch (kind)
        {
            case BanKind.Text: peer.BanTextUntil = until; break;
            case BanKind.Sound: peer.BanSoundUntil = until; break;
            case BanKind.Files: peer.BanFilesUntil = until; break;
        }
    }

    public void Lift(ulong targetUin, BanKind kind) => Apply(targetUin, kind, null);
}

/// <summary>IP-фильтр allow/deny (ТЗ 6.3). Пустые списки = «разрешено всё».</summary>
public sealed class IpFilter
{
    private readonly HashSet<string> _allow = [];
    private readonly HashSet<string> _deny = [];

    public IReadOnlyCollection<string> Allow => _allow;
    public IReadOnlyCollection<string> Deny => _deny;

    public bool IsAllowed(string ip)
    {
        if (_deny.Contains(ip)) return false;
        if (_allow.Count > 0 && !_allow.Contains(ip)) return false;
        return true;
    }

    public static IpFilter FromConfig(AppConfig cfg, string allowCsv, string denyCsv)
    {
        var f = new IpFilter();
        foreach (var a in allowCsv.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            f._allow.Add(a);
        foreach (var d in denyCsv.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            f._deny.Add(d);
        return f;
    }
}

/// <summary>Менеджер статусов + авто-away по бездействию.</summary>
public sealed class StatusManager(AppConfig config)
{
    public event Action<UserStatus>? StatusChanged;
    private DateTimeOffset _lastActivity = DateTimeOffset.UtcNow;

    public UserStatus Current => config.LocalStatus;

    public void NotifyActivity() => _lastActivity = DateTimeOffset.UtcNow;

    public void Set(UserStatus status)
    {
        if (config.LocalStatus == status) return;
        config.LocalStatus = status;
        if (!string.IsNullOrEmpty(config.ConfigPath)) config.Save();
        StatusChanged?.Invoke(status);
    }

    /// <summary>Тик таймера: AutoAway — перевод в Away после AutoAwayTimeMin бездействия.</summary>
    public void Tick()
    {
        if (!config.AutoAway || config.LocalStatus != UserStatus.Online) return;
        if (DateTimeOffset.UtcNow - _lastActivity > TimeSpan.FromMinutes(config.AutoAwayTimeMin))
            Set(UserStatus.Away);
    }

    public Packet CreateStatusPacket(ulong uin) => new()
    {
        Type = PacketType.StatusChange,
        SenderUin = uin,
        Seq = Packet.NextSeq(),
        Payload = Wire.Write(w => w.Write((byte)config.LocalStatus)),
    };
}
