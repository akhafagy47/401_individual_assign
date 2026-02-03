from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
import os

app = FastAPI(
    title="Campus Items API",
    description="REST API for managing campus items",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
DB_PATH = "items.db"
SEED_FILE = "data/seed.json"

# Pydantic Models
class Source(BaseModel):
    name: str = Field(..., min_length=1)

class ItemInput(BaseModel):
    title: str = Field(..., min_length=1)
    source: Source
    publishedAt: str
    url: str = Field(..., min_length=1)
    summary: str
    tags: List[str] = []
    
    @field_validator('publishedAt')
    @classmethod
    def validate_datetime(cls, v):
        try:
            # Validate ISO 8601 datetime format
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            # Ensure it ends with Z
            if not v.endswith('Z'):
                raise ValueError('Datetime must be in UTC with Z suffix')
            return v
        except Exception:
            raise ValueError('publishedAt must be a valid UTC datetime string (ISO 8601 format with Z, e.g., 2025-03-01T09:00:00Z)')

class ItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    source: Optional[Source] = None
    publishedAt: Optional[str] = None
    url: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    
    @field_validator('publishedAt')
    @classmethod
    def validate_datetime(cls, v):
        if v is not None:
            try:
                datetime.fromisoformat(v.replace('Z', '+00:00'))
                if not v.endswith('Z'):
                    raise ValueError('Datetime must be in UTC with Z suffix')
                return v
            except Exception:
                raise ValueError('publishedAt must be a valid UTC datetime string (ISO 8601 format with Z, e.g., 2025-03-01T09:00:00Z)')
        return v

class Item(BaseModel):
    id: str
    title: str
    source: Source
    publishedAt: str
    url: str
    summary: str
    tags: List[str]

# Database functions
def init_db():
    """Initialize the database with schema"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_name TEXT NOT NULL,
            publishedAt TEXT NOT NULL,
            url TEXT NOT NULL,
            summary TEXT NOT NULL,
            tags TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()

def load_seed_data():
    """Load seed data if database is empty"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if database is empty
    cursor.execute("SELECT COUNT(*) FROM items")
    count = cursor.fetchone()[0]
    
    if count == 0:
        # Load seed data
        if os.path.exists(SEED_FILE):
            with open(SEED_FILE, 'r') as f:
                seed_items = json.load(f)
            
            for item in seed_items:
                item_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO items (id, title, source_name, publishedAt, url, summary, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    item_id,
                    item['title'],
                    item['source']['name'],
                    item['publishedAt'],
                    item['url'],
                    item['summary'],
                    json.dumps(item['tags'])
                ))
            
            conn.commit()
    
    conn.close()

def row_to_item(row) -> dict:
    """Convert database row to Item dict"""
    return {
        "id": row[0],
        "title": row[1],
        "source": {"name": row[2]},
        "publishedAt": row[3],
        "url": row[4],
        "summary": row[5],
        "tags": json.loads(row[6])
    }

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()
    load_seed_data()

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

