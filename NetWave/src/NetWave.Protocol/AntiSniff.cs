using System.Security.Cryptography;
using System.Text;

namespace NetWave.Protocol;

/// <summary>
/// Anti-Sniff: кодирование payload перед отправкой для защиты от снифферов.
/// Режим AES (AES-128-CBC, случайный IV в префиксе) — основной;
/// режим Xor (XOR + Base64) — legacy для обратной совместимости со старыми клиентами.
/// Маркер схемы ("A"/"X") в начале позволяет принимать оба варианта всегда.
/// </summary>
public sealed class AntiSniff
{
    private const byte SchemeAes = (byte)'A';
    private const byte SchemeXor = (byte)'X';
    private readonly byte[] _key; // 16 bytes, из секрета через SHA-1
    public bool PreferXor { get; init; }

    public AntiSniff(string secret)
    {
        _key = SHA1.HashData(Encoding.UTF8.GetBytes(secret))[..16];
    }

    public byte[] Encode(ReadOnlySpan<byte> payload)
        => PreferXor ? EncodeXor(payload) : EncodeAes(payload);

    public bool TryDecode(ReadOnlySpan<byte> data, out byte[] payload)
    {
        payload = Array.Empty<byte>();
        if (data.Length < 1) return false;
        return data[0] switch
        {
            SchemeAes => TryDecodeAes(data[1..], out payload),
            SchemeXor => TryDecodeXor(data[1..], out payload),
            _ => false,
        };
    }

    // ── AES-128-CBC ────────────────────────────────────────────────
    private byte[] EncodeAes(ReadOnlySpan<byte> payload)
    {
        using var aes = Aes.Create();
        aes.Key = _key;
        aes.GenerateIV();
        using var enc = aes.CreateEncryptor();
        var plain = payload.ToArray();
        var cipher = enc.TransformFinalBlock(plain, 0, plain.Length);
        var res = new byte[1 + aes.IV.Length + cipher.Length];
        res[0] = SchemeAes;
        aes.IV.CopyTo(res, 1);
        cipher.CopyTo(res, 1 + aes.IV.Length);
        return res;
    }

    private bool TryDecodeAes(ReadOnlySpan<byte> data, out byte[] payload)
    {
        payload = Array.Empty<byte>();
        const int ivLen = 16;
        if (data.Length < ivLen + 16) return false; // минимум IV + один блок
        try
        {
            using var aes = Aes.Create();
            aes.Key = _key;
            aes.Mode = CipherMode.CBC;
            aes.Padding = PaddingMode.PKCS7;
            aes.IV = data[..ivLen].ToArray();
            using var dec = aes.CreateDecryptor();
            var body = data[ivLen..].ToArray();
            payload = dec.TransformFinalBlock(body, 0, body.Length);
            return true;
        }
        catch
        {
            return false; // неверный ключ/повреждённые данные → пакет отбрасывается
        }
    }

    // ── XOR + Base64 (legacy) ──────────────────────────────────────
    private byte[] EncodeXor(ReadOnlySpan<byte> payload)
    {
        var xored = new byte[payload.Length];
        for (var i = 0; i < payload.Length; i++)
            xored[i] = (byte)(payload[i] ^ _key[i % _key.Length]);
        var b64 = Convert.ToBase64String(xored);
        var res = new byte[1 + b64.Length];
        res[0] = SchemeXor;
        Encoding.ASCII.GetBytes(b64).CopyTo(res.AsSpan(1));
        return res;
    }

    private bool TryDecodeXor(ReadOnlySpan<byte> data, out byte[] payload)
    {
        payload = Array.Empty<byte>();
        try
        {
            var xored = Convert.FromBase64String(Encoding.ASCII.GetString(data));
            payload = new byte[xored.Length];
            for (var i = 0; i < xored.Length; i++)
                payload[i] = (byte)(xored[i] ^ _key[i % _key.Length]);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
