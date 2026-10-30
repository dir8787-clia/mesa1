using NetWave.Protocol;

namespace NetWave.Data.Config;

/// <summary>
/// Полная конфигурация клиента, разделы и значения по умолчанию — строго по ТЗ (раздел 5).
/// Хранится в INI (default.ini). Потокобезопасное чтение/запись через lock при Save/Load.
/// </summary>
public sealed class AppConfig
{
    public string ConfigPath { get; private set; } = "";

    // [Local]
    public string LocalName { get; set; } = Environment.UserName;
    public UserStatus LocalStatus { get; set; } = UserStatus.Online;

    // [Main]
    public bool NoSound { get; set; }
    public bool ShowIP { get; set; } = true;
    public bool SortListMode { get; set; }          // 0 — по группам, 1 — плоский список
    public bool HideOnStartup { get; set; }
    public bool HideOnEscape { get; set; } = true;
    public bool HideOnClose { get; set; } = true;   // закрывать в трей
    public bool HighPriority { get; set; } = true;  // высокий приоритет процесса для аудио
    public bool HideMe { get; set; }                // невидимость для broadcast
    public bool RemoteUpdate { get; set; } = true;  // разрешить удалённое обновление конфига сервером
    public int StartupDelaySec { get; set; }
    public bool WorkWithOffline { get; set; }
    public bool AutoAway { get; set; }
    public int AutoAwayTimeMin { get; set; } = 10;
    public string Language { get; set; } = "russian";

    // [Text]
    public bool ShowTime { get; set; } = true;
    public bool ChatMode { get; set; }
    public bool ShowNewFirst { get; set; }          // новые сообщения сверху
    public bool RestorePositions { get; set; } = true;
    public bool BringToFront { get; set; } = true;
    public bool CloseAfterSend { get; set; }
    public bool SendOnEnter { get; set; } = true;   // false → Ctrl+Enter
    public bool ChatSendOnEnter { get; set; } = true;
    public bool UseIgnoreStrings { get; set; }
    public bool ShowSmiles { get; set; } = true;
    public bool ShowSmilesAnimation { get; set; } = true;
    public bool SendTypeNotify { get; set; } = true;
    public List<string> IgnoreStrings { get; set; } = new();
    public List<string> IgnoreUins { get; set; } = new();

    // [Net]
    public int BasePort { get; set; } = 8765;       // UDP service/text; +1 звук, +2 файлы
    public int PingOffline { get; set; }            // интервал ping оффлайн (сек), 0 = выкл
    public int PingOnline { get; set; }             // интервал ping онлайн (сек), 0 = выкл
    public bool PingBroadcast { get; set; } = true;
    public int PingCount { get; set; } = 1;
    public int TTLsec { get; set; } = 180;          // время жизни записи о peer без активности
    public bool BroadcastMode { get; set; } = true; // P2P broadcast обнаружение
    public bool UseServer { get; set; }
    public bool ServerMode { get; set; }            // этот инстанс — сервер
    public string ServerHost { get; set; } = "192.168.1.1";
    public int ServerPort { get; set; } = 8772;
    public bool ServerTls { get; set; }
    public bool IgnoreServer { get; set; }          // режим: игнорировать сервер полностью
    public int PingResponseWaitSec { get; set; } = 8;
    public List<string> FixedClients { get; set; } = new(); // "ip[:port]" вручную добавленные

    // [Sound Capture]
    public int CaptureDeviceId { get; set; }
    public int SampleRate { get; set; } = 22050;    // 8000/16000/22050/44100
    public int BufferLenMs { get; set; } = 50;
    public CodecType EncoderType { get; set; } = CodecType.Opus;
    public bool CaptureAgc { get; set; }            // AGC на исходящем — опционально
    public bool NoiseGate { get; set; } = true;
    public int NoisePowerDb { get; set; } = -60;
    public bool VasEnabled { get; set; } = true;    // VAS (не совместим с AGC захвата)
    public double VasPowerOn { get; set; } = 0.03;  // порог начала передачи
    public double VasPowerOff { get; set; } = 0.015;// порог остановки (тишина)
    public int VasReadAheadBlocks { get; set; } = 2;// read-ahead буфер старта речи