@app.get("/api/v1/items")
async def list_items(
    limit: int = Query(default=10, ge=1, le=20),
    offset: int = Query(default=0, ge=0)
):
    """List all items with pagination"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, source_name, publishedAt, url, summary, tags
        FROM items
        ORDER BY publishedAt DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    
    rows = cursor.fetchall()
    conn.close()
    
    items = [row_to_item(row) for row in rows]
    
    return {"status": "ok", "data": items}

@app.get("/api/v1/items/{item_id}")
async def get_item(item_id: str):
    """Get a single item by ID"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, source_name, publishedAt, url, summary, tags
        FROM items
        WHERE id = ?
    """, (item_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Item not found"
                }
            }
        )
    
    item = row_to_item(row)
    return {"status": "ok", "data": item}

@app.post("/api/v1/items", status_code=201)
async def create_item(item: ItemInput):
    """Create a new item"""
    try:
        item_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO items (id, title, source_name, publishedAt, url, summary, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id,
            item.title,
            item.source.name,
            item.publishedAt,
            item.url,
            item.summary,
            json.dumps(item.tags)
        ))
        
        conn.commit()
        conn.close()
        
        created_item = {
            "id": item_id,
            "title": item.title,
            "source": {"name": item.source.name},
            "publishedAt": item.publishedAt,
            "url": item.url,
            "summary": item.summary,
            "tags": item.tags
        }
        
        return {"status": "ok", "data": created_item}
    
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e)
                }
            }
        )

@app.patch("/api/v1/items/{item_id}")
async def update_item(item_id: str, update_data: dict):
    """Update an item (partial update)"""
    # Check if 'id' is in the request body
    if 'id' in update_data:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "id field cannot be updated"
                }
            }
        )
    
    # Validate the update data
    try:
        if update_data:
            # Create a partial model for validation
            ItemUpdate(**update_data)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e)
                }
            }
        )
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if item exists
    cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Item not found"
                }
            }
        )
    
    # Build update query
    update_fields = []
    update_values = []
    
    if 'title' in update_data:
        update_fields.append("title = ?")
        update_values.append(update_data['title'])
    
    if 'source' in update_data:
        update_fields.append("source_name = ?")
        update_values.append(update_data['source']['name'])
    
    if 'publishedAt' in update_data:
        update_fields.append("publishedAt = ?")
        update_values.append(update_data['publishedAt'])
    
    if 'url' in update_data:
        update_fields.append("url = ?")
        update_values.append(update_data['url'])
    
    if 'summary' in update_data:
        update_fields.append("summary = ?")
        update_values.append(update_data['summary'])
    
    if 'tags' in update_data:
        update_fields.append("tags = ?")
        update_values.append(json.dumps(update_data['tags']))
    
    if update_fields:
        update_values.append(item_id)
        query = f"UPDATE items SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, update_values)
        conn.commit()
    
    # Fetch updated item
    cursor.execute("""
        SELECT id, title, source_name, publishedAt, url, summary, tags
        FROM items
        WHERE id = ?
    """, (item_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    item = row_to_item(row)
    return {"status": "ok", "data": item}

@app.delete("/api/v1/items/{item_id}", status_code=204)
async def delete_item(item_id: str):
    """Delete an item"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if item exists
    cursor.execute("SELECT id FROM items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Item not found"
                }
            }
        )
    
    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    
    return None

# Frontend
@app.get("/", response_class=HTMLResponse)
async def frontend():
    """Serve the frontend page"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Campus Items</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 2rem;
            }
            
            #app-root {
                max-width: 800px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                padding: 2rem;
            }
            
            h1 {
                color: #333;
                margin-bottom: 1.5rem;
                font-size: 2rem;
            }
            
            button {
                background: #667eea;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 1rem;
                cursor: pointer;
                transition: background 0.3s;
            }
            
            button:hover {
                background: #5568d3;
            }
            
            .results {
                margin-top: 2rem;
                padding-top: 2rem;
                border-top: 2px solid #eee;
            }
            
            .stat {
                margin-bottom: 1rem;
                padding: 1rem;
                background: #f8f9fa;
                border-radius: 6px;
            }
            
            .label {
                font-weight: 600;
                color: #666;
                margin-bottom: 0.5rem;
            }
            
            .value {
                color: #333;
                font-size: 1.1rem;
            }
            
            .loading {
                display: none;
                margin-top: 1rem;
                color: #667eea;
                font-style: italic;
            }
            
            .loading.active {
                display: block;
            }
        </style>
    </head>
    <body>
        <div id="app-root" data-testid="app-root">
            <h1>Campus Items Viewer</h1>
            <button id="load-button" data-testid="load-button">Load Items</button>
            <div class="loading" id="loading">Loading...</div>
            <div class="results">
                <div class="stat">
                    <div class="label">Number of Items:</div>
                    <div class="value" id="items-count" data-testid="items-count">-</div>
                </div>
                <div class="stat">
                    <div class="label">First Item Title:</div>
                    <div class="value" id="first-item-title" data-testid="first-item-title">-</div>
                </div>
            </div>
        </div>
        
        <script>
            const loadButton = document.getElementById('load-button');
            const loading = document.getElementById('loading');
            const itemsCount = document.getElementById('items-count');
            const firstItemTitle = document.getElementById('first-item-title');
            
            loadButton.addEventListener('click', async () => {
                loading.classList.add('active');
                
                try {
                    const response = await fetch('/api/v1/items');
                    const result = await response.json();
                    
                    if (result.status === 'ok' && result.data) {
                        const items = result.data;
                        itemsCount.textContent = items.length;
                        
                        if (items.length > 0) {
                            firstItemTitle.textContent = items[0].title;
                        } else {
                            firstItemTitle.textContent = 'No items';
                        }
                    } else {
                        itemsCount.textContent = 'Error';
                        firstItemTitle.textContent = 'Error loading data';
                    }
                } catch (error) {
                    itemsCount.textContent = 'Error';
                    firstItemTitle.textContent = 'Failed to load items';
                } finally {
                    loading.classList.remove('active');
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Run with: uvicorn main:app --host 0.0.0.0 --port 8080