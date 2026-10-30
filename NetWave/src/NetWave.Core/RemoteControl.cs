using System.Net;
using NetWave.Data.Config;
using NetWave.Protocol;

namespace NetWave.Core;

/// <summary>
/// Аналог Wizmo: удалённое управление машиной пира (выключение дисплея, микшер,
/// выход из системы, перезагрузка). Команды шифруются тем же anti-sniff каналом.
/// Исполнение — через <see cref="IRemoteExecutor"/> (Win32 P/Invoke в клиентском приложении).
/// </summary>
public sealed class RemoteControlManager(AppConfig config)
{
    public event Action<RemoteControlPayload, IPEndPoint>? CommandReceived;
    public bool AllowIncoming { get; set; } // «разрешить управлять мной»

    public Packet CreateCommand(RemoteControlCommand cmd, int value = 0) => new()
    {
        Type = PacketType.RemoteControl,
        SenderUin = config.Uin,
        Seq = Packet.NextSeq(),
        Payload = new RemoteControlPayload(cmd, value).Serialize(),
        Flags = PacketFlags.RequiresAck,
    };

    /// <summary>Приёмником вызывается из диспетчера; автоисполнение отключается настройкой.</summary>
    public void HandleIncoming(Packet pkt, IPEndPoint remote, IRemoteExecutor? executor)
    {
        var payload = RemoteControlPayload.Deserialize(pkt.Payload);
        if (!AllowIncoming || executor is null) return;
        CommandReceived?.Invoke(payload, remote);
        executor.Execute(payload);
    }
}

/// <summary>Контрат исполнения системных команд (реализация на Windows — P/Invoke).</summary>
public interface IRemoteExecutor
{
    void Execute(RemoteControlPayload command);
}
