# Thread-safe global workflow state dictionary for web UI interaction
CURRENT_WORKFLOW = {
    "status": "idle",  # "idle", "running", "waiting_approval", "completed", "failed"
    "state": None,
    "user_decision": None,
}
