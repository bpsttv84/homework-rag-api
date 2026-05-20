# ДЗ 10 — Production RAG API. Пояснення для здачі

**Студент:** TARAS TARAN (`bpsttv84` на GitHub)  
**Проєкт:** `homework-rag-api`  
**Публічний URL (Fly.io):** https://homework-rag-api.fly.dev  

---

## 1. Що реалізовано

Окремий **production-oriented RAG API** (FastAPI) без high-level RAG-фреймворків:

| Компонент | Реалізація |
|-----------|------------|
| RAG | Qdrant колекція `rag_chunks`, chunking ~500 tok / overlap 50, `sentence-transformers` (384 dim) |
| Semantic cache | Окрема колекція `rag_cache`, поріг similarity 0.92, TTL 1 год |
| LLM | OpenRouter (`AsyncOpenAI`), fallback chain, circuit breaker, timeout 15 с |
| Rate limit | Redis token bucket (без Lua), pre-check + post-consume, 429 + `Retry-After` |
| Auth | 3 tier × 3 моделі в `app/api_keys.yaml`, заголовок `X-API-Key` |
| Security | ≥5 regex на injection, `suspicious_*.log`, post-check output |
| Cost | SQLite (локально) / опційно Postgres, `GET /usage/today`, `/usage/breakdown` |
| Observability | Langfuse SDK 4.x (spans: embed, cache, retrieve, llm) |
| Deploy | Fly.io, `auto_stop_machines = false`, healthcheck `/health` |

---

## 2. Перевірка на проді (виконано)

```text
GET https://homework-rag-api.fly.dev/health
→ {"liveness":"ok","active_streams":0,"aborted_streams":0}

POST /index/rebuild (X-Admin-Key)
→ {"status":"accepted"}

POST /chat/stream (X-API-Key: sk-demo-free-rag)
→ SSE tokens + done з sources: ["0"], model, cache_hit, fallback_used

GET /usage/today
→ requests/tokens/cost_usd
```

Демо-ключі для перевірки викладачем — у `app/api_keys.yaml` (наприклад `sk-demo-free-rag`).

---

## 3. Acceptance checklist (відповідність ТЗ)

| Вимога | Статус | Доказ |
|--------|--------|-------|
| SSE `/chat/stream`, `sources` у `done` | ✓ | `02-chat-stream-done.png`, прод curl |
| Cache MISS → HIT | ✓ | `02` + `03-cache-hit.png` |
| 429 + Retry-After | ✓ | `06-429-retry-after.png` |
| Fallback | ✓ | `07-fallback.png`, `fallback_used: true` на першому запиті |
| `/usage/today` | ✓ | `04-usage-today.png` |
| Langfuse traces | ✓ | `08-langfuse.png` |
| Fly deploy + публічний URL | ✓ | `09-fly-dashboard*.png`, https://homework-rag-api.fly.dev |

---

## 4. Зовнішні сервіси (free tier)

- **OpenRouter** — LLM  
- **Qdrant Cloud** — vectors + cache  
- **Upstash Redis** — rate limit (на Fly; локально — Docker Redis)  
- **Langfuse Cloud** — traces  
- **Fly.io** — hosting  

Секрети на Fly задані через `flyctl secrets set` (не в репозиторії).

---

## 5. Як запустити локально

```powershell
cd homework-rag-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# заповнити OPENROUTER_API_KEY та інші ключі
docker compose up -d
python scripts\index.py
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Чат (PowerShell): `.\scripts\example-chat-stream.ps1` або `curl.exe --%` (див. README).

---

## 6. Структура здачі

| Що здається | Де |
|-------------|-----|
| Код | GitHub repo (посилання нижче) |
| `.env.example` | у репозиторії |
| Скріншоти | `report/screenshots/` + `REPORT.md` |
| Архів | `homework-rag-api-DZ10-submission.zip` (код без `.env`, `.venv`, зі скрінами) |
| Цей файл | `SUBMISSION.md` — коротке пояснення для викладача |

---

## 7. Відомі обмеження / ризики

- Образ Docker ~2.8 GB (PyTorch + sentence-transformers); cold start на Fly може бути довгим.  
- На Fly: 2 GB RAM у `fly.toml`.  
- Перший deploy вимагав коректних `fly secrets` (Redis/Qdrant не `localhost`).  
- Для здачі використовуються **demo API keys** з `api_keys.yaml`; у проді їх слід замінити.

---

## 8. Посилання

- **Production API:** https://homework-rag-api.fly.dev  
- **GitHub:** _(додай після `git push`)_  
- **Звіт зі скрінами:** `REPORT.md`  
