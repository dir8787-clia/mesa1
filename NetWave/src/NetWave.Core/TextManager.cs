using System.Net;
using NetWave.Data;
using NetWave.Data.Config;
using NetWave.Protocol;
using static NetWave.Protocol.Wire;

namespace NetWave.Core;

/// <summary>Событие тексового обмена для уровня представления.</summary>
public sealed record TextReceivedEvent(ulong FromUin, string FromName, string Text,
                                        DateTimeOffset Timestamp, bool IsChat, bool Ignored);

/// <summary>
/// Менеджер текстового обмена: приватные сообщения, глобальный чат, штампы,
/// игнор по клиентам/ключевым словам, typing-notify, история в SQLite.
/// </summary>
public sealed class TextManager(AppConfig config, ClientManager clients, HistoryRepository history)
{
    public event Action<TextReceivedEvent>? MessageReceived;
    public event Action<ulong>? TypingNotify;           // uin печатает
    public event Action<string>? AdminMessageReceived;  // от сервера

    private readonly List<Stamp> _stamps = new();
    private DateTimeOffset _lastTypingSent = DateTimeOffset.MinValue;
    private readonly HashSet<ulong> _chatMembers = [];

    public IReadOnlyList<Stamp> Stamps => _stamps;
    public bool JoinedGlobalChat { get; private set; }
    public IReadOnlyCollection<ulong> ChatMembers => _chatMembers;

    public void LoadDefaultStamps()
    {
        _stamps.Clear();
        _stamps.AddRange([
            new Stamp("away", "Отошёл от компьютера"),
            new Stamp("busy", "Занят, перезвоню позже"),
            new Stamp("lunch", "На обеде"),
            new Stamp("reboot", "Перезагружаюсь, буду через 5 минут"),
        ]);
    }

    /// <summary>Отправка приватного сообщения. Возвращает готовый пакет для транспорта.</summary>
    public Packet CreateOutgoingText(ulong targetUin, string text, string? stampId = null)
    {
        var payload = new TextPayload(text, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), stampId);
        var pkt = NewPacket(PacketType.Text, payload.Serialize());
        pkt.Flags |= PacketFlags.RequiresAck;
        _ = history.AddMessageAsync(new StoredMessage
        {
            PeerUin = targetUin,
            Direction = MessageDirection.Outgoing,
            Kind = MessageKind.Private,
            Text = text,
            Timestamp = DateTimeOffset.UtcNow,
        });
        return pkt;
    }

    /// <summary>Отправка в глобальный чат (все участники получают через broadcast/сервер).</summary>
    public Packet CreateChatMessage(string text)
    {
        var payload = new TextPayload(text, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
        var pkt = NewPacket(PacketType.Chat, payload.Serialize());
        _ = history.AddMessageAsync(new StoredMessage
        {
            PeerUin = 0,
            PeerName = config.LocalName,
            Direction = MessageDirection.Outgoing,
            Kind = MessageKind.Chat,
            Text = text,
            Timestamp = DateTimeOffset.UtcNow,
        });
        return pkt;
    }

    public Packet JoinChat()
    {
        JoinedGlobalChat = true;
        var pkt = NewPacket(PacketType.Chat, Wire.Write(w => { w.Write((byte)1); w.WriteStr(config.LocalName); }));
        return pkt;
    }

    public Packet LeaveChat()
    {
        JoinedGlobalChat = false;
        return NewPacket(PacketType.Chat, Wire.Write(w => { w.Write((byte)0); w.WriteStr(config.LocalName); }));
    }

    public Packet CreateTypingNotify(ulong targetUin)
    {
        // throttling: не чаще раза в 2 сек
        if (!config.SendTypeNotify || DateTimeOffset.UtcNow - _lastTypingSent < TimeSpan.FromSeconds(2))
            return null!;
        _lastTypingSent = DateTimeOffset.UtcNow;
        var pkt = NewPacket(PacketType.TypingNotify, Array.Empty<byte>());
        return pkt;
    }

    /// <summary>Обработка входящего пакета TEXT/CHAT/TYPING/ADMIN. Вызывается из сетевого диспетчера.</summary>
    public void HandleIncoming(Packet pkt, IPEndPoint remote)
    {
        switch (pkt.Type)
        {
            case PacketType.Text:
            {
                var tp = TextPayload.Deserialize(pkt.Payload);
                var ignored = clients.IsIgnoredUin(pkt.SenderUin) || clients.ShouldIgnore(tp.Text);
                var name = clients.Find(pkt.SenderUin)?.Name ?? $"[{remote.Address}]";
                _ = history.AddMessageAsync(new StoredMessage
                {
                    PeerUin = pkt.SenderUin,
                    PeerName = name,
                    Direction = MessageDirection.Incoming,
                    Kind = MessageKind.Private,
                    Text = tp.Text,
                    Timestamp = DateTimeOffset.FromUnixTimeMilliseconds(tp.TimestampMs),
                    Ignored = ignored,
                });
                MessageReceived?.Invoke(new TextReceivedEvent(pkt.SenderUin, name, tp.Text,
                    DateTimeOffset.FromUnixTimeMilliseconds(tp.TimestampMs), false, ignored));
                break;
            }
            case PacketType.Chat:
            {
                // join/leave маркеры или сообщение
                if (pkt.Payload.Length > 0 && (pkt.Payload[0] == 1 || pkt.Payload[0] == 0))
                {
                    var join = pkt.Payload[0] == 1;
                    using var r = new BinaryReader(new MemoryStream(pkt.Payload));
                    r.ReadByte();
                    var cname = r.ReadStr();
                    var cuin = pkt.SenderUin;
                    if (join) _chatMembers.Add(cuin); else _chatMembers.Remove(cuin);
                    clients.SetInGlobalChat(cuin, join);
                    return;
                }
                var cp = TextPayload.Deserialize(pkt.Payload);
                var ignored = clients.IsIgnoredUin(pkt.SenderUin) || clients.ShouldIgnore(cp.Text);
                var nm = clients.Find(pkt.SenderUin)?.Name ?? $"[{remote.Address}]";
                _ = history.AddMessageAsync(new StoredMessage
                {
                    PeerUin = 0,
                    PeerName = nm,
                    Direction = MessageDirection.Incoming,
                    Kind = MessageKind.Chat,
                    Text = cp.Text,
                    Timestamp = DateTimeOffset.FromUnixTimeMilliseconds(cp.TimestampMs),
                    Ignored = ignored,
                });
                MessageReceived?.Invoke(new TextReceivedEvent(pkt.SenderUin, nm, cp.Text,
                    DateTimeOffset.FromUnixTimeMilliseconds(cp.TimestampMs), true, ignored));
                break;
            }
            case PacketType.TypingNotify:
                TypingNotify?.Invoke(pkt.SenderUin);
                break;
            case PacketType.AdminMsg:
            {
                var msg = System.Text.Encoding.UTF8.GetString(pkt.Payload);
                AdminMessageReceived?.Invoke(msg);
                _ = history.AddMessageAsync(new StoredMessage
                {
                    PeerUin = 0,
                    PeerName = "SERVER",
                    Direction = MessageDirection.System,
                    Kind = MessageKind.Admin,
                    Text = msg,
                    Timestamp = DateTimeOffset.UtcNow,
                });
                break;
            }
        }
    }

    private Packet NewPacket(PacketType type, byte[] payload) => new()
    {
        Type = type,
        SenderUin = config.Uin,
        Seq = Packet.NextSeq(),
        Payload = payload,
    };
}

public sealed record Stamp(string Id, string Text);
