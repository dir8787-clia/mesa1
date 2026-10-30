namespace NetWave.Protocol;

/// <summary>Типы сетевых пакетов NetWave (см. ТЗ, раздел 4).</summary>
public enum PacketType : byte
{
    Unknown = 0,
    Ping = 1,             // проверка статуса (онлайн/оффлайн)
    Pong = 2,             // ответ на ping
    Broadcast = 3,        // обнаружение клиентов в LAN
    Text = 4,             // текстовое сообщение
    Sound = 5,            // звуковой пакет (UDP 8766)
    FileRequest = 6,      // запрос на передачу файла (подтверждение получателем)
    FileData = 7,         // блок данных файла (TCP 8767)
    FileAck = 8,          // подтверждение получения блока / согласия на приём
    StatusChange = 9,     // смена статуса клиента
    Chat = 10,            // глобальный чат
    TypingNotify = 11,    // уведомление о наборе текста
    AdminMsg = 12,        // административное сообщение от сервера
    ConfigUpdate = 13,    // удалённая запись config.ini
    ConfigRead = 14,      // удалённое чтение config.ini
    ConfigResponse = 15,  // содержимое config.ini в ответ
    SoundStart = 16,      // начало голосовой сессии (запрос)
    SoundEnd = 17,        // завершение голосовой сессии
    FileResult = 18,      // итог передачи файла (ok/error/refused)
    RemoteControl = 19,   // команды удалённого управления (Wizmo-аналог)
    Ban = 20,             // бан-команда сервера (текст/звук/файлы)
    P2PRoute = 21,        // маршрутный указатель сервера: «говори напрямую с этим endpoint»
    PeerList = 22,        // рассылка списка известных пиров (для клиентов за NAT-подобными сегментами)
    Ack = 23,             // общий ACK (по Seq)
}

/// <summary>Флаги заголовка пакета.</summary>
[Flags]
public enum PacketFlags : ushort
{
    None = 0,
    Encrypted = 1,       // payload прошёл anti-sniff кодирование
    Compressed = 2,      // payload сжат (lz4-style — здесь Deflate)
    FromServer = 4,      // пакет сгенерирован сервером
    ToServer = 8,        // пакет адресован серверу на обработку/маршрутизацию
    RequiresAck = 16,
    IsAck = 32,
}

/// <summary>Статусы клиента.</summary>
public enum UserStatus : byte
{
    Offline = 0,
    Online = 1,
    Away = 2,
    DoNotDisturb = 3,
}

/// <summary>Режимы codec'ов звука.</summary>
public enum CodecType : byte
{
    Opus = 0,     // рекомендуемый, 6–510 кбит/с
    Speex = 1,    // legacy, 16–24 кбит/с
    Adpcm = 2,    // быстрый, для локальных сетей
}

/// <summary>Коды удалённого управления (Wizmo-аналог).</summary>
public enum RemoteControlCommand : byte
{
    DisplayOff = 1,
    VolumeSet = 2,
    MuteOn = 3,
    MuteOff = 4,
    LogOut = 5,
    Reboot = 6,
}
