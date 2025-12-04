# WokeloFileSync - Complete Setup Guide

A modern file synchronization system that connects to cloud storage providers (like Box), indexes documents with full-text search, and provides automated sync capabilities using Celery workers.

## 🚀 Quick Start Overview

WokeloFileSync consists of:
- **FastAPI Server** - REST API for managing connectors and search
- **Celery Workers** - Background tasks for document processing
- **Elasticsearch** - Full-text search and indexing
- **PostgreSQL** - Metadata and configuration storage
- **Redis** - Task queue and caching

---

## 📋 Prerequisites & Services Setup

### 1. **Install Required Services**

#### **PostgreSQL Database**
```powershell
# Download and install PostgreSQL from https://www.postgresql.org/download/windows/
# During installation, remember your postgres user password

# After installation, create your database:
psql -U postgres -c "CREATE DATABASE filesync_dev;"
psql -U postgres -c "CREATE USER filesync WITH PASSWORD 'password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE filesync_dev TO filesync;"
```

#### **Redis Server**
```powershell
# Option 1: Install Redis for Windows
# Download from https://github.com/microsoftarchive/redis/releases
# Or use Windows Subsystem for Linux (WSL) with Redis

# Option 2: Use Docker
docker run -d -p 6379:6379 redis:latest

# Verify Redis is running
redis-cli ping  # Should return "PONG"
```

#### **Elasticsearch**
```powershell
# Download Elasticsearch 7.16.x from https://www.elastic.co/downloads/elasticsearch
# Extract and run:
bin\elasticsearch.bat

# Verify it's running
Invoke-RestMethod http://localhost:9200
```

### 2. **Python Environment Setup**

```powershell
# Navigate to project directory
cd path\to\WokeloFileSync

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. **Environment Configuration**

Create a `.env` file in the project root:

```env
# Box OAuth (Get from Box Developer Console)
BOX_CLIENT_ID=your_box_client_id
BOX_CLIENT_SECRET=your_box_client_secret
BOX_REDIRECT_URI=http://127.0.0.1:8000/auth/box/callback

# Database
POSTGRES_USER=filesync
POSTGRES_PASSWORD=password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=filesync_dev
DATABASE_URL=postgresql://filesync:password@localhost:5432/filesync_dev

# Redis
REDIS_URL=redis://localhost:6379/0

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200

# Advanced Features
USE_ADVANCED_INDEXING=true
ENABLE_EMBEDDINGS=true
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# App Settings
LOG_LEVEL=INFO
INDEX_CHECK_INTERVAL_MINUTES=2
PRUNE_CHECK_INTERVAL_MINUTES=5
```

### 4. **Database Schema Setup**

```powershell
# Initialize database schema
psql -U filesync -d filesync_dev -f infra/db/schema.sql

# Setup initial Box connector (optional)
psql -U filesync -d filesync_dev -f infra/db/setup_box.sql
```

---

## 🔧 Running the System

### **1. Start Core Services**

Make sure these are running:
- PostgreSQL (port 5432)
- Redis (port 6379) 
- Elasticsearch (port 9200)

### **2. Start FastAPI Server**

```powershell
# In terminal 1 (with venv activated)
cd WokeloFileSync
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Server will be available at: http://localhost:8000

### **3. Start Celery Workers**

```powershell
# In terminal 2 (with venv activated)
cd WokeloFileSync
.\.venv\Scripts\Activate.ps1
python -m celery -A workers.celery_worker_functional worker --loglevel=info --pool=solo
```

### **4. Start Celery Beat Scheduler (Optional)**

```powershell
# In terminal 3 (with venv activated)
cd WokeloFileSync
.\.venv\Scripts\Activate.ps1
python -m celery -A workers.celery_worker_functional beat --loglevel=info
```

---

## 🔌 Creating a New Connector

### **Method 1: Using Box Connector (Built-in)**

#### **Step 1: Setup Box App**
1. Go to https://developer.box.com/
2. Create new app → Custom App → Server Authentication (with JWT) or OAuth 2.0
3. Get your `Client ID` and `Client Secret`
4. Add redirect URI: `http://127.0.0.1:8000/auth/box/callback`

#### **Step 2: Authenticate via API**

```powershell
# Start OAuth flow
Invoke-RestMethod -Uri "http://localhost:8000/auth/box/start" -Method GET

# Follow the URL to authorize, then the callback will save your credentials automatically
```

#### **Step 3: Create Connector-Credential Pair**

```powershell
# List available connectors
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/connectors" -Method GET

# Create CC pair (replace IDs with actual values)
$ccPairData = @{
    connector_id = 1
    credential_id = 1
    name = "My Box Sync"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/cc_pairs" -Method POST -ContentType "application/json" -Body $ccPairData
```