    // [Sound Play]
    public int PlayDeviceId { get; set; }
    public int Volume { get; set; } = 40;
    public int MaxBufferLenMs { get; set; } = 3000;
    public int MinBufferLenMs { get; set; } = 25;
    public int Prebuffer { get; set; } = 3;         // блоков перед стартом воспроизведения
    public int AddonBufferMs { get; set; } = 10;
    public bool TscEnabled { get; set; } = true;    // Time Shift Control
    public bool PlayAgc { get; set; } = true;       // AGC входящего — обязательно по умолчанию

    // [Files]
    public int ChunkSizeKB { get; set; } = 512;
    public bool AutoAccept { get; set; }
    public string FilesPath { get; set; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "NetWave Files");
    public OverwriteAction Overwrite { get; set; } = OverwriteAction.Rename;
    public int FileConfirmTimeoutSec { get; set; } = 30;

    // [Alerts]
    public string AlertTextReceived { get; set; } = @"Sounds\msg_received.wav";
    public string AlertTextSent { get; set; } = @"Sounds\msg_sent.wav";
    public string AlertSoundCall { get; set; } = "#4";
    public bool FlashTaskBar { get; set; } = true;
    public bool ShowBalloonNotify { get; set; } = true;

    // [Clipboard]
    public bool ClipboardReceive { get; set; }
    public bool ClipboardAutoOpenImages { get; set; } = true;

    // Прочее
    public string AntiSniffSecret { get; set; } = "netwave-default-secret";
    public bool AntiSniffLegacyXor { get; set; }
    public ulong Uin { get; set; }                  // генерируется один раз при первом запуске

    public int SoundPort => BasePort + 1;           // UDP 8766
    public int FilePort => BasePort + 2;            // TCP 8767

    public static AppConfig Default(string? path = null)
    {
        var cfg = new AppConfig();
        if (path is not null) cfg.Load(path);
        return cfg;
    }

