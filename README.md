# SysPulse

Hafif Linux sistem izleme ajanı (**C11 / POSIX**) ve gerçek zamanlı dashboard backend'i (**ASP.NET Core + EF Core SQLite + SignalR**).

## Mimari & Sahiplik

- **`agent/` (`dev-agent`)**: `/proc` ve `/sys` üzerinden CPU, Load Average, RAM/Swap, Disk I/O ve process sayılarını düşük overhead ile okuyup `POST /api/v1/metrics` ile iletir.
- **`backend/` (`dev-backend`)**: Gelen JSON metriklerini doğrular, SQLite veritabanına yazar, eşik aşımında cooldown'lı alert üretir ve SignalR üzerinden `wwwroot/` dashboard'una aktarır.
- **`docs/CONTRACT.md` (`dev-main`)**: İki taraf arasındaki tek yetkili HTTP/JSON, veritabanı, SignalR ve faz sınırı sözleşmesi.
- **`tools/` (`dev-main`)**: İki geliştiricinin birbirini beklemeden bağımsız çalışabilmesi için sıfır bağımlılıklı Python 3 mock araçları.

## Hızlı Bağımsız Test (`tools/`)

C Agent geliştirirken (Backend olmadan):
```bash
python3 tools/mock_server.py --port 5000
```

.NET Backend geliştirirken (C Agent olmadan, spike alert testi dahil):
```bash
python3 tools/mock_agent.py --url http://127.0.0.1:5000/api/v1/metrics --spike
```

Detaylı alan tanımları, C# DTO'ları ve Linux `/proc` hesaplama kuralları için [docs/CONTRACT.md](docs/CONTRACT.md) belgesine bakın.
