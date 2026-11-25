# SysPulse — Ortak Mimari Sözleşme (Faz 1)

Bu belge **SysPulse** projesinin tek yetkili teknik sözleşmesidir. Amaç, iki geliştiricinin birbirini beklemeden kendi klasörlerinde ve dallarında bağımsız çalışabilmesini ve entegrasyon günü iki servisin sıfır sürtünmeyle birleşmesini sağlamaktır.

---

## 1. Proje Özeti ve Mimari Sınırlar

```
+---------------------------+        HTTP/1.1 POST + JSON        +----------------------------------+
|  Linux Monitoring Agent   | ---------------------------------> |   ASP.NET Core Backend + SignalR |
|  (agent/ — Saf C11/POSIX) |        POST /api/v1/metrics        |   (backend/ — .NET + EF Core)    |
+---------------------------+                                    +----------------------------------+
  - /proc & /sys okur                                              - Payload doğrular & SQLite'a yazar
  - Delta (CPU%, Disk B/s) hesaplar                                - Eşik & cooldown kontrolü yapar
  - Alert/eşik kurallarını BİLMEZ                                  - SignalR ile dashboard'a iter
                                                                   - wwwroot/ içinde tek sayfa UI sunar
```

### Sahiplik ve Dal (Branch) Sınırları

| Alan | Sorumlu | Git Dalı | Açıklama |
| :--- | :--- | :--- | :--- |
| `agent/` | Enes | `dev-agent` | Saf C (C11 / POSIX) metrik toplama servisi |
| `backend/` | Arkadaşın | `dev-backend` | ASP.NET Core API, SQLite, Alert, SignalR ve `wwwroot/` dashboard |
| `docs/CONTRACT.md`, `tools/`, `.gitignore`, `README.md` | Ortak | `dev-main` | Sözleşme anayasası; yalnızca iki tarafın ortak onayıyla değişir |

### Git Çalışma Akışı
1. Ortak sözleşme ve araçlar `dev-main` dalında sabitlenir.
2. Her iki geliştirici kendi dalını `dev-main` ile senkronlar:
   ```bash
   git checkout dev-agent && git merge dev-main
   git checkout dev-backend && git merge dev-main
   ```
3. Geliştirme süresince Enes yalnızca `agent/` altına, arkadaşın yalnızca `backend/` altına yazar (**sıfır merge conflict**).
4. Faz 1 tamamlandığında her iki dal PR ile `dev-main` içine alınır; uçtan uca entegrasyon testinden sonra `dev-main` → `main` birleştirilir.

---

## 2. Faz 1 (Ultra-Hafif MVP) vs Faz 2 ve Kapsam Dışı Kalkanı

