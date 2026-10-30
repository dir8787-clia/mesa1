using System.Net;
using NetWave.Data.Config;
using NetWave.Protocol;

namespace NetWave.Core;

/// <summary>Известный клиент (peer) в списке контактов.</summary>
public sealed class PeerInfoModel
{
    public required ulong Uin { get; init; }
    public string Name { get; set; } = "";
    public IPEndPoint Endpoint { get; set; } = new(IPAddress.Loopback, 0);
    public UserStatus Status { get; set; } = UserStatus.Online;
    public bool CanReceiveSound { get; set; } = true;   // иконка наушников
    public bool IsFixed { get; set; }                    // добавлен вручную (IP+порт)
    public bool InGlobalChat { get; set; }               // значок активного глобального чата
    public Guid GroupId { get; set; }
    public DateTimeOffset LastSeen { get; set; } = DateTimeOffset.UtcNow;
    public int MissedPings { get; set; }

    /// <summary>Бан-флаги, полученные от сервера: текст/звук/файлы до указанного момента.</summary>
    public DateTimeOffset? BanTextUntil { get; set; }
    public DateTimeOffset? BanSoundUntil { get; set; }
    public DateTimeOffset? BanFilesUntil { get; set; }

    public bool IsBanned(BanKind kind) => kind switch
    {
        BanKind.Text => BanTextUntil is { } t && t > DateTimeOffset.UtcNow,
        BanKind.Sound => BanSoundUntil is { } s && s > DateTimeOffset.UtcNow,
        BanKind.Files => BanFilesUntil is { } f && f > DateTimeOffset.UtcNow,
        _ => false,
    };
}

public enum BanKind : byte { Text = 1, Sound = 2, Files = 3 }

/// <summary>Группа клиентов (drag & drop в UI).</summary>
public sealed class ContactGroup
{
    public Guid Id { get; init; } = Guid.NewGuid();
    public string Name { get; set; } = "Новая группа";
}

/// <summary>
/// Реестр клиентов: обнаружение, TTL, статусы, группы, игнор.
/// Потребляет события сети (broadcast/ping/pong/status) и хранит актуальное состояние списка.
/// </summary>
public sealed class ClientManager(AppConfig config)
{
    private readonly Dictionary<ulong, PeerInfoModel> _peers = new();
    private readonly Dictionary<Guid, ContactGroup> _groups = new();
    private readonly Lock _sync = new();

    public event Action<PeerInfoModel>? PeerOnline;
    public event Action<PeerInfoModel>? PeerOffline;
    public event Action<PeerInfoModel>? PeerUpdated;

    public IReadOnlyList<ContactGroup> Groups
    {
        get { lock (_sync) return _groups.Values.OrderBy(g => g.Name).ToList(); }
    }

    public IReadOnlyList<PeerInfoModel> Peers
    {
        get { lock (_sync) return _peers.Values.ToList(); }
    }

    public AppConfig Config { get; } = config;

    public PeerInfoModel? Find(ulong uin)
    {
        lock (_sync) return _peers.TryGetValue(uin, out var p) ? p : null;
    }

    public PeerInfoModel? FindByEndpoint(IPEndPoint ep)
    {
        lock (_sync) return _peers.Values.FirstOrDefault(p => p.Endpoint.Equals(ep));
    }

    /// <summary>Обработка входящего Broadcast/Pong — обновление или регистрация клиента.</summary>
    public void UpsertFromProtocol(PeerInfo info, IPEndPoint remote)
    {
        PeerInfoModel? evicted = null;
        bool isNew = false;
        PeerInfoModel peer;
        lock (_sync)
        {
            if (!_peers.TryGetValue(info.Uin, out peer!))
            {
                peer = new PeerInfoModel { Uin = info.Uin };
                _peers[info.Uin] = peer;
                isNew = true;
            }
            peer.Name = info.Name;
            peer.Status = info.Status;
            peer.CanReceiveSound = info.CanReceiveSound;
            peer.Endpoint = remote;
            peer.LastSeen = DateTimeOffset.UtcNow;
            peer.MissedPings = 0;
        }
        if (isNew) PeerOnline?.Invoke(peer); else PeerUpdated?.Invoke(peer);
        GC.KeepAlive(evicted);
    }

