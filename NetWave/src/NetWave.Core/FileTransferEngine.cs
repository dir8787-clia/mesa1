using System.Net;
using NetWave.Data.Config;
using NetWave.Protocol;

namespace NetWave.Core;

/// <summary>Состояние активной передачи файлов.</summary>
public sealed class FileTransfer
{
    public Guid TransferId { get; init; } = Guid.NewGuid();
    public ulong PeerUin { get; set; }
    public IPEndPoint? PeerEndpoint { get; set; }        // для P2P-маршрутизации через сервер
    public string RootName { get; set; } = "";           // имя файла или директории
    public bool IsDirectory { get; set; }
    public List<(string RelPath, long Size)> Entries { get; set; } = [];
    public long TotalBytes { get; set; }
    public long TransferredBytes { get; set; }
    public int ChunkSize { get; set; }
    public bool IsOutgoing { get; set; }
    public TransferState State { get; set; } = TransferState.WaitingConfirm;
    public DateTimeOffset StartedUtc { get; set; } = DateTimeOffset.UtcNow;
    public double SpeedBps { get; internal set; }
    public TimeSpan Eta { get; internal set; }
    public string? Error { get; set; }
}

public enum TransferState { WaitingConfirm, InProgress, Completed, Failed, Refused, Cancelled }

/// <summary>
/// Движок передачи файлов (логический слой): запросы/подтверждения/чанки поверх TCP.
/// Транспортные операции делегируются в <see cref="IFileTransport"/> (реализация — NetWave.Transport).
/// </summary>
public sealed class FileTransferEngine(AppConfig config, ClientManager clients, IFileTransport transport)
{
    private readonly Dictionary<Guid, FileTransfer> _transfers = new();
    private readonly Lock _sync = new();

    public event Action<FileTransfer>? TransferStateChanged;
    public event Action<FileTransfer, string>? IncomingRequestReceived; // требует подтверждения пользователем
    public event Action<string>? ConflictDetected;

    public IReadOnlyList<FileTransfer> Transfers
    {
        get { lock (_sync) return _transfers.Values.ToList(); }
    }

    /// <summary>Начать отправку файла/директории одному или нескольким получателям (мультикаст).</summary>
    public async Task<FileTransfer> SendAsync(string path, ulong targetUin, CancellationToken ct = default)
    {
        var isDir = Directory.Exists(path);
        if (!isDir && !File.Exists(path))
            throw new FileNotFoundException(path);

        var entries = EnumerateEntries(path, isDir);
        var total = entries.Sum(e => e.Size);
        var chunk = Math.Clamp(config.ChunkSizeKB, 16, 8192) * 1024;

        var peer = clients.Find(targetUin) ?? throw new InvalidOperationException($"Unknown peer {targetUin}");
        if (peer.IsBanned(BanKind.Files))
            throw new InvalidOperationException($"Клиент {peer.Name} забанен по файлам сервером");

        var t = new FileTransfer
        {
            PeerUin = targetUin,
            PeerEndpoint = peer.Endpoint,
            RootName = Path.GetFileName(path.TrimEnd(Path.DirectorySeparatorChar)),
            IsDirectory = isDir,
            Entries = entries,
            TotalBytes = total,
            ChunkSize = chunk,
            IsOutgoing = true,
        };

        lock (_sync) _transfers[t.TransferId] = t;

        // 1) Запрос подтверждения (если автоприём у получателя выключен — он ответит из UI)
        var reqPayload = new FileRequestPayload(t.TransferId, t.RootName, total, chunk,
                                                isDir, entries.Count, config.LocalName)
                             .Serialize();
        var pkt = new Packet
        {
            Type = PacketType.FileRequest,
            SenderUin = config.Uin,
            Seq = Packet.NextSeq(),
            Payload = reqPayload,
            Flags = PacketFlags.RequiresAck,
        };
        await transport.SendControlAsync(pkt, t, ct);
        Raise(t);

        // 2) Ждём FILE_ACK с таймаутом (по умолчанию 30 сек)
        var ack = await WaitForAckAsync(t, TimeSpan.FromSeconds(config.FileConfirmTimeoutSec), ct);
        if (ack is null || !ack.Accepted)
        {
            t.State = ack is null ? TransferState.Failed : TransferState.Refused;
            t.Error = ack?.Message ?? "Таймаут ожидания подтверждения";
            Raise(t);
            return t;
        }

        // 3) Потоковая блочная передача по TCP
        t.State = TransferState.InProgress;
        Raise(t);
        try
        {
            await transport.PushDataAsync(t, ct);
            t.State = TransferState.Completed;
        }
        catch (OperationCanceledException)
        {
            t.State = TransferState.Cancelled;
        }
        catch (Exception ex)
        {
            t.State = TransferState.Failed;
            t.Error = ex.Message;
        }
        Raise(t);
        return t;
    }

    /// <summary>Мультикаст-отправка: одному файлу — множеству клиентов одновременно.</summary>
    public async Task<IReadOnlyList<FileTransfer>> SendMulticastAsync(string path, IEnumerable<ulong> targetUins,
                                                                      CancellationToken ct = default)
    {
        var results = new List<FileTransfer>();
        foreach (var uin in targetUins.ToList())
            results.Add(await SendAsync(path, uin, ct));
        return results;
    }

