using System.Buffers.Binary;
using System.Text;

namespace NetWave.Protocol;

/// <summary>Payload пакета Broadcast (обнаружение) / Pong / статуса.</summary>
public sealed record PeerInfo(ulong Uin, string Name, UserStatus Status, bool CanReceiveSound,
                             string Ip, int Port, ushort ProtocolVersionVer)
{
    public byte[] Serialize()
    {
        var name = Encoding.UTF8.GetBytes(Name);
        var ip = Encoding.UTF8.GetBytes(Ip);
        var ms = new MemoryStream();
        var w = new BinaryWriter(ms, Encoding.UTF8);
        w.Write(Uin); w.Write((byte)Status); w.Write((byte)(CanReceiveSound ? 1 : 0));
        w.Write(name.Length); w.Write(name);
        w.Write(ip.Length); w.Write(ip); w.Write(Port); w.Write(ProtocolVersionVer);
        w.Flush();
        return ms.ToArray();
    }

    public static PeerInfo Deserialize(ReadOnlySpan<byte> data)
    {
        var r = new BinaryReader(new MemoryStream(data.ToArray()), Encoding.UTF8);
        var uin = r.ReadUInt64();
        var status = (UserStatus)r.ReadByte();
        var snd = r.ReadByte() != 0;
        var name = Encoding.UTF8.GetString(r.ReadBytes(r.ReadInt32()));
        var ip = Encoding.UTF8.GetString(r.ReadBytes(r.ReadInt32()));
        var port = (int)r.ReadUInt16();
        var ver = r.ReadUInt16();
        return new PeerInfo(uin, name, status, snd, ip, port, ver);
    }
}

/// <summary>Payload текстового сообщения / чата.</summary>
public sealed record TextPayload(string Text, long TimestampMs, string? StampId = null)
{
    public byte[] Serialize()
    {
        var t = Encoding.UTF8.GetBytes(Text);
        var s = StampId is null ? Array.Empty<byte>() : Encoding.UTF8.GetBytes(StampId);
        var ms = new MemoryStream();
        var w = new BinaryWriter(ms);
        w.Write(TimestampMs); w.Write(t.Length); w.Write(t); w.Write(s.Length); w.Write(s);
        w.Flush();
        return ms.ToArray();
    }

    public static TextPayload Deserialize(ReadOnlySpan<byte> data)
    {
        var r = new BinaryReader(new MemoryStream(data.ToArray()), Encoding.UTF8);
        var ts = r.ReadInt64();
        var text = Encoding.UTF8.GetString(r.ReadBytes(r.ReadInt32()));
        var sl = r.ReadInt32();
        var stamp = sl > 0 ? Encoding.UTF8.GetString(r.ReadBytes(sl)) : null;
        return new TextPayload(text, ts, stamp);
    }
}

/// <summary>Payload звукового пакета. Заголовок блока + кадры кодека.</summary>
public sealed record SoundPayload(ulong SessionId, uint SampleRate, CodecType Codec,
                                  ushort FrameIndex, bool LastFrame, byte[] Frames, byte[] Parity /* FEC */)
{
    public byte[] Serialize()
    {
        var ms = new MemoryStream();
        var w = new BinaryWriter(ms);
        w.Write(SessionId); w.Write(SampleRate); w.Write((byte)Codec);
        w.Write(FrameIndex); w.Write((byte)(LastFrame ? 1 : 0));
        w.Write(Frames.Length); w.Write(Frames);
        w.Write(Parity.Length); w.Write(Parity);
        w.Flush();
        return ms.ToArray();
    }

    public static SoundPayload Deserialize(ReadOnlySpan<byte> data)
    {
        var r = new BinaryReader(new MemoryStream(data.ToArray()), Encoding.UTF8);
        var sid = r.ReadUInt64();
        var sr = r.ReadUInt32();
        var codec = (CodecType)r.ReadByte();
        var fi = r.ReadUInt16();
        var last = r.ReadByte() != 0;
        var frames = r.ReadBytes(r.ReadInt32());
        var parity = r.ReadBytes(r.ReadInt32());
        return new SoundPayload(sid, sr, codec, fi, last, frames, parity);
    }
}