    /// <summary>Ручное добавление фиксированного клиента (ip[:port]).</summary>
    public PeerInfoModel AddFixed(string ipPort)
    {
        var parts = ipPort.Split(':', 2);
        var ip = IPAddress.Parse(parts[0]);
        var port = parts.Length > 1 ? int.Parse(parts[1]) : Config.BasePort;
        var ep = new IPEndPoint(ip, port);
        var existing = FindByEndpoint(ep);
        if (existing is not null) return existing;

        // Фиксированный клиент может быть ещё не представлен в broadcast — резервируем временный UIN.
        var peer = new PeerInfoModel
        {
            Uin = ~(ulong)Math.Abs(ep.ToString().GetHashCode()),
            Name = $"[{ip}]",
            Endpoint = ep,
            IsFixed = true,
            Status = UserStatus.Offline,
        };
        lock (_sync) _peers[peer.Uin] = peer;
        return peer;
    }

    public ContactGroup CreateGroup(string name)
    {
        var g = new ContactGroup { Name = name };
        lock (_sync) _groups[g.Id] = g;
        return g;
    }

    public void MoveToGroup(ulong uin, Guid groupId)
    {
        var peer = Find(uin);
        if (peer is not null) { peer.GroupId = groupId; PeerUpdated?.Invoke(peer); }
    }

    public void SetStatus(ulong uin, UserStatus status)
    {
        var peer = Find(uin);
        if (peer is null) return;
        peer.Status = status;
        PeerUpdated?.Invoke(peer);
    }

    public void SetInGlobalChat(ulong uin, bool value)
    {
        var peer = Find(uin);
        if (peer is null) return;
        peer.InGlobalChat = value;
        PeerUpdated?.Invoke(peer);
    }

    /// <summary>Отмечает ping как неудачный; после PingCount промахов — оффлайн.</summary>
    public void RegisterPingFailure(ulong uin)
    {
        var peer = Find(uin);
        if (peer is null) return;
        peer.MissedPings++;
        var limit = Math.Max(1, Config.PingCount);
        if (peer.Status != UserStatus.Offline && peer.MissedPings >= limit)
        {
            peer.Status = UserStatus.Offline;
            PeerOffline?.Invoke(peer);
        }
    }

    /// <summary>TTL-чистка: клиенты без активности дольше TTLsec уходят в оффлайн.</summary>
    public void ExpireStale()
    {
        List<PeerInfoModel> expired = [];
        lock (_sync)
        {
            var ttl = TimeSpan.FromSeconds(Math.Max(30, Config.TTLsec));
            foreach (var p in _peers.Values)
            {
                if (!p.IsFixed && p.Status != UserStatus.Offline &&
                    DateTimeOffset.UtcNow - p.LastSeen > ttl)
                {
                    p.Status = UserStatus.Offline;
                    expired.Add(p);
                }
            }
        }
        foreach (var p in expired) PeerOffline?.Invoke(p);
    }

    /// <summary>Игнорирование по ключевым словам (ТЗ 3.2).</summary>
    public bool ShouldIgnore(string text)
    {
        if (!Config.UseIgnoreStrings || Config.IgnoreStrings.Count == 0) return false;
        foreach (var w in Config.IgnoreStrings)
            if (text.Contains(w, StringComparison.OrdinalIgnoreCase))
                return true;
        return false;
    }

    public bool IsIgnoredUin(ulong uin) =>
        Config.IgnoreUins.Any(s => ulong.TryParse(s, out var v) && v == uin);

    /// <summary>Сортировка списка: по группам либо плоский (SortListMode).</summary>
    public List<PeerInfoModel> GetSortedList()
    {
        var peers = Peers;
        return Config.SortListMode
            ? peers.OrderBy(p => p.Name, StringComparer.CurrentCultureIgnoreCase).ToList()
            : peers.OrderBy(p => p.GroupId == Guid.Empty)
                   .ThenBy(p => Groups.FirstOrDefault(g => g.Id == p.GroupId)?.Name ?? "")
                   .ThenBy(p => p.Name, StringComparer.CurrentCultureIgnoreCase)
                   .ToList();
    }
}