#### **Step 4: Trigger Initial Sync**

```powershell
# Trigger sync (replace 1 with your CC pair ID)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/sync/1/trigger" -Method POST
```

### **Method 2: Creating a Custom Connector**

#### **Step 1: Create Connector Class**
```python
# Create file: connectors/mycustom/connector.py
from connectors.base import BaseConnector, DocumentItem
from typing import Iterator, Dict, Any

class MyCustomConnector(BaseConnector):
    def list_all_items(self, access_token: str, config: Dict[str, Any]) -> Iterator[DocumentItem]:
        # Your implementation here
        pass
    
    def download_file(self, access_token: str, file_id: str, local_path: str) -> bool:
        # Your implementation here
        pass
```

#### **Step 2: Register Connector**
```python
# Add to connectors/registry.py
from connectors.mycustom.connector import MyCustomConnector

# In CONNECTORS dict:
CONNECTORS = {
    "box": BoxConnector,
    "mycustom": MyCustomConnector,  # Add this line
}
```

#### **Step 3: Create via API**
```powershell
$connectorData = @{
    name = "My Custom Connector"
    source = "mycustom"
    input_type = "load_state"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/connectors" -Method POST -ContentType "application/json" -Body $connectorData
```

---

## 📊 Using the System

### **Search Documents**

```powershell
# Basic search
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/search?q=your_query&size=10" -Method GET

# Advanced search with Python
python -c "
from infra.document_index.elasticsearch.index import search
results = search(q='your query', size=10)
print(results)
"
```

### **Monitor System Status**

```powershell
# Check API health
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -Method GET

# Check Elasticsearch
Invoke-RestMethod -Uri "http://localhost:9200/_cluster/health" -Method GET

# Check indexed documents
Invoke-RestMethod -Uri "http://localhost:9200/documents/_count" -Method GET
```

### **Manual Operations**

```powershell
# Manual sync trigger
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/sync/{cc_pair_id}/trigger" -Method POST

# Manual pruning (cleanup deleted files)
python -c "
from workers.celery_worker_functional import cleanup_deleted_files
cleanup_deleted_files.delay(1)  # 1 = connector_id
print('Pruning triggered!')
"
```

---

## 🔄 Automated Operations

### **PowerShell Scripts (Included)**

```powershell
# Start all automation
.\start_automation.ps1

# Stop all automation  
.\stop_automation.ps1

# Check status
.\check_status.ps1

# Box OAuth helper
.\box_oauth.ps1
```

### **Scheduled Tasks**
The system automatically runs:
- **Document Indexing**: Every 2 minutes
- **Cleanup/Pruning**: Every 5 minutes

---

## 🔍 Troubleshooting

### **Common Issues**

#### **Celery Worker Not Starting**
```powershell
# Check Redis connection
redis-cli ping

# Use solo pool on Windows
celery -A workers.celery_worker_functional worker --pool=solo
```

#### **Database Connection Issues**
```powershell
# Test connection
python -c "
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv
load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    print('Database connected successfully!')
"
```

#### **Elasticsearch Issues**
```powershell
# Check if ES is running
curl http://localhost:9200

# Check index status
curl http://localhost:9200/documents/_stats
```

### **Log Locations**
- **FastAPI**: Console output where uvicorn is running
- **Celery Worker**: Console output where celery worker is running
- **Elasticsearch**: `logs/` directory in ES installation

---

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   FastAPI       │    │  Celery Workers  │    │  Elasticsearch  │
│   (REST API)    │────│  (Background)    │────│  (Search Index) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                        │
         │              ┌──────────────────┐               │
         │              │     Redis        │               │
         └──────────────│  (Task Queue)    │───────────────┘
                        └──────────────────┘
                                 │
                        ┌──────────────────┐
                        │   PostgreSQL     │
                        │   (Metadata)     │
                        └──────────────────┘
```

## 📚 API Documentation

Once the FastAPI server is running, visit:
- **Interactive API Docs**: http://localhost:8000/docs
- **OpenAPI Schema**: http://localhost:8000/openapi.json

---

## 🎯 Next Steps

1. **Setup your first connector** (Box recommended for testing)
2. **Upload some files** to your connected storage
3. **Trigger sync** and watch documents get indexed
4. **Search your documents** using the API or directly via Elasticsearch
5. **Set up automated scheduling** for continuous sync

For advanced configurations and custom connectors, refer to the code examples in the `connectors/` directory.

---

**Need Help?** Check the logs, verify all services are running, and ensure your `.env` file is properly configured.