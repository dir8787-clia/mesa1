# NetWave — современный сетевой мессенджер реального времени

C# 12 / .NET 8. Голосовая связь (Opus/Speex/ADPCM), текст, файлы, глобальный чат,
P2P-обнаружение в LAN и серверный режим для распределённых сетей.

## Структура решения

```
NetWave.sln
├── src/
│   ├── NetWave.Protocol        — сетевой протокол: пакеты, кодек, CRC32, anti-sniff (AES/XOR)
│   ├── NetWave.Core            — прикладной слой: клиент-менеджер, группы, статусы, UIN,
│   │                             передача файлов, автоответчик, звуковая история, баны, конфиг
│   ├── NetWave.Transport       — инфраструктура: UDP 8765/8766, TCP 8767, broadcast/multicast,
│   │                             net scanner, коннектор к серверу, реконнект
│   ├── NetWave.Audio           — аудио-движок: IAudioEngine (NAudio на Windows), VAS, AGC, TSC,
│   │                             кодеки, VU-метры, запись сессий
│   ├── NetWave.Data            — SQLite + EF Core: история сообщений, события; INI/JSON конфиг
│   ├── NetWave.Server          — выделенный сервер: регистрация клиентов, маршрутизация,
│   │                             мульти-серверные топологии, админ-рассылки, удалённый config.ini
│   ├── NetWave.Client          — WPF (MVVM, CommunityToolkit.Mvvm): главное окно, чаты, настройки,
│   │                             трей, хоткеи, уведомления, темы/смайлы/аватары
│   └── NetWave.Cli             — headless-клиент для интеграционных тестов и Linux
└── tests/NetWave.Tests         — xUnit + FluentAssertions (unit + интеграция UDP/TCP/сервер)
```

Соответствие слоям из ТЗ:

| Слой ТЗ                | Проект            |
|------------------------|-------------------|
| Presentation (WPF/MVVM)| NetWave.Client    |
| Application (Core)     | NetWave.Core, NetWave.Protocol, NetWave.Audio |
| Data                   | NetWave.Data      |
| Infrastructure         | NetWave.Transport |

## Протокол

Порты по умолчанию: **UDP 8765** (сервис + текст), **UDP 8766** (звук), **TCP 8767** (файлы).
Формат пакета (little-endian): `Magic "NW" | Version | Type | Flags | Seq(u64) | SenderUIN(u64) |
PayloadLen(u16) | Payload(anti-sniff) | CRC32`. Обратная совместимость: версия пакета проверяется
на приёмнике, v1 декодируется всегда.

Типы: PING/PONG, BROADCAST, TEXT, SOUND (+SOUND_START/END), FILE_REQUEST/DATA/ACK/RESULT,
ADMIN_MSG, CONFIG_UPDATE/READ/RESPONSE, STATUS_CHANGE, CHAT, TYPING, REMOTE_CONTROL, BAN, P2P_ROUTE.

## Сборка и запуск

```bash
dotnet build                              # сборка всего решения (кроссплатформенно)
dotnet test                               # unit + интеграционные тесты
dotnet run --project src/NetWave.Server   # сервер (распределённые сети)
dotnet run --project src/NetWave.Cli      # headless-клиент
# WPF-клиент собирается и запускается только на Windows:
dotnet run --project src/NetWave.Client   # (Windows)
```

На не-Windows платформах WPF-проект исключается из сборки автоматически
(`EnableWindowsTargeting`), а аудио-движок подменяется no-op реализацией,
поэтому ядро, транспорт и сервер полностью работоспособны и тестируемы на любом ОС.

## Конфигурация

INI (`default.ini` в `%APPDATA%/NetWave` или `~/.config/NetWave`) — см. разделы `[Local]`,
`[Main]`, `[Text]`, `[Net]`, `[Sound Capture]`, `[Sound Play]`, `[Files]`, `[Alerts]`,
`[Clipboard]` в `src/NetWave.Data/Config/AppConfig.cs`. Значения по умолчанию соответствуют ТЗ.

## Безопасность

* Anti-Sniff: AES-128-CBC (IV в префиксе) либо XOR+Base64 (legacy-режим совместимости).
* IP-фильтрация allow/deny (`IpFilter`).
* Валидация всех входящих пакетов: magic, версия, длина, CRC32 — до диспетчеризации.
* TLS для TCP-канала серверного режима (опционально, `ServerTls`).
