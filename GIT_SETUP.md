# Git + GitHub — покроково (Windows)

Профіль GitHub: **bpsttv84** (TARAS TARAN).

## 1. Встановити Git (якщо `git` не знаходиться в терміналі)

```powershell
winget install -e --id Git.Git
```

Перезапусти PowerShell / Cursor.

## 2. Ім’я та email (один раз)

```powershell
git config --global user.name "TARAS TARAN"
git config --global user.email "tarantarasik@gmail.com"
```

Email — той, що прив’язаний до GitHub (Settings → Emails).

## 3. Репозиторій на GitHub

1. https://github.com/new  
2. Name: `homework-rag-api` (або `lesson-10-rag-api`)  
3. **Private** або Public — на вибір викладача  
4. **Не** додавай README/LICENSE з веб-інтерфейсу (репо порожній).

## 4. SSH (рекомендовано) або HTTPS

**SSH:** Settings → SSH and GPG keys → New SSH key.

```powershell
ssh-keygen -t ed25519 -C "твій@email.com" -f "$env:USERPROFILE\.ssh\id_ed25519_github"
Get-Content "$env:USERPROFILE\.ssh\id_ed25519_github.pub"
```

Встав публічний ключ у GitHub. Перевірка:

```powershell
ssh -T git@github.com
```

## 5. Ініціалізація проєкту

```powershell
cd "E:\_r_d\Заняття 10 - API Layer for AI Systems\lesson-10-api-layer-ai-systems\homework-rag-api"

git init
git add .
git status
# переконайся: .env НЕ в списку (є в .gitignore)
git commit -m "ДЗ 10: Production RAG API — FastAPI, Qdrant, Redis, Fly deploy"
git branch -M main
git remote add origin git@github.com:bpsttv84/homework-rag-api.git
git push -u origin main
```

Якщо remote вже існує: `git remote set-url origin git@github.com:bpsttv84/homework-rag-api.git`

## 6. Після push

Додай URL у `SUBMISSION.md` і `REPORT.md`:

`https://github.com/bpsttv84/homework-rag-api`

## Безпека

- Файл **`.env` ніколи не комітити** (вже в `.gitignore`).  
- Якщо ключі потрапили в чат/термінал — **ротуй** OpenRouter, Qdrant, Upstash, `ADMIN_API_KEY` на Fly.
