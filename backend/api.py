from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
from fastapi.responses import StreamingResponse
import subprocess
import sqlite3
from orchestrator import Orchestrator
import os

app = FastAPI()

# Allow your Next.js frontend to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # Change to localhost:3000 in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "data/knowledge_base.db"

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

# @app.get("/api/transcripts")
# def get_transcripts():
#     """Fetch the debate log for the frontend chat UI."""
#     if not os.path.exists(DB_PATH):
#         return []
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = dict_factory
#     data = conn.execute("SELECT day, phase, agent, content FROM transcript ORDER BY id ASC").fetchall()
#     conn.close()
#     return data

@app.get("/api/findings")
def get_findings():
    """Fetch validated findings for the dashboard."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    data = conn.execute("SELECT * FROM findings ORDER BY day DESC").fetchall()
    conn.close()
    return data

@app.get("/api/hypotheses")
def get_hypotheses():
    """Fetch hypotheses for the Graveyard/Audit dashboard."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    data = conn.execute("SELECT day, status, votes_for, votes_against, content FROM hypotheses ORDER BY day DESC").fetchall()
    conn.close()
    return data

# Define what data the frontend will send us
class SimulationRequest(BaseModel):
    days: int
    topic: str

@app.post("/api/simulate")
def start_simulation(req: SimulationRequest, background_tasks: BackgroundTasks):
    """Trigger the multi-agent loop in the background."""
    
    def run_sim(topic: str, total_days: int):
        # We pass the dynamic topic from the frontend into the Orchestrator
        orch = Orchestrator(research_topic=topic)
        orch.run(total_days=total_days)
        
    # Run in background so the UI doesn't freeze waiting for the LLMs
    background_tasks.add_task(run_sim, req.topic, req.days)
    
    return {"message": f"Simulation started for {req.days} days on topic: {req.topic}"}

@app.delete("/api/clear")
def clear_database():
    """Wipes the database so you can start a fresh simulation from the UI."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        return {"message": "Database deleted successfully"}
    return {"message": "Database already empty or not found"}

@app.get("/api/stream")
async def stream_transcripts():
    """SSE endpoint pushing new database rows to the client."""
    async def event_generator():
        last_id = 0 
        
        while True:
            # FIX 1: If the DB file is missing, reset the ID counter to 0
            if not os.path.exists(DB_PATH):
                last_id = 0 
                await asyncio.sleep(1)
                continue
                
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = dict_factory
            
            # FIX 2: Check if the DB was recreated and IDs started over
            max_id_query = conn.execute("SELECT MAX(id) as max_id FROM transcript").fetchone()
            current_max = max_id_query['max_id'] if max_id_query['max_id'] else 0
            
            # If the database max ID is suddenly smaller than our tracker, it was cleared!
            if last_id > current_max:
                last_id = 0
            
            # Query ONLY the messages that are newer than our last_id
            new_msgs = conn.execute(
                "SELECT id, day, phase, agent, content FROM transcript WHERE id > ?", 
                (last_id,)
            ).fetchall()
            conn.close()

            if new_msgs:
                last_id = new_msgs[-1]['id']
                yield f"data: {json.dumps(new_msgs)}\n\n"
            
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")