import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database import users_collection
from security.jwt_handler import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])

_ALLOWED_USER_SORT_FIELDS = {"username", "email", "role", "createdAt", "lastActiveAt"}
_VALID_ROLES = {"admin", "user"}
_REPORTS_DIR = Path("./reports").resolve()


def user_to_response(user: dict) -> dict:
    created = user.get("createdAt")
    last_active = user.get("lastActiveAt")
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "role": user.get("role"),
        "lastActiveAt": last_active.isoformat() if last_active else "",
        "createdAt": created.isoformat() if created else "",
    }


@router.get("/profile/{user_id}")
async def get_user_profile(user_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = await users_collection.find_one({"_id": ObjectId(user_id)}, {"password": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    logger.info("User profile accessed: %s", user.get("username"))
    return user_to_response(user)


@router.get("/search")
async def search_users(
    query: str,
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    safe_query = re.escape(query)
    users = []
    async for user in users_collection.find(
        {"username": {"$regex": safe_query, "$options": "i"}},
        {"password": 0},
    ).limit(limit):
        users.append(user_to_response(user))
    return users


@router.get("/reports/download")
async def download_report(filename: str, current_user: dict = Depends(get_current_user)):
    resolved = (_REPORTS_DIR / filename).resolve()
    if not str(resolved).startswith(str(_REPORTS_DIR)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    try:
        content = resolved.read_text()
        return {"filename": filename, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")


@router.post("/hash")
async def hash_data(request: dict, current_user: dict = Depends(get_current_user)):
    data = request.get("data", "")
    digest = hashlib.sha256(data.encode()).hexdigest()
    return {"hash": digest, "algorithm": "SHA-256"}


@router.get("/advanced-search")
async def advanced_search(
    username: str = None,
    email: str = None,
    role: str = None,
    sort_by: str = None,
    order: str = None,
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    query = {}
    if username:
        query["username"] = {"$regex": re.escape(username), "$options": "i"}
    if email:
        query["email"] = {"$regex": re.escape(email), "$options": "i"}
    if role:
        if role not in _VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Validation failed", "errors": {"role": f"role must be one of: {', '.join(sorted(_VALID_ROLES))}"}},
            )
        query["role"] = role

    sort_field = sort_by if sort_by in _ALLOWED_USER_SORT_FIELDS else "_id"
    sort_dir = -1 if (order or "").lower() == "desc" else 1

    users = []
    async for user in users_collection.find(query, {"password": 0}).sort(sort_field, sort_dir).limit(limit):
        users.append(user_to_response(user))
    return users


@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    logger.info("User deleted: %s", user_id)
    return {"message": "User deleted"}


@router.put("/{user_id}/role")
async def change_role(user_id: str, request: dict, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_role = request.get("role")
    if new_role not in _VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": {"role": f"role must be one of: {', '.join(sorted(_VALID_ROLES))}"}},
        )

    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    logger.info("Role changed for user %s to %s", user_id, new_role)
    return {"message": "Role updated", "role": new_role}