    /// <summary>Получатель: подтверждение или отказ на входящий запрос.</summary>
    public void ConfirmIncoming(Guid transferId, bool accept)
    {
        FileTransfer? t;
        lock (_sync) _transfers.TryGetValue(transferId, out t);
        if (t is null) return;
        t.State = accept ? TransferState.InProgress : TransferState.Refused;
        Raise(t);
    }

    /// <summary>Вызывается транспортом при получении входящего запроса.</summary>
    public void OnIncomingRequest(FileRequestPayload req, IPEndPoint remote, ulong senderUin)
    {
        var t = new FileTransfer
        {
            PeerUin = senderUin,
            PeerEndpoint = remote,
            RootName = req.FileName,
            IsDirectory = req.IsDirectory,
            TotalBytes = req.TotalSize,
            ChunkSize = req.ChunkSize,
            IsOutgoing = false,
            State = TransferState.WaitingConfirm,
        };
        lock (_sync) _transfers[t.TransferId] = t;

        if (config.AutoAccept)
        {
            ConfirmAuto(t);
        }
        else
        {
            IncomingRequestReceived?.Invoke(t, req.SenderName);
        }
    }

    private void ConfirmAuto(FileTransfer t)
    {
        t.State = TransferState.InProgress;
        Raise(t);
        _ = transport.StartReceivingAsync(t, ResolveDestination(t), PrepareOptions(t));
    }

    private string ResolveDestination(FileTransfer t)
    {
        // Папка для полученных файлов — по умолчанию подпапка с именем отправителя
        var senderName = clients.Find(t.PeerUin)?.Name ?? $"uin_{t.PeerUin:X}";
        var safe = string.Join("_", senderName.Split(Path.GetInvalidFileNameChars()));
        return Path.Combine(config.FilesPath, safe);
    }

    private ReceiveOptions PrepareOptions(FileTransfer t) => new()
    {
        Overwrite = config.Overwrite,
        OnConflict = name =>
        {
            ConflictDetected?.Invoke(name);
            return config.Overwrite switch
            {
                OverwriteAction.Overwrite => ConflictResolution.Overwrite,
                OverwriteAction.Skip => ConflictResolution.Skip,
                _ => ConflictResolution.Rename,
            };
        },
    };

    public void UpdateProgress(FileTransfer t, long deltaBytes)
    {
        t.TransferredBytes += deltaBytes;
        var elapsed = DateTimeOffset.UtcNow - t.StartedUtc;
        if (elapsed.TotalSeconds > 0.5)
        {
            t.SpeedBps = t.TransferredBytes / elapsed.TotalSeconds;
            var remaining = t.TotalBytes - t.TransferredBytes;
            t.Eta = t.SpeedBps > 1 ? TimeSpan.FromSeconds(remaining / t.SpeedBps) : TimeSpan.Zero;
        }
        Raise(t);
    }

    public void CompleteIncoming(Guid id)
    {
        if (_transfers.TryGetValue(id, out var t)) { t.State = TransferState.Completed; Raise(t); }
    }

    public void Fail(Guid id, string error)
    {
        if (_transfers.TryGetValue(id, out var t)) { t.State = TransferState.Failed; t.Error = error; Raise(t); }
    }

    private void Raise(FileTransfer t) => TransferStateChanged?.Invoke(t);

    private async Task<FileAckPayload?> WaitForAckAsync(FileTransfer t, TimeSpan timeout, CancellationToken ct)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        while (DateTimeOffset.UtcNow < deadline && !ct.IsCancellationRequested)
        {
            if (t.State == TransferState.InProgress)
                return new FileAckPayload(t.TransferId, true, "");
            if (t.State == TransferState.Refused)
                return new FileAckPayload(t.TransferId, false, t.Error ?? "Отказ");
            await Task.Delay(100, ct);
        }
        return null;
    }

    internal static List<(string RelPath, long Size)> EnumerateEntries(string root, bool isDir)
    {
        if (!isDir)
            return [(Path.GetFileName(root), new FileInfo(root).Length)];

        var list = new List<(string, long)>();
        var baseDir = Path.GetDirectoryName(root)!;
        foreach (var f in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
            list.Add((Path.GetRelativePath(baseDir, f), new FileInfo(f).Length));
        return list;
    }
}

/// <summary>Транспортный контракт движка файлов (реализация — сокетный слой).</summary>
public interface IFileTransport
{
    Task SendControlAsync(Packet controlPacket, FileTransfer transfer, CancellationToken ct);
    Task PushDataAsync(FileTransfer transfer, CancellationToken ct);
    Task StartReceivingAsync(FileTransfer transfer, string destinationDir, ReceiveOptions options);
}

public sealed class ReceiveOptions
{
    public OverwriteAction Overwrite { get; init; }
    public required Func<string, ConflictResolution> OnConflict { get; init; }
}

public enum ConflictResolution { Overwrite, Rename, Skip }
