import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "hitl_tasks.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (id TEXT PRIMARY KEY, 
                  sender TEXT, 
                  content TEXT, 
                  risk_score INTEGER,
                  status TEXT, 
                  timestamp TEXT,
                  decision_comment TEXT)''')
    conn.commit()
    conn.close()

def add_task(task_id, sender, content, risk_score):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?)",
              (task_id, sender, content, risk_score, "PENDING", datetime.now().isoformat(), ""))
    conn.commit()
    conn.close()

def get_pending_tasks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE status = 'PENDING'")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_decision(task_id, status, comment):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tasks SET status = ?, decision_comment = ? WHERE id = ?",
              (status, comment, task_id))
    conn.commit()
    conn.close()

def get_task(task_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None
