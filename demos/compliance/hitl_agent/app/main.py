import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from .db import init_db, add_task, get_pending_tasks, update_decision, get_task

# Initialize DB
init_db()

app = FastAPI(title="Nexus HITL Compliance Interceptor")
templates = Jinja2Templates(directory="app/templates")

@app.post("/rpc")
async def intercept_rpc(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Basic Validation
    if "jsonrpc" not in data or "method" not in data:
         raise HTTPException(status_code=400, detail="Invalid JSON-RPC")
    
    # Negative Testing: Check params
    if "params" not in data or "sender" not in data["params"]:
         raise HTTPException(status_code=400, detail="Missing params")

    # Extract info
    task_id = data.get("id")
    params = data.get("params", {})
    sender = params.get("sender", "unknown")
    
    message = params.get("message", {})
    # Handle different payload structures from generator
    if "metadata" in message:
        risk = message["metadata"].get("risk_score", 0)
        content = message.get("parts", [{}])[0].get("text", "No content")
    else:
        # Fallback
        risk = 0
        content = str(message)

    # Save to DB
    add_task(task_id, sender, content, risk)

    # Return "Paused" response
    return {
        "jsonrpc": "2.0",
        "result": {
            "status": "paused", 
            "reason": "Intercepted for Human Review (EU AI Act Art. 14)",
            "task_id": task_id
        },
        "id": task_id
    }

@app.get("/admin/tasks", response_class=HTMLResponse)
async def list_tasks(request: Request):
    tasks = get_pending_tasks()
    return templates.TemplateResponse("dashboard.html", {"request": request, "tasks": tasks})

@app.post("/admin/decide")
async def decide_task(request: Request, task_id: str = Form(...), action: str = Form(...), comment: str = Form("")):
    # Retrieve Task
    task = get_task(task_id)
    if not task:
        return "Task not found"
        
    status = "APPROVED" if action == "approve" else "REJECTED"
    update_decision(task_id, status, comment)
    
    # In a real impl, we would now client.post(NEXT_HOP, task_original_payload)
    # For PoC, we just update state.
    
    # Redirect back to dashboard
    tasks = get_pending_tasks()
    return templates.TemplateResponse("dashboard.html", {"request": request, "tasks": tasks})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)
