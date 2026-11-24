# Thread-safe global workflow states dictionary for multi-tenant web UI interaction
import datetime

WORKFLOWS = {}

def get_session_state(session_id: str):
    """Retrieve or initialize the state for a specific session."""
    if session_id not in WORKFLOWS:
        WORKFLOWS[session_id] = {
            "status": "idle",  # "idle", "running", "waiting_approval", "completed", "failed"
            "state": None,
            "user_decision": None,
            "logs": []
        }
    return WORKFLOWS[session_id]

def log_step(message: str, level: str = "info", session_id: str = "default"):
    """Append a timestamped log entry to the live workflow logs array for a specific session."""
    now = datetime.datetime.now().strftime("%I:%M:%S %p").lower()
    entry = {"time": now, "msg": message, "type": level}
    session_state = get_session_state(session_id)
    if "logs" not in session_state:
        session_state["logs"] = []
    session_state["logs"].append(entry)
    print(f"[{session_id}] [{now}] [{level.upper()}] {message}")
