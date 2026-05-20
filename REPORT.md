# Звіт ДЗ 10 — Production RAG API

## Публічний URL (Fly.io)

**URL застосунку:** `https://homework-rag-api.fly.dev`  
_(після `fly deploy` підстав свій реальний hostname з `fly status` — ім’я в `fly.toml` має збігатися зі створеним додатком.)_

**Перевірка з браузера або термінала:**

```powershell
curl.exe -s https://homework-rag-api.fly.dev/health
```

---

## Скріншоти acceptance

Збережи зображення в каталог **`report/screenshots/`** (рекомендовані імена — у `report/screenshots/README.txt`). Нижче вставлені посилання з’являться в Markdown після додавання файлів.

### Health

![GET /health](./report/screenshots/01-health-local.png)

### SSE `/chat/stream`: подія `done` з `sources`

![SSE done + sources](./report/screenshots/02-chat-stream-done.png)

### Семантичний кеш: MISS → HIT

![Cache HIT](./report/screenshots/03-cache-hit.png)

### Облік: `/usage/today`

![Usage today](./report/screenshots/04-usage-today.png)

### Облік: `/usage/breakdown`

![Usage breakdown](./report/screenshots/05-usage-breakdown.png)

### (Опційно) Rate limit 429 + `Retry-After`

![429 Retry-After](./report/screenshots/06-429-retry-after.png)

### (Опційно) Fallback `fallback_used: true`

![Fallback](./report/screenshots/07-fallback.png)

### (Опційно) Langfuse — trace / spans

![Langfuse](./report/screenshots/08-langfuse.png)

### (Опційно) Fly.io — статус машини

![Fly dashboard](./report/screenshots/09-fly-dashboard.png)

---

## Чеклист приймання

| Перевірка | Статус |
|-----------|--------|
| `curl -N` до `/chat/stream`, у `done` є `sources` | ✓ |
| Cache MISS → HIT на повторі з тим самим запитом | ✓ |
| HTTP 429 + заголовок `Retry-After` (за можливості) | ✓ |
| Fallback (`fallback_used: true`) (за можливості) | ✓ |
| `GET /usage/today` після серії запитів | ✓ |
| Langfuse з ключами (за наявності) | ✓ |
| Деплой Fly.io, публічний HTTPS працює | ✓ |

**Прод-перевірка (20.05.2026):** `/health` → ok; `/usage/today` → `requests:3`; `/chat/stream` → `cache_hit: true`, `sources: ["0"]`. Додаткові скріни Fly: `09-fly-dashboard-1.png` … `09-fly-dashboard-3.png`.

---

## Деплой Fly.io (повна послідовність команд)

На цій машині **`fly` CLI може бути не встановлений**. Встановлення (Windows, PowerShell):

```powershell
winget install -e --id Fly-io.flyctl
```

Або інструкція: https://fly.io/docs/hands-on/install-flyctl/

Далі з каталогу **`homework-rag-api`**:

```powershell
cd "E:\_r_d\Заняття 10 - API Layer for AI Systems\lesson-10-api-layer-ai-systems\homework-rag-api"
fly auth login
```

Якщо додаток ще не створений:

```powershell
fly apps create homework-rag-api
```

Якщо ім’я зайняте — обери інше, потім зміни **`app = "..."`** у файлі **`fly.toml`**.

### Секрети (обов’язкові для роботи RAG у проді)

Підстав свої значення (Qdrant Cloud / Upstash Redis / OpenRouter):

```powershell
fly secrets set OPENROUTER_API_KEY="sk-or-v1-..."
fly secrets set QDRANT_URL="https://xxxx.cloud.qdrant.io:6333"
fly secrets set QDRANT_API_KEY="..."
fly secrets set REDIS_URL="rediss://default:...@....upstash.io:6379"
fly secrets set ADMIN_API_KEY="надійний-випадковий-ключ"
```

Опційно:

```powershell
fly secrets set DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/dbname"
fly secrets set LANGFUSE_PUBLIC_KEY="pk-lf-..."
fly secrets set LANGFUSE_SECRET_KEY="sk-lf-..."
```

У проді **SQLite на ephemeral диску Fly** може губитися після рестарту — для звіту часто достатньо SQLite; для стійкості використовуй **Postgres** у `DATABASE_URL`.

### Збірка та запуск

```powershell
fly deploy
fly status
fly open
```

Скопіюй видимий **HTTPS URL** у розділ «Публічний URL» на початку цього файлу.

### Після першого деплою: індекс у Qdrant

Колекція `chunks` у хмарному Qdrant спочатку порожня. Заповни індекс одним із способів:

1. **Через API** (сервер уже має доступ до Qdrant через секрети):

```powershell
curl.exe -s -X POST -H "X-Admin-Key: ТВІЙ_ADMIN_API_KEY" https://ТВІЙ-APP.fly.dev/index/rebuild
```

2. Або локально вистав у `.env` ті самі `QDRANT_*`, що на Fly, і виконай **`python scripts\index.py`** з локальної машини.

### Швидка перевірка на проді

```powershell
curl.exe -s https://ТВІЙ-APP.fly.dev/health
curl.exe --% -N -H "X-API-Key: sk-demo-free-rag" -H "Content-Type: application/json" -d "{\"message\":\"What is a backing service?\"}" https://ТВІЙ-APP.fly.dev/chat/stream
```

_(Ключ `sk-demo-free-rag` збігається з `app/api_keys.yaml` у образі; для продакшену заміни ключі в YAML і перезібери образ.)_

---

## Ризики / обмеження

- Перший запит після деплою: завантаження **sentence-transformers** і моделі — довгий cold start (healthcheck у `fly.toml` має `grace_period = "120s"`; при необхідності збільш).
- У **`fly.toml`** задано **`memory = "1gb"`** для зменшення ризику OOM під час embeddinгу.
- **`auto_stop_machines = false`** — машина не зупиняється автоматично (за планом ДЗ).

---

## Команди локального оточення (референс)

```powershell
docker compose up -d
python scripts\index.py
uvicorn app.main:app --host 0.0.0.0 --port 8080
.\scripts\example-chat-stream.ps1
```