    public void Load(string path)
    {
        ConfigPath = path;
        var ini = IniFile.Load(path);

        LocalName = ini.GetString("Local", "Name", LocalName);
        LocalStatus = (UserStatus)Math.Clamp(ini.GetInt("Local", "Status", (int)LocalStatus), 0, 3);

        NoSound = ini.GetBool("Main", "NoSound", NoSound);
        ShowIP = ini.GetBool("Main", "ShowIP", ShowIP);
        SortListMode = ini.GetBool("Main", "SortListMode", SortListMode);
        HideOnStartup = ini.GetBool("Main", "HideOnStartup", HideOnStartup);
        HideOnEscape = ini.GetBool("Main", "HideOnEscape", HideOnEscape);
        HideOnClose = ini.GetBool("Main", "HideOnClose", HideOnClose);
        HighPriority = ini.GetBool("Main", "HighPriority", HighPriority);
        HideMe = ini.GetBool("Main", "HideMe", HideMe);
        RemoteUpdate = ini.GetBool("Main", "RemoteUpdate", RemoteUpdate);
        StartupDelaySec = ini.GetInt("Main", "StartupDelaySec", StartupDelaySec);
        WorkWithOffline = ini.GetBool("Main", "WorkWithOffline", WorkWithOffline);
        AutoAway = ini.GetBool("Main", "AutoAway", AutoAway);
        AutoAwayTimeMin = ini.GetInt("Main", "AutoAwayTimeMin", AutoAwayTimeMin);
        Language = ini.GetString("Main", "Language", Language);
        Uin = ulong.TryParse(ini.GetString("Local", "UIN", ""), out var u) ? u : 0;

        ShowTime = ini.GetBool("Text", "ShowTime", ShowTime);
        ChatMode = ini.GetBool("Text", "ChatMode", ChatMode);
        ShowNewFirst = ini.GetBool("Text", "ShowNewFirst", ShowNewFirst);
        RestorePositions = ini.GetBool("Text", "RestorePositions", RestorePositions);
        BringToFront = ini.GetBool("Text", "BringToFront", BringToFront);
        CloseAfterSend = ini.GetBool("Text", "CloseAfterSend", CloseAfterSend);
        SendOnEnter = ini.GetBool("Text", "SendOnEnter", SendOnEnter);
        ChatSendOnEnter = ini.GetBool("Text", "ChatSendOnEnter", ChatSendOnEnter);
        UseIgnoreStrings = ini.GetBool("Text", "UseIgnoreStrings", UseIgnoreStrings);
        ShowSmiles = ini.GetBool("Text", "ShowSmiles", ShowSmiles);
        ShowSmilesAnimation = ini.GetBool("Text", "ShowSmilesAnimation", ShowSmilesAnimation);
        SendTypeNotify = ini.GetBool("Text", "SendTypeNotify", SendTypeNotify);
        IgnoreStrings = SplitList(ini.GetString("Text", "IgnoreStrings", ""));
        IgnoreUins = SplitList(ini.GetString("Text", "IgnoreUins", ""));

        BasePort = ini.GetInt("Net", "BasePort", BasePort);
        PingOffline = ini.GetInt("Net", "PingOffline", PingOffline);
        PingOnline = ini.GetInt("Net", "PingOnline", PingOnline);
        PingBroadcast = ini.GetBool("Net", "PingBroadcast", PingBroadcast);
        PingCount = ini.GetInt("Net", "PingCount", PingCount);
        TTLsec = ini.GetInt("Net", "TTLsec", TTLsec);
        BroadcastMode = ini.GetBool("Net", "BroadcastMode", BroadcastMode);
        UseServer = ini.GetBool("Net", "UseServer", UseServer);
        ServerMode = ini.GetBool("Net", "ServerMode", ServerMode);
        ServerHost = ini.GetString("Net", "ServerHost", ServerHost);
        ServerPort = ini.GetInt("Net", "ServerPort", ServerPort);
        ServerTls = ini.GetBool("Net", "ServerTls", ServerTls);
        IgnoreServer = ini.GetBool("Net", "IgnoreServer", IgnoreServer);
        PingResponseWaitSec = ini.GetInt("Net", "PingResponseWaitSec", PingResponseWaitSec);
        FixedClients = SplitList(ini.GetString("Net", "FixedClients", ""));

        CaptureDeviceId = ini.GetInt("Sound Capture", "DeviceID", CaptureDeviceId);
        SampleRate = ini.GetInt("Sound Capture", "SampleRate", SampleRate);
        BufferLenMs = ini.GetInt("Sound Capture", "BufferLen", BufferLenMs);
        EncoderType = (CodecType)Math.Clamp(ini.GetInt("Sound Capture", "EncoderType", (int)EncoderType), 0, 2);
        CaptureAgc = ini.GetBool("Sound Capture", "AGC", CaptureAgc);
        NoiseGate = ini.GetBool("Sound Capture", "NoiseGate", NoiseGate);
        NoisePowerDb = ini.GetInt("Sound Capture", "NoisePower", NoisePowerDb);
        VasEnabled = ini.GetBool("Sound Capture", "VAS", VasEnabled);
        VasPowerOn = ParseDouble(ini.GetString("Sound Capture", "PowerOn"), VasPowerOn);
        VasPowerOff = ParseDouble(ini.GetString("Sound Capture", "PowerOff"), VasPowerOff);
        VasReadAheadBlocks = ini.GetInt("Sound Capture", "ReadAhead", VasReadAheadBlocks);

        PlayDeviceId = ini.GetInt("Sound Play", "DeviceID", PlayDeviceId);
        Volume = ini.GetInt("Sound Play", "Volume", Volume);
        MaxBufferLenMs = ini.GetInt("Sound Play", "MaxBufferLen", MaxBufferLenMs);
        MinBufferLenMs = ini.GetInt("Sound Play", "MinBufferLen", MinBufferLenMs);
        Prebuffer = ini.GetInt("Sound Play", "PrebufferBeforePlay", Prebuffer);
        AddonBufferMs = ini.GetInt("Sound Play", "AddonBuffer", AddonBufferMs);
        TscEnabled = ini.GetBool("Sound Play", "TSC", TscEnabled);
        PlayAgc = ini.GetBool("Sound Play", "AGC", PlayAgc);

        ChunkSizeKB = ini.GetInt("Files", "ChunkSizeKB", ChunkSizeKB);
        AutoAccept = ini.GetBool("Files", "AutoAccept", AutoAccept);
        FilesPath = ini.GetString("Files", "Path", FilesPath);
        Overwrite = (OverwriteAction)Math.Clamp(ini.GetInt("Files", "OverwriteAction", (int)Overwrite), 0, 2);
        FileConfirmTimeoutSec = ini.GetInt("Files", "ConfirmTimeoutSec", FileConfirmTimeoutSec);

        AlertTextReceived = ini.GetString("Alerts", "TextReceived", AlertTextReceived);
        AlertTextSent = ini.GetString("Alerts", "TextSent", AlertTextSent);
        AlertSoundCall = ini.GetString("Alerts", "SoundCall", AlertSoundCall);
        FlashTaskBar = ini.GetBool("Alerts", "FlashTaskBar", FlashTaskBar);
        ShowBalloonNotify = ini.GetBool("Alerts", "ShowBalloonNotify", ShowBalloonNotify);

        ClipboardReceive = ini.GetBool("Clipboard", "Receive", ClipboardReceive);
        ClipboardAutoOpenImages = ini.GetBool("Clipboard", "AutoOpenImages", ClipboardAutoOpenImages);

        AntiSniffSecret = ini.GetString("Security", "AntiSniffSecret", AntiSniffSecret);
        AntiSniffLegacyXor = ini.GetBool("Security", "LegacyXor", AntiSniffLegacyXor);

        // Взаимоисключения по ТЗ: VAS и AGC захвата одновременно включены быть не могут.
        if (VasEnabled && CaptureAgc) CaptureAgc = false;
    }

