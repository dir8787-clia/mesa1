using System.Security.Cryptography;

namespace NetWave.Data;

/// <summary>
/// Генератор и хранилище уникального идентификатора клиента (UIN).
/// Формируется один раз при первом запуске: старший бит фиксирован, далее — криптосточный случай.
/// Сохраняется в config.ini ([Local] UIN) и более не меняется.
/// </summary>
public static class UinGenerator
{
    public static ulong Generate()
    {
        Span<byte> b = stackalloc byte[8];
        RandomNumberGenerator.Fill(b);
        var uin = BitConverter.ToUInt64(b);
        uin &= 0x7FFF_FFFF_FFFF_FFFF; // убираем знаковый/старший бит — всегда положительный
        if (uin == 0) uin = 1;
        return uin;
    }

    /// <summary>Возвращает существующий UIN из конфига или генерирует и сохраняет новый.</summary>
    public static ulong EnsureUin(Config.AppConfig cfg)
    {
        if (cfg.Uin != 0) return cfg.Uin;
        cfg.Uin = Generate();
        if (!string.IsNullOrEmpty(cfg.ConfigPath)) cfg.Save();
        return cfg.Uin;
    }
}
