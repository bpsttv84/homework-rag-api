# Homework 10 — Production RAG API

Окремий сервіс: **FastAPI** + **SSE** (`POST /chat/stream`), **Qdrant** (колекції `chunks` + semantic `cache`), **Redis** token bucket (без Lua), **OpenRouter** з fallback і circuit breaker, облік витрат (SQLite за замовчуванням), опційно **Langfuse**, деплой на **Fly.io**.

## Вимоги

- Python **3.11+**
- Docker (для Qdrant + Redis локально)

## Швидкий старт (локально)

```powershell
cd homework-rag-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Заповніть OPENROUTER_API_KEY у .env
docker compose up -d
python scripts\index.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Перевірка здоров’я:

```powershell
curl http://127.0.0.1:8080/health
```

Стрім чату (SSE). У **PowerShell** простіше не боротись з лапками вручну.

**Найнадійніше** — готовий скрипт (JSON пишеться у `%TEMP%`, шлях до файлу для `-d @...` завжди валідний):

```powershell
cd homework-rag-api
.\scripts\example-chat-stream.ps1
```

Чат **без скрипта**, але стійко до PowerShell: тіло через **stdin** (`-d "@-"`), щоб оболонка не ламала лапки в `--data-raw $j`:

```powershell
'{"message":"What is a backing service in the twelve-factor app?"}' | curl.exe -N `
  -H "X-API-Key: sk-demo-free-rag" `
  -H "Content-Type: application/json" `
  -d "@-" `
  http://127.0.0.1:8080/chat/stream
```

Або режим **«не парси далі»** для `curl.exe` (лише якщо рядок одним фрагментом передається в curl):

```powershell
curl.exe --% -N -H "X-API-Key: sk-demo-free-rag" -H "Content-Type: application/json" -d "{\"message\":\"What is a backing service in the twelve-factor app?\"}" http://127.0.0.1:8080/chat/stream
```

Якщо використовуєш `-d "@body.json"`, файл має бути в **поточній теці** оболонки (не з `C:\Windows\System32`) або вкажи повний шлях, наприклад `-d "@E:\path\to\homework-rag-api\body.json"`.

У відповіді очікуйте рядки `data: {...}`; фінальний рядок містить `"type":"done"`, поля `cache_hit`, `sources`, `model`, `fallback_used`, `output_filtered`.

## API-ключі (демо)

Файл `app/api_keys.yaml` — три тіри з різними `tokens_per_minute` і ланцюжками моделей OpenRouter:

| Ключ | Тір |
|------|-----|
| `sk-demo-free-rag` | demo-free |
| `sk-demo-pro-rag` | demo-pro |
| `sk-demo-enterprise-rag` | demo-enterprise |

Заголовок: **`X-API-Key`**.

## Змінні середовища

Див. `.env.example`: `OPENROUTER_API_KEY`, `QDRANT_*`, `REDIS_URL`, `DATABASE_URL`, `LANGFUSE_*`, `ADMIN_API_KEY`, `LLM_CONCURRENCY`, `EMBEDDING_MODEL`.

## Індексація

- Джерело за замовчуванням: `data/source.md` (або PDF, якщо розширення `.pdf`).
- Скрипт перестворює колекцію chunks у Qdrant і робить upsert.

```powershell
python scripts\index.py
```

## Адмін: перебудова індексу

```powershell
curl -X POST -H "X-Admin-Key: change-me-admin" http://127.0.0.1:8080/index/rebuild
```

Ключ задається в `ADMIN_API_KEY`. Паралельний другий rebuild поверне **409**, поки перший не завершиться.

## Usage

Потрібен той самий `X-API-Key`, що й для чату:

- `GET /usage/today`
- `GET /usage/breakdown` (вікно ~остання година, агрегати по моделях, cache hit / fallback rates)

## Деплой Fly.io

1. `fly launch` (або існуючий `fly.toml` + `fly apps create`).
2. `fly secrets set OPENROUTER_API_KEY=... QDRANT_URL=... REDIS_URL=...` тощо.
3. Для SQLite на Fly потрібен volume або зовнішня БД (`DATABASE_URL` Postgres).
4. Після деплою вкажіть публічний URL у `REPORT.md`.

У `fly.toml` встановлено **`auto_stop_machines = false`** згідно з планом.

## Acceptance (чеклист для REPORT.md)

- [ ] `curl -N` до `/chat/stream`, у `done` є `sources`.
- [ ] Повторний ідентичний запит — cache **HIT** (швидше), інший — **MISS**.
- [ ] **429** + `Retry-After` при перевищенні token bucket (великий `message` або багато запитів).
- [ ] Fallback: зламаний primary (наприклад, тимчасово змінити першу модель у YAML на неіснуючу) — відповідь з fallback, у `done` `fallback_used: true`.
- [ ] `GET /usage/today` після ~20 запитів.
- [ ] Скріншот трас у **Langfuse** (якщо ключі задані).

Детальні нотатки й скріншоти — у **`REPORT.md`**.
