using System.Buffers.Binary;
using System.IO.Compression;

namespace NetWave.Protocol;

/// <summary>
/// Бинарный пакет NetWave (little-endian):
/// Magic "NW" | Version(u8) | Type(u8) | Flags(u16) | Seq(u64) | SenderUIN(u64) |
/// PayloadLen(u32) | Payload | Crc32(u32).
/// Валидация выполняется до диспетчеризации — защита от повреждённых/вредоносных datagram.
/// </summary>
public sealed class Packet
{
    public const byte ProtocolVersion = 2;      // текущая версия
    public const byte MinSupportedVersion = 1;  // обратная совместимость: v1 читаем всегда
    public const ushort Magic = 0x574E;         // "NW" little-endian
    public const int HeaderSize = 2 + 1 + 1 + 2 + 8 + 8 + 4; // = 26
    public const int MaxPayloadSize = 1 << 20;  // 1 MiB — жёсткий лимит (anti buffer-overflow)

    public byte Version { get; set; } = ProtocolVersion;
    public PacketType Type { get; set; }
    public PacketFlags Flags { get; set; }
    public ulong Seq { get; set; }
    public ulong SenderUin { get; set; }
    public byte[] Payload { get; set; } = Array.Empty<byte>();

    /// <summary>Кодировать payload anti-sniff'ом при сериализации.</summary>
    public bool ProtectPayload { get; set; } = true;

    public static ulong NextSeq() => (ulong)Environment.TickCount64 << 20
                                     ^ (ulong)Random.Shared.Next(0, 1 << 20);

    public byte[] Encode(AntiSniff? sniffer = null)
    {
        var payload = Payload;

        if ((Flags & PacketFlags.Compressed) != 0)
            payload = Deflate(payload);

        if (ProtectPayload && sniffer is not null)
        {
            payload = sniffer.Encode(payload);
            Flags |= PacketFlags.Encrypted;
        }
        else
        {
            Flags &= ~PacketFlags.Encrypted;
        }

        var buf = new byte[HeaderSize + payload.Length + 4];
        var span = buf.AsSpan();
        BinaryPrimitives.WriteUInt16LittleEndian(span, Magic); span = span[2..];
        span[0] = Version; span = span[1..];
        span[0] = (byte)Type; span = span[1..];
        BinaryPrimitives.WriteUInt16LittleEndian(span, (ushort)Flags); span = span[2..];
        BinaryPrimitives.WriteUInt64LittleEndian(span, Seq); span = span[8..];
        BinaryPrimitives.WriteUInt64LittleEndian(span, SenderUin); span = span[8..];
        BinaryPrimitives.WriteUInt32LittleEndian(span, (uint)payload.Length); span = span[4..];
        payload.CopyTo(span); span = span[payload.Length..];
        BinaryPrimitives.WriteUInt32LittleEndian(span, Crc32.Compute(buf[..^4]));
        return buf;
    }

    /// <summary>Полная валидация и декодирование. Возвращает false для мусорных пакетов.</summary>
    public static bool TryDecode(ReadOnlySpan<byte> data, AntiSniff? sniffer, out Packet? packet)
    {
        packet = null;
        if (data.Length < HeaderSize + 4) return false;

        var head = data;
        if (BinaryPrimitives.ReadUInt16LittleEndian(head) != Magic) return false; head = head[2..];
        var version = head[0]; head = head[1..];
        if (version < MinSupportedVersion || version > ProtocolVersion) return false;
        var type = head[0]; head = head[1..];
        var flags = (PacketFlags)BinaryPrimitives.ReadUInt16LittleEndian(head); head = head[2..];
        var seq = BinaryPrimitives.ReadUInt64LittleEndian(head); head = head[8..];
        var uin = BinaryPrimitives.ReadUInt64LittleEndian(head); head = head[8..];
        var len = BinaryPrimitives.ReadUInt32LittleEndian(head); head = head[4..];

        if (len > MaxPayloadSize || data.Length != HeaderSize + (int)len + 4) return false;

        // CRC по всему буферу кроме последних 4 байт
        var expectedCrc = BinaryPrimitives.ReadUInt32LittleEndian(data[^4..]);
        if (Crc32.Compute(data[..^4]) != expectedCrc) return false;

        var payload = data.Slice(HeaderSize, (int)len).ToArray();

        if (flags.HasFlag(PacketFlags.Encrypted) && sniffer is not null)
        {
            if (!sniffer.TryDecode(payload, out var decoded)) return false; // bad key/format
            payload = decoded;
        }

        if (flags.HasFlag(PacketFlags.Compressed))
        {
            try { payload = Inflate(payload); }
            catch { return false; }
        }

        packet = new Packet
        {
            Version = version,
            Type = (PacketType)type,
            Flags = flags,
            Seq = seq,
            SenderUin = uin,
            Payload = payload,
        };
        return true;
    }

    private static byte[] Deflate(byte[] input)
    {
        using var ms = new MemoryStream();
        using (var d = new DeflateStream(ms, CompressionLevel.Fastest, true))
            d.Write(input);
        var res = ms.ToArray();
        return res.Length < input.Length ? res : input; // сжатие невыгодно — оставляем как есть
    }

    private static byte[] Inflate(byte[] input)
    {
        using var ms = new MemoryStream(input);
        using var d = new DeflateStream(ms, CompressionMode.Decompress);
        using var outMs = new MemoryStream();
        d.CopyTo(outMs);
        return outMs.ToArray();
    }
}

/// <summary>CRC32 (полином 0xEDB88320) — табличный, без аллокаций.</summary>
public static class Crc32
{
    private static readonly uint[] Table = BuildTable();

    private static uint[] BuildTable()
    {
        var t = new uint[256];
        for (uint i = 0; i < 256; i++)
        {
            var c = i;
            for (var k = 0; k < 8; k++)
                c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            t[i] = c;
        }
        return t;
    }

    public static uint Compute(ReadOnlySpan<byte> data)
    {
        uint crc = 0xFFFFFFFFu;
        foreach (var b in data)
            crc = Table[(crc ^ b) & 0xFF] ^ (crc >> 8);
        return crc ^ 0xFFFFFFFFu;
    }
}