/// <summary>Запрос на передачу файла/директории.</summary>
public sealed record FileRequestPayload(Guid TransferId, string FileName, long TotalSize,
                                        int ChunkSize, bool IsDirectory, int FileCount, string SenderName)
{
    public byte[] Serialize() => Wire.Write(w =>
    {
        w.Write(TransferId.ToByteArray()); w.WriteStr(FileName); w.Write(TotalSize);
        w.Write(ChunkSize); w.Write((byte)(IsDirectory ? 1 : 0)); w.Write(FileCount);
        w.WriteStr(SenderName);
    });

    public static FileRequestPayload Deserialize(ReadOnlySpan<byte> d) => Wire.Read(d, r =>
        new FileRequestPayload(new Guid(r.ReadBytes(16)), r.ReadStr(), r.ReadInt64(),
            r.ReadInt32(), r.ReadByte() != 0, r.ReadInt32(), r.ReadStr()));
}

/// <summary>Подтверждение/отказ на приём файла.</summary>
public sealed record FileAckPayload(Guid TransferId, bool Accepted, string Message)
{
    public byte[] Serialize() => Wire.Write(w =>
    {
        w.Write(TransferId.ToByteArray()); w.Write((byte)(Accepted ? 1 : 0)); w.WriteStr(Message);
    });

    public static FileAckPayload Deserialize(ReadOnlySpan<byte> d) => Wire.Read(d, r =>
        new FileAckPayload(new Guid(r.ReadBytes(16)), r.ReadByte() != 0, r.ReadStr()));
}

/// <summary>Удалённая команда управления (Wizmo-аналог).</summary>
public sealed record RemoteControlPayload(RemoteControlCommand Command, int Value)
{
    public byte[] Serialize() => Wire.Write(w => { w.Write((byte)Command); w.Write(Value); });
    public static RemoteControlPayload Deserialize(ReadOnlySpan<byte> d) => Wire.Read(d, r =>
        new RemoteControlPayload((RemoteControlCommand)r.ReadByte(), r.ReadInt32()));
}

/// <summary>Команда бана от сервера.</summary>
public sealed record BanPayload(ulong TargetUin, byte Kind /*1=text,2=sound,3=files*/,
                                int DurationSec /*0 = permanent*/, bool Unban, string Reason)
{
    public byte[] Serialize() => Wire.Write(w =>
    {
        w.Write(TargetUin); w.Write(Kind); w.Write(DurationSec);
        w.Write((byte)(Unban ? 1 : 0)); w.WriteStr(Reason);
    });

    public static BanPayload Deserialize(ReadOnlySpan<byte> d) => Wire.Read(d, r =>
        new BanPayload(r.ReadUInt64(), r.ReadByte(), r.ReadInt32(), r.ReadByte() != 0, r.ReadStr()));
}

public static class Wire
{
    public static byte[] Write(Action<BinaryWriter> action)
    {
        var ms = new MemoryStream();
        using (var w = new BinaryWriter(ms, Encoding.UTF8, true)) action(w);
        return ms.ToArray();
    }

    public static T Read<T>(ReadOnlySpan<byte> data, Func<BinaryReader, T> reader)
    {
        using var ms = new MemoryStream(data.ToArray());
        using var r = new BinaryReader(ms, Encoding.UTF8);
        return reader(r);
    }

    public static void WriteStr(this BinaryWriter w, string s)
    {
        var b = Encoding.UTF8.GetBytes(s);
        w.Write(b.Length);
        w.Write(b);
    }

    public static string ReadStr(this BinaryReader r) => Encoding.UTF8.GetString(r.ReadBytes(r.ReadInt32()));
}