### Faz 1 (Şimdi — MVP)
- **Agent (`agent/`):**
  - Toplam CPU kullanım yüzdesi (`usage_percent`), Load Average (`1m`, `5m`, `15m`), mantıksal çekirdek sayısı (`core_count`).
  - RAM (`total`, `used`, `available`, `usage_percent`) ve Swap (`total`, `used`).
  - Toplam Disk I/O hızı (`read_bytes_per_sec`, `write_bytes_per_sec`).
  - Toplam ve çalışan process sayıları (`total_count`, `running_count` — `/proc/loadavg` üzerinden).
  - Çalışma modeli: Foreground (`systemd` `Type=simple` uyumlu), `SIGINT` / `SIGTERM` ile temiz kapanış.
  - Ağ hata davranışı: **Drop & Retry** (backend kapalıysa hatayı `stderr`'e yazar, o örneği atlar ve bir sonraki periyotta tekrar dener).
- **Backend & Dashboard (`backend/`):**
  - SQLite + EF Core ile kalıcı kayıt.
  - `appsettings.json` içinden okunan sabit eşik kuralları + spam önleyici **cooldown** + SignalR bildirimi.
  - `wwwroot/` altından sunulan minimalist tek sayfalık HTML + Vanilla JS + Chart.js dashboard ve düz JS web alert uyarısı.
  - Kimlik doğrulama **yok** (tamamen lokal çalışma).

### Faz 2 (Sözleşme Kırılmadan Eklemeli Yükseltme)
- `/proc/[pid]` taraması ve JSON şemasına opsiyonel `processes.top` (Top-10 process) dizisinin eklenmesi.
- Agent tarafında bağlantı kopuklukları için bellek içi ring buffer (çevrimdışı kuyruk) ve toplu gönderim.
- Opsiyonel `X-Api-Key` başlık doğrulaması, PostgreSQL geçişi, çekirdek bazlı CPU veya ağ arayüzü (Network I/O) metrikleri.

### Faz 1 Kapsam Dışı (Kesin Yasak Listesi)
Aşağıdakiler Faz 1 tamamlanana kadar **eklenmeyecektir**:
- JWT / Login / Kullanıcı yönetimi / TLS (HTTPS).
- gRPC / Protobuf derleme zinciri.
- `/proc/[pid]` süreç taraması ve process listesi.
- Agent içinde ring buffer / disk kuyruğu.
- Docker / PostgreSQL / TimescaleDB zorunluluğu.
- Dinamik alert kuralı CRUD API'si, Discord/Slack/E-posta webhook'ları.
- React / Vue / Angular / Blazor gibi ayrı SPA framework'leri.

---

## 3. HTTP/1.1 İletişim Sözleşmesi (Agent → Backend)

- **Varsayılan Adres:** `http://127.0.0.1:5000`
- **Health Kontrolü:** `GET /api/v1/health` → `200 OK`
  ```json
  {"status":"ok"}
  ```
- **Metrik Gönderimi:** `POST /api/v1/metrics`
- **Gerekli HTTP İstek Başlıkları:**
  - `Host: <host>:<port>`
  - `Content-Type: application/json`
  - `Content-Length: <byte_uzunlugu>`
  - `Connection: close` *(Faz 1'de ham POSIX soketlerinde keep-alive karmaşıklığından kaçınmak için önerilir; backend hem `close` hem `keep-alive` destekler.)*

### Tam Faz 1 JSON Gövdesi

Tüm anahtarlar **kesinlikle `snake_case`** olmalıdır:

```json
{
  "schema_version": 1,
  "host_id": "enes-arch-laptop",
  "timestamp_ms": 1795634891507,
  "interval_sec": 2,
  "cpu": {
    "usage_percent": 24.5,
    "load_1m": 1.12,
    "load_5m": 0.98,
    "load_15m": 0.85,
    "core_count": 8
  },
  "memory": {
    "total_bytes": 16777216000,
    "used_bytes": 7516192768,
    "available_bytes": 9261023232,
    "usage_percent": 44.8,
    "swap_total_bytes": 4294967296,
    "swap_used_bytes": 134217728
  },
  "disk": {
    "read_bytes_per_sec": 1048576,
    "write_bytes_per_sec": 524288
  },
  "processes": {
    "total_count": 284,
    "running_count": 3
  }
}
```

### Alan Tablosu

| Alan | Tip | Birim | Aralık / Kural | Zorunluluk |
| :--- | :--- | :--- | :--- | :--- |
| `schema_version` | `int` | - | Değer `1` olmalı | Zorunlu |
| `host_id` | `string` | - | 1–64 karakter, regex: `^[a-zA-Z0-9._-]+$` | Zorunlu |
| `timestamp_ms` | `int64` | ms | UTC Unix epoch milisaniye, `> 0` | Zorunlu |
| `interval_sec` | `int` | sn | `1..3600` (varsayılan `2`) | Zorunlu |
| `cpu.usage_percent` | `double` | `%` | `0.0..100.0` | Zorunlu |
| `cpu.load_1m` | `double` | - | `>= 0.0` | Zorunlu |
| `cpu.load_5m` | `double` | - | `>= 0.0` | Zorunlu |
| `cpu.load_15m` | `double` | - | `>= 0.0` | Zorunlu |
| `cpu.core_count` | `int` | adet | `>= 1` | Zorunlu |
| `memory.total_bytes` | `int64` | byte | `>= 0` | Zorunlu |
| `memory.used_bytes` | `int64` | byte | `>= 0` (`total_bytes - available_bytes`) | Zorunlu |
| `memory.available_bytes` | `int64` | byte | `>= 0` | Zorunlu |
| `memory.usage_percent` | `double` | `%` | `0.0..100.0` (`total_bytes > 0 ? used_bytes * 100.0 / total_bytes : 0.0`) | Zorunlu |
| `memory.swap_total_bytes` | `int64` | byte | `>= 0` | Zorunlu |
| `memory.swap_used_bytes` | `int64` | byte | `>= 0` (`SwapTotal - SwapFree`) | Zorunlu |
| `disk.read_bytes_per_sec` | `int64` | byte/sn | `>= 0` | Zorunlu |
| `disk.write_bytes_per_sec` | `int64` | byte/sn | `>= 0` | Zorunlu |
| `processes.total_count` | `int` | adet | `>= 0` | Zorunlu |
| `processes.running_count` | `int` | adet | `>= 0` | Zorunlu |
| `processes.top` | `array \| null` | - | Faz 2 için ayrılmıştır; Faz 1'de gönderilmez | Opsiyonel |

> **Geriye Uyumluluk Kuralı:** Backend bilinmeyen ek JSON alanlarını hata vermeden yok saymalıdır; böylece Faz 2 alanları sözleşmeyi kırmadan eklenebilir.

### HTTP Yanıt Kodları

| Durum | Gövde | Açıklama |
| :--- | :--- | :--- |
| `201 Created` | `{"status":"accepted","id":42}` | Metrik doğrulandı ve kaydedildi (C agent her `2xx` kodunu başarılı kabul eder) |
| `400 Bad Request` | `{"error":"<açıklama>"}` | Geçersiz JSON, eksik alan veya aralık/tip ihlali |
| `500 Internal Server Error` | `{"error":"internal_error"}` | Sunucu/veritabanı beklenmeyen hatası |

### Kritik C ↔ .NET Uyumluluk Kuralları
1. **Ondalık Ayırıcı:** JSON içindeki sayılarda ondalık ayırıcı **daima nokta (`.`)** olmalıdır. C agent `LC_NUMERIC` ayarını `tr_TR` gibi virgül kullanan bir locale'e çekmemelidir (`"C"` locale korunmalı).
2. **`NaN` / `Infinity` Yasağı:** C tarafında `0`'a bölme durumları korunmalı, JSON içine asla `nan` veya `inf` yazılmamalıdır.
3. **İlk Örnek (Baseline) Kuralı:** Agent açılışta `/proc/stat` ve `/proc/diskstats` için başlangıç anlık görüntüsü (baseline) alır, 1 `interval_sec` uyur, delta değerlerini hesapladıktan sonra **ilk `POST` isteğini gönderir**. Böylece ilk tikte sahte `0` veya yapay sıçrama oluşmaz.

---

## 4. C Agent Teknik Referansı (Enes'in Tarafı — Faz 1)

### CLI Arayüzü
```text
./syspulse-agent [--host 127.0.0.1] [--port 5000] [--interval 2] [--host-id <ad>]
```
- `--host-id` verilmezse `gethostname()` ile makine adı alınır.
- Çalışma: Ön planda (`foreground`) tek döngü; `sigaction` + `volatile sig_atomic_t` ile `SIGINT` ve `SIGTERM` yakalanarak temiz kapanış yapılır.
- Bağlantı hatası: `connect()` / `send()` başarısız olursa `fprintf(stderr, ...)` ile uyarır, o örneği atlar ve sonraki `interval` tikinde yeniden dener (**drop & retry**).

### Linux `/proc` ve `/sys` Kaynak Eşlemeleri

| Metrik | Kaynak | Hesaplama |
| :--- | :--- | :--- |
| **CPU%** | `/proc/stat` (ilk `cpu ` satırı) | `user nice system idle iowait irq softirq steal` sütunları okunur. `idle_all = idle + iowait`, `non_idle = user + nice + system + irq + softirq + steal`, `total = idle_all + non_idle`. İki örnek arasındaki `delta_total > 0` ise `usage = (delta_total - delta_idle) * 100.0 / delta_total`. |
| **Core Sayısı** | `sysconf(_SC_NPROCESSORS_ONLN)` | Çevrimiçi mantıksal çekirdek sayısı. |
| **Load & Process** | `/proc/loadavg` | İlk 3 alan: `load_1m`, `load_5m`, `load_15m`. 4. alan `running/total` biçimindedir (örn. `3/284`). Tek dosya okumasıyla iki grup biter. |
| **RAM & Swap** | `/proc/meminfo` | `MemTotal`, `MemAvailable`, `SwapTotal`, `SwapFree` satırları (KiB × `1024` = byte). `used_bytes = total_bytes - available_bytes`, `swap_used_bytes = swap_total_bytes - swap_free_bytes`. |
| **Disk I/O** | `/proc/diskstats` + `/sys/block/` | Çift sayımı önlemek için **yalnızca `/sys/block/` altındaki taban blok aygıtları** toplanır; `loop*`, `ram*`, `zram*`, `sr*`, `dm-*`, `md*` aygıtları hariç tutulur. `diskstats` içindeki 6. alan (okunan 512B sektör) ve 10. alan (yazılan 512B sektör) deltaları `512 / elapsed_sec` ile byte/sn'ye çevrilir. |

---

## 5. .NET Backend, Veritabanı, Alert & SignalR Referansı (Arkadaşının Tarafı — Faz 1)

### Hazır C# DTO Kayıtları

`System.Text.Json` ile doğrudan kullanılacak DTO tanımları:

```csharp
using System.Text.Json.Serialization;

public sealed record MetricPayloadDto(
    [property: JsonPropertyName("schema_version")] int SchemaVersion,
    [property: JsonPropertyName("host_id")] string HostId,
    [property: JsonPropertyName("timestamp_ms")] long TimestampMs,
    [property: JsonPropertyName("interval_sec")] int IntervalSec,
    [property: JsonPropertyName("cpu")] CpuMetricsDto Cpu,
    [property: JsonPropertyName("memory")] MemoryMetricsDto Memory,
    [property: JsonPropertyName("disk")] DiskMetricsDto Disk,
    [property: JsonPropertyName("processes")] ProcessMetricsDto Processes
);

public sealed record CpuMetricsDto(
    [property: JsonPropertyName("usage_percent")] double UsagePercent,
    [property: JsonPropertyName("load_1m")] double Load1m,
    [property: JsonPropertyName("load_5m")] double Load5m,
    [property: JsonPropertyName("load_15m")] double Load15m,
    [property: JsonPropertyName("core_count")] int CoreCount
);

public sealed record MemoryMetricsDto(
    [property: JsonPropertyName("total_bytes")] long TotalBytes,
    [property: JsonPropertyName("used_bytes")] long UsedBytes,
    [property: JsonPropertyName("available_bytes")] long AvailableBytes,
    [property: JsonPropertyName("usage_percent")] double UsagePercent,
    [property: JsonPropertyName("swap_total_bytes")] long SwapTotalBytes,
    [property: JsonPropertyName("swap_used_bytes")] long SwapUsedBytes
);

public sealed record DiskMetricsDto(
    [property: JsonPropertyName("read_bytes_per_sec")] long ReadBytesPerSec,
    [property: JsonPropertyName("write_bytes_per_sec")] long WriteBytesPerSec
);

public sealed record ProcessMetricsDto(
    [property: JsonPropertyName("total_count")] int TotalCount,
    [property: JsonPropertyName("running_count")] int RunningCount
);

public sealed record AlertEventDto(
    [property: JsonPropertyName("id")] long Id,
    [property: JsonPropertyName("host_id")] string HostId,
    [property: JsonPropertyName("timestamp_ms")] long TimestampMs,
    [property: JsonPropertyName("metric")] string Metric,
    [property: JsonPropertyName("value")] double Value,
    [property: JsonPropertyName("threshold")] double Threshold,
    [property: JsonPropertyName("message")] string Message
);
```

### Dashboard Okuma Uçları (Frontend Başlangıç Yüklemesi)
- `GET /api/v1/hosts` → Kayıtlı host listesi (`[{"host_id": "...", "last_seen_ms": 1795634891507}]`).
- `GET /api/v1/metrics/recent?hostId=<id>&limit=60` → Seçili host için son `limit` metrik (grafiklerin eskiden yeniye dolması için kronolojik sırada).
- `GET /api/v1/alerts/recent?hostId=<id>&limit=20` → Son `limit` alert kaydı.

### SignalR Hub (`/hubs/metrics`)
- `MetricReceived` → `POST /api/v1/metrics` ile gelen `MetricPayloadDto` JSON nesnesini tüm bağlı istemcilere yayınlar.
- `AlertTriggered` → Eşik aşımında `AlertEventDto` JSON nesnesini yayınlar:
  ```json
  {
    "id": 7,
    "host_id": "enes-arch-laptop",
    "timestamp_ms": 1795634901507,
    "metric": "cpu.usage_percent",
    "value": 92.4,
    "threshold": 85.0,
    "message": "CPU usage 92.4% exceeded threshold 85.0% on enes-arch-laptop"
  }
  ```

### Alert Kuralları (`appsettings.json`)
```json
"AlertRules": {
  "CpuUsagePercent": 85.0,
  "MemoryUsagePercent": 90.0,
  "CooldownSeconds": 30
}
```
- Cooldown kontrolü **`(host_id, metric)`** çifti bazında yapılır; aynı metrik eşiği aşmaya devam etse bile `CooldownSeconds` dolmadan yeni `AlertEvents` satırı ve SignalR `AlertTriggered` olayı üretilmez.
- **Tarayıcı Uyarısı Notu:** Dashboard düz JS `window.alert()` kullandığında modal pencere açık kaldığı sürece SignalR bağlantısının kalp atışı/event loop'u duraksar. Backend tarafındaki `30` saniyelik cooldown bu tıkanmayı azaltır; ek olarak sayfa üstünde bloklamayan bir uyarı bandı (banner) göstermek pratikte daha akıcıdır.

### SQLite + EF Core Şema Özeti
- Veritabanı dosyası: `syspulse.db` (repository'ye commit edilmez, `.gitignore` içindedir).
- İki temel tablo:
  - `MetricSamples` (`Id`, `HostId`, `TimestampMs`, düzleştirilmiş CPU/RAM/Disk/Process sütunları; `(HostId, TimestampMs)` bileşik indeksi).
  - `AlertEvents` (`Id`, `HostId`, `TimestampMs`, `Metric`, `Value`, `Threshold`, `Message`; `(HostId, TimestampMs)` indeksi).

---

## 6. Bağımsız Test & Entegrasyon Kontrol Listesi (Definition of Done)

### Enes (C Agent) Tamamlanma Kriterleri
- [ ] `python3 tools/mock_server.py` ayaktayken C agent `0` şema (`400`) hatası ile sürekli akıyor.
- [ ] `Ctrl+C` (`SIGINT`) veya `SIGTERM` geldiğinde bellek sızıntısı olmadan temiz çıkıyor.
- [ ] `mock_server.py` kapatılıp tekrar açıldığında agent çökmüyor, yeniden bağlanıp göndermeye devam ediyor.
- [ ] AddressSanitizer (`-fsanitize=address,undefined`) veya `valgrind` ile temiz çalışıyor.

### Arkadaşın (.NET Backend & Dashboard) Tamamlanma Kriterleri
- [ ] `python3 tools/mock_agent.py --spike` çalıştırıldığında tüm istekler `201 Created` dönüyor ve `syspulse.db` içine kaydediliyor.
- [ ] `http://127.0.0.1:5000` adresindeki dashboard açılışta `/api/v1/metrics/recent` ile geçmişi çekip ardından SignalR ile canlı grafik akıtıyor.
- [ ] `--spike` anlarında (`CPU > 85%` veya `RAM > 90%`) `AlertEvents` tablosuna kayıt düşüyor, `CooldownSeconds` spam'i engelliyor ve web JS alert tetikleniyor.

### Entegrasyon Günü (Birleşme)
1. Mock araçları kapatılır.
2. `.NET` backend başlatılır (`http://127.0.0.1:5000`).
3. Gerçek `./syspulse-agent` başlatılır.
4. Gerçek Linux makine metriklerinin canlı dashboard'da aktığı ve yapay yük (`stress` vb.) altında alert ürettiği doğrulanır.
