# Thread-safe global workflow state dictionary for web UI interaction
import datetime

CURRENT_WORKFLOW = {
    "status": "idle",  # "idle", "running", "waiting_approval", "completed", "failed"
    "state": None,
    "user_decision": None,
    "logs": []
}

def log_step(message: str, level: str = "info"):
    """Append a timestamped log entry to the live workflow logs array."""
    now = datetime.datetime.now().strftime("%I:%M:%S %p").lower()
    entry = {"time": now, "msg": message, "type": level}
    if "logs" not in CURRENT_WORKFLOW:
        CURRENT_WORKFLOW["logs"] = []
    CURRENT_WORKFLOW["logs"].append(entry)
    print(f"[{now}] [{level.upper()}] {message}")
