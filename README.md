# Wokelo File Sync

Clean, modular copy of your current File Sync system with existing models, logic, and Celery workers.

Prerequisites
- Python 3.9+
- Redis running (WSL or local) at redis://localhost:6379/0
- PostgreSQL reachable (default DB_URL in .env or env vars)
- Box OAuth credentials in box_credentials.json (same as your current setup). Copy box_credentials.json from your old repo into this repo root.

Repository hygiene
- The repo ships with a .gitignore that skips venvs, IDE folders, compiled Python cache, elasticsearch artifacts, celery beat schedule files, and the exported main.zip archive.
- Keep secrets such as .env and box_credentials.json local; the ignore rules prevent accidental commits.
- Add any machine-only folders (ex: scratch data) to .gitignore before committing.

Setup (Windows PowerShell)
1) Create and activate venv
   
   ```powershell
   cd "C:\Users\Dell\Desktop\local\WokeloFileSync"
   py -3 -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2) Install dependencies
   
   ```powershell
   pip install -r requirements.txt
   ```

3) Initialize database schema (one-time)
   
   ```powershell
   python .\scripts\init_db.py
   ```

4) Environment
   - Create a .env in the repo root (optional) or export env vars before running:
   
   ```ini
   # .env example
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=password
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=filesync
   REDIS_URL=redis://localhost:6379/0
   INDEX_CHECK_INTERVAL_MINUTES=2
   PRUNE_CHECK_INTERVAL_MINUTES=5
   ```

5) Start Redis (if using WSL)
   - In WSL terminal:
   
   ```bash
   sudo redis-server /etc/redis/redis.conf
   ```

Run options
- Start API (FastAPI)
  
  ```powershell
  cd "C:\Users\Dell\Desktop\local\WokeloFileSync"
  .\venv\Scripts\Activate.ps1
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```
- Continuous (recommended):
  - Terminal 1 — Celery worker
    
    ```powershell
    cd "C:\Users\Dell\Desktop\local\WokeloFileSync"
    .\venv\Scripts\Activate.ps1
    celery -A workers.celery_worker_functional worker --loglevel=info --concurrency=1
    ```
  
  - Terminal 2 — Celery beat (schedules indexing + prune)
    
    ```powershell
    cd "C:\Users\Dell\Desktop\local\WokeloFileSync"
    .\venv\Scripts\Activate.ps1
    celery -A workers.celery_worker_functional beat --loglevel=info
    ```

- One-shot full cycle (index + local sync + prune):
  
  ```powershell
  cd "C:\Users\Dell\Desktop\local\WokeloFileSync"
  .\venv\Scripts\Activate.ps1
  python .\scripts\run_full_cycle.py
  ```

Environment (optional)
- Add these to .env if you use them:
  - ELASTICSEARCH_URL (default http://localhost:9200)
  - ELASTICSEARCH_INDEX_NAME (default documents)

Notes
- Database schema and table names are the same as your current system.
- Local storage sync writes to documents/box and documents/metadata relative to repo root.
- Box credentials are read from box_credentials.json in the current directory (same file as you use today).
