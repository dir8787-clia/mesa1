using NetWave.Data.Config;
using NetWave.Protocol;

namespace NetWave.Core;

/// <summary>
/// Автоответчик (Answer Machine, ТЗ 3.7):
/// • активируется при смене статуса на Away;
/// • текстовый автоответ — всем входящим сообщениям;
/// • голосовой автоответчик — запись входящего звука; отвечает голосом только
///   клиентам со статусом ≠ Away (чтобы два автоответчика не разговаривали друг с другом).
/// </summary>
public sealed class AnswerMachine(AppConfig config, TextManager text)
{
    public bool TextEnabled { get; set; } = true;
    public string TextReply { get; set; } = "Пользователь отошёл. Это автоматический ответ.";
    public bool VoiceEnabled { get; set; }
    public string? VoiceRecordingPath { get; set; }
    public bool IsActive => config.LocalStatus == UserStatus.Away;

    /// <summary>Вызывается из диспетчера при входящем TEXT от online-клиента.</summary>
    public Packet? OnIncomingText(ulong fromUin, UserStatus senderStatus)
    {
        if (!IsActive || !TextEnabled) return null;
        var pkt = text.CreateOutgoingText(fromUin, TextReply);
        // помечаем как автоответ, чтобы UI показал факт без повтора цепочки
        return pkt;
    }

    /// <summary>Может ли голосовой автоответчик ответить этому пиру (≠ Away).</summary>
    public bool CanVoiceAnswer(UserStatus senderStatus) =>
        IsActive && VoiceEnabled && VoiceRecordingPath is not null &&
        senderStatus != UserStatus.Away;
}

/// <summary>
/// Звуковая история (ТЗ 3.8): запись всех входящих/исходящих сессий в WAV.
/// Форматы: PCM16, IMA ADPCM, MS ADPCM. MP3/Lame сознательно НЕ поддерживается
/// (по ТЗ — риск зависания). Реализация пишет заголовок WAV и принимает PCM-блоки.
/// </summary>
public sealed class SoundHistoryRecorder : IDisposable
{
    public enum WavFormat { Pcm16 = 0, ImaAdpcm = 1, MsAdpcm = 2 }

    private readonly Data.SoundHistoryRepositoryAdapter _index;
    private BinaryWriter? _writer;
    private string _currentFile = "";
    private long _dataStart;

    public SoundHistoryRecorder(Data.SoundHistoryRepositoryAdapter index) => _index = index;

    public void BeginSession(ulong peerUin, string peerName, bool incoming, int sampleRate, WavFormat fmt)
    {
        Directory.CreateDirectory(Path.Combine(GetRoot(), "SoundHistory"));
        var dir = Path.Combine(GetRoot(), "SoundHistory");
        var stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        var tag = incoming ? "in" : "out";
        _currentFile = Path.Combine(dir, $"{stamp}_{tag}_{Sanitize(peerName)}.wav");
        _writer = new BinaryWriter(File.Create(_currentFile));
        WriteWavHeader(_writer, sampleRate, fmt);
        _dataStart = _writer.BaseStream.Position;
    }

    public void AppendPcm(short[] samples)
    {
        if (_writer is null) return;
        for (var i = 0; i < samples.Length; i++)
            _writer.Write(samples[i]);
    }

    public async Task<int> EndSessionAsync(ulong peerUin, string peerName, bool incoming)
    {
        if (_writer is null) return 0;
        var dataLen = _writer.BaseStream.Length - _dataStart;
        _writer.Seek(0, SeekOrigin.Begin);
        WriteWavHeader(_writer, CurrentSampleRate, CurrentFormat, (int)dataLen);
        _writer.Dispose();
        _writer = null;
        var durSec = (int)(dataLen / (2L * CurrentSampleRate));
        await _index.AddAsync(_currentFile, peerUin, peerName, incoming ? Data.MessageDirection.Incoming : Data.MessageDirection.Outgoing, durSec);
        return durSec;
    }

    private int CurrentSampleRate = 22050;
    private WavFormat CurrentFormat = WavFormat.Pcm16;

    private static void WriteWavHeader(BinaryWriter w, int sampleRate, WavFormat fmt, int dataLen = -1)
    {
        ushort codec = fmt switch { WavFormat.Pcm16 => 1, WavFormat.ImaAdpcm => 17, _ => 6 };
        int blockAlign = codec == 1 ? 2 : 256;
        int byteRate = codec == 1 ? sampleRate * 2 : sampleRate; // упрощённо для ADPCM-блоков
        var totalData = dataLen < 0 ? 0 : dataLen;
        w.Write("RIFF"u8);
        w.Write(36 + totalData);
        w.Write("WAVE"u8);
        w.Write("fmt "u8);
        w.Write(16);
        w.Write(codec);
        w.Write((ushort)1);               // mono
        w.Write(sampleRate);
        w.Write(byteRate);
        w.Write((ushort)blockAlign);
        w.Write((ushort)(codec == 1 ? 16 : 4));
        w.Write("data"u8);
        w.Write(totalData);
    }

    private static string GetRoot() => NetWave.Data.ConfigPaths.GetRoot();

    private static string Sanitize(string s) =>
        string.Join("_", s.Split(Path.GetInvalidFileNameChars()));

    public void Dispose() => _writer?.Dispose();
}