    public void Save() => Save(ConfigPath);

    public void Save(string path)
    {
        if (string.IsNullOrEmpty(path)) return;
        var ini = new IniFile();
        ini.Set("Local", "Name", LocalName);
        ini.Set("Local", "Status", (int)LocalStatus);
        ini.Set("Local", "UIN", Uin.ToString());
        ini.Set("Main", nameof(NoSound), NoSound);
        ini.Set("Main", "ShowIP", ShowIP);
        ini.Set("Main", "SortListMode", SortListMode);
        ini.Set("Main", "HideOnStartup", HideOnStartup);
        ini.Set("Main", "HideOnEscape", HideOnEscape);
        ini.Set("Main", "HideOnClose", HideOnClose);
        ini.Set("Main", "HighPriority", HighPriority);
        ini.Set("Main", "HideMe", HideMe);
        ini.Set("Main", "RemoteUpdate", RemoteUpdate);
        ini.Set("Main", "StartupDelaySec", StartupDelaySec);
        ini.Set("Main", "WorkWithOffline", WorkWithOffline);
        ini.Set("Main", "AutoAway", AutoAway);
        ini.Set("Main", "AutoAwayTimeMin", AutoAwayTimeMin);
        ini.Set("Main", "Language", Language);
        ini.Set("Text", "ShowTime", ShowTime);
        ini.Set("Text", "ChatMode", ChatMode);
        ini.Set("Text", "ShowNewFirst", ShowNewFirst);
        ini.Set("Text", "RestorePositions", RestorePositions);
        ini.Set("Text", "BringToFront", BringToFront);
        ini.Set("Text", "CloseAfterSend", CloseAfterSend);
        ini.Set("Text", "SendOnEnter", SendOnEnter);
        ini.Set("Text", "ChatSendOnEnter", ChatSendOnEnter);
        ini.Set("Text", "UseIgnoreStrings", UseIgnoreStrings);
        ini.Set("Text", "ShowSmiles", ShowSmiles);
        ini.Set("Text", "ShowSmilesAnimation", ShowSmilesAnimation);
        ini.Set("Text", "SendTypeNotify", SendTypeNotify);
        ini.Set("Text", "IgnoreStrings", string.Join(";", IgnoreStrings));
        ini.Set("Text", "IgnoreUins", string.Join(";", IgnoreUins));
        ini.Set("Net", "BasePort", BasePort);
        ini.Set("Net", "PingOffline", PingOffline);
        ini.Set("Net", "PingOnline", PingOnline);
        ini.Set("Net", "PingBroadcast", PingBroadcast);
        ini.Set("Net", "PingCount", PingCount);
        ini.Set("Net", "TTLsec", TTLsec);
        ini.Set("Net", "BroadcastMode", BroadcastMode);
        ini.Set("Net", "UseServer", UseServer);
        ini.Set("Net", "ServerMode", ServerMode);
        ini.Set("Net", "ServerHost", ServerHost);
        ini.Set("Net", "ServerPort", ServerPort);
        ini.Set("Net", "ServerTls", ServerTls);
        ini.Set("Net", "IgnoreServer", IgnoreServer);
        ini.Set("Net", "PingResponseWaitSec", PingResponseWaitSec);
        ini.Set("Net", "FixedClients", string.Join(";", FixedClients));
        ini.Set("Sound Capture", "DeviceID", CaptureDeviceId);
        ini.Set("Sound Capture", "SampleRate", SampleRate);
        ini.Set("Sound Capture", "BufferLen", BufferLenMs);
        ini.Set("Sound Capture", "EncoderType", (int)EncoderType);
        ini.Set("Sound Capture", "AGC", CaptureAgc);
        ini.Set("Sound Capture", "NoiseGate", NoiseGate);
        ini.Set("Sound Capture", "NoisePower", NoisePowerDb);
        ini.Set("Sound Capture", "VAS", VasEnabled);
        ini.Set("Sound Capture", "PowerOn", VasPowerOn.ToString(System.Globalization.CultureInfo.InvariantCulture));
        ini.Set("Sound Capture", "PowerOff", VasPowerOff.ToString(System.Globalization.CultureInfo.InvariantCulture));
        ini.Set("Sound Capture", "ReadAhead", VasReadAheadBlocks);
        ini.Set("Sound Play", "DeviceID", PlayDeviceId);
        ini.Set("Sound Play", "Volume", Volume);
        ini.Set("Sound Play", "MaxBufferLen", MaxBufferLenMs);
        ini.Set("Sound Play", "MinBufferLen", MinBufferLenMs);
        ini.Set("Sound Play", "PrebufferBeforePlay", Prebuffer);
        ini.Set("Sound Play", "AddonBuffer", AddonBufferMs);
        ini.Set("Sound Play", "TSC", TscEnabled);
        ini.Set("Sound Play", "AGC", PlayAgc);
        ini.Set("Files", "ChunkSizeKB", ChunkSizeKB);
        ini.Set("Files", "AutoAccept", AutoAccept);
        ini.Set("Files", "Path", FilesPath);
        ini.Set("Files", "OverwriteAction", (int)Overwrite);
        ini.Set("Files", "ConfirmTimeoutSec", FileConfirmTimeoutSec);
        ini.Set("Alerts", "TextReceived", AlertTextReceived);
        ini.Set("Alerts", "TextSent", AlertTextSent);
        ini.Set("Alerts", "SoundCall", AlertSoundCall);
        ini.Set("Alerts", "FlashTaskBar", FlashTaskBar);
        ini.Set("Alerts", "ShowBalloonNotify", ShowBalloonNotify);
        ini.Set("Clipboard", "Receive", ClipboardReceive);
        ini.Set("Clipboard", "AutoOpenImages", ClipboardAutoOpenImages);
        ini.Set("Security", "AntiSniffSecret", AntiSniffSecret);
        ini.Set("Security", "LegacyXor", AntiSniffLegacyXor);
        ini.Save(path);
        ConfigPath = path;
    }

    /// <summary>Сериализация всей конфигурации обратно в текст INI (для удалённого чтения сервером).</summary>
    public string ToIniText()
    {
        var tmp = Path.Combine(Path.GetTempPath(), $"netwave_cfg_{Guid.NewGuid():N}.ini");
        Save(tmp);
        var text = File.ReadAllText(tmp);
        File.Delete(tmp);
        return text;
    }

    private static List<string> SplitList(string s) =>
        s.Split([';', ','], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();

    private static double ParseDouble(string s, double def) =>
        double.TryParse(s, System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : def;
}

public enum OverwriteAction
{
    Overwrite = 0,
    Rename = 1,
    Skip = 2,
}
