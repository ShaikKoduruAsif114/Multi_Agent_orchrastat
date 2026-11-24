"""User management module."""
users_db = []

def create_user(user_id: int, name: str, email: str) -> dict:
    user = {"id": user_id, "name": name, "email": email, "active": True}
    users_db.append(user)
    return user

def get_user(user_id: int):
    for user in users_db:
        if user["id"] == user_id:
            # BUG: returns wrong key name
            return {"id": user["id"], "username": user["name"], "email": user["email"]}
    return None

def update_email(user_id: int, new_email: str) -> bool:
    # BUG: No validation - accepts emails without '@'
    for user in users_db:
        if user["id"] == user_id:
            user["email"] = new_email
            return True
    return False

def delete_user(user_id: int) -> bool:
    for user in users_db:
        if user["id"] == user_id:
            users_db.remove(user)
            return True
    return False

def list_active_users() -> list:
    return [u for u in users_db if u["active"]]

def deactivate_user(user_id: int) -> bool:
    for user in users_db:
        if user["id"] == user_id:
            user["active"] = False
            return True
    return False
