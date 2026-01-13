from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import os
from datetime import datetime
import json

app = FastAPI(title="LabPilot API", description="API for managing ML experiments")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DB_PATH = os.getenv("LABPILOT_DB_PATH", "./labpilot.db")

# Pydantic models
class Experiment(BaseModel):
    id: int
    start_time: str
    end_time: Optional[str] = None
    server: Optional[str] = None
    command: str
    commit_hash: Optional[str] = None
    commit_message: Optional[str] = None
    params: Optional[str] = None
    ckpt_path: Optional[str] = None
    duration: Optional[float] = None
    status: str
    log_snippet: Optional[str] = None
    exit_code: Optional[int] = None

class ExperimentCreate(BaseModel):
    command: str
    commit_hash: Optional[str] = None
    params: Optional[str] = None

class ExperimentUpdate(BaseModel):
    end_time: Optional[str] = None
    duration: Optional[float] = None
    status: Optional[str] = None
    log_snippet: Optional[str] = None
    exit_code: Optional[int] = None
    ckpt_path: Optional[str] = None

def get_db_connection():
    """Get a connection to the SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This allows us to access columns by name
    return conn

def init_db():
    """Initialize the database with the experiments table if it doesn't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            server TEXT,
            command TEXT NOT NULL,
            commit_hash TEXT,
            commit_message TEXT,
            params TEXT,
            ckpt_path TEXT,
            duration REAL,
            status TEXT,
            log_snippet TEXT,
            exit_code INTEGER
        )
    """)
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

@app.get("/")
def read_root():
    return {"message": "Welcome to LabPilot API", "status": "running"}

@app.get("/experiments", response_model=List[Experiment])
def get_experiments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    server: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """
    Get a list of experiments with optional filtering and pagination
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Build the query with optional filters
    query = "SELECT * FROM experiments"
    conditions = []
    params = []
    
    if status:
        conditions.append("status = ?")
        params.append(status)
    
    if server:
        conditions.append("server = ?")
        params.append(server)
    
    if search:
        conditions.append("(command LIKE ? OR log_snippet LIKE ? OR ckpt_path LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
    params.extend([limit, skip])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    # Convert rows to Experiment objects
    experiments = []
    for row in rows:
        experiment_data = {k: row[k] for k in row.keys()}
        experiments.append(Experiment(**experiment_data))
    
    return experiments

@app.get("/experiments/{experiment_id}", response_model=Experiment)
def get_experiment(experiment_id: int):
    """
    Get a specific experiment by ID
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    experiment_data = {k: row[k] for k in row.keys()}
    return Experiment(**experiment_data)

@app.post("/experiments", response_model=Experiment)
def create_experiment(experiment: ExperimentCreate):
    """
    Create a new experiment record
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    current_time = datetime.now().isoformat()
    
    cursor.execute("""
        INSERT INTO experiments (start_time, command, commit_hash, params, status)
        VALUES (?, ?, ?, ?, ?)
    """, (current_time, experiment.command, experiment.commit_hash, experiment.params, "running"))
    
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Return the created experiment
    return get_experiment(new_id)

@app.put("/experiments/{experiment_id}", response_model=Experiment)
def update_experiment(experiment_id: int, experiment_update: ExperimentUpdate):
    """
    Update an existing experiment
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Build the update query dynamically based on provided fields
    update_fields = []
    params = []
    
    for field, value in experiment_update.dict(exclude_unset=True).items():
        if value is not None:
            update_fields.append(f"{field} = ?")
            params.append(value)
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    params.append(experiment_id)
    query = f"UPDATE experiments SET {', '.join(update_fields)} WHERE id = ?"
    
    cursor.execute(query, params)
    
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    conn.commit()
    conn.close()
    
    return get_experiment(experiment_id)

@app.get("/experiments/stats")
def get_experiment_stats():
    """
    Get statistics about experiments
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total count
    cursor.execute("SELECT COUNT(*) as count FROM experiments")
    total = cursor.fetchone()["count"]
    
    # Count by status
    cursor.execute("SELECT status, COUNT(*) as count FROM experiments GROUP BY status")
    status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
    
    # Count by server
    cursor.execute("SELECT server, COUNT(*) as count FROM experiments WHERE server IS NOT NULL GROUP BY server")
    server_counts = {row["server"]: row["count"] for row in cursor.fetchall()}
    
    # Recent experiments (last 24 hours)
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM experiments 
        WHERE start_time >= datetime('now', '-1 day')
    """)
    recent = cursor.fetchone()["count"]
    
    conn.close()
    
    return {
        "total_experiments": total,
        "status_counts": status_counts,
        "server_counts": server_counts,
        "recent_experiments": recent,
        "last_updated": datetime.now().isoformat()
    }

@app.delete("/experiments/{experiment_id}")
def delete_experiment(experiment_id: int):
    """
    Delete an experiment (soft delete by marking as deleted)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
    
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    conn.commit()
    conn.close()
    
    return {"message": "Experiment deleted successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)