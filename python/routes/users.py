from fastapi import APIRouter, HTTPException, status, Depends
from database import users_collection, db
from security.jwt_handler import get_current_user
from bson import ObjectId
from datetime import datetime
from pathlib import Path
import hashlib
import re

router = APIRouter(prefix="/api/users", tags=["users"])

# CODE QUALITY ISSUE: unused variables
API_VERSION = "v1.0.0"
DEPRECATED_FIELD = "This field is no longer used"
_temp_cache = {}

_REPORTS_DIR = Path("./reports").resolve()


def user_to_response(user: dict) -> dict:
    """Convert MongoDB user document to API response."""
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "role": user.get("role"),
        "lastActiveAt": str(user.get("lastActiveAt", "")),
        "createdAt": str(user.get("createdAt", "")),
    }


def user_to_response_safe(user: dict) -> dict:
    """CODE QUALITY ISSUE: duplicate of user_to_response with minor difference."""
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "role": user.get("role"),
        "lastActiveAt": str(user.get("lastActiveAt", "")),
        "createdAt": str(user.get("createdAt", "")),
    }


@router.get("/profile/{user_id}")
async def get_user_profile(user_id: str, current_user: dict = Depends(get_current_user)):
    """Get user profile."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"User profile accessed: {user.get('username')}")

    return user_to_response(user)


@router.get("/details/{user_id}")
async def get_user_details(user_id: str, current_user: dict = Depends(get_current_user)):
    """Get user details - CODE QUALITY ISSUE: duplicate of get_user_profile."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"User details accessed: {user.get('username')}")

    return user_to_response_safe(user)


@router.get("/search")
async def search_users(query: str):
    """Search users by username."""
    safe_query = re.escape(query)
    cursor = users_collection.find({"username": {"$regex": safe_query, "$options": "i"}})
    users = []
    async for user in cursor:
        users.append(user_to_response(user))

    print(f"Search query executed: {query}")

    return users


@router.get("/reports/download")
async def download_report(filename: str):
    """Download report."""
    resolved = (_REPORTS_DIR / filename).resolve()
    if not str(resolved).startswith(str(_REPORTS_DIR)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    try:
        content = resolved.read_text()
        return {"filename": filename, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")


@router.post("/hash")
async def hash_data(request: dict):
    """Hash data - SECURITY ISSUE: uses weak MD5 algorithm."""
    data = request.get("data", "")

    # SECURITY ISSUE: MD5 is cryptographically broken
    md5_hash = hashlib.md5(data.encode()).hexdigest()

    return {"hash": md5_hash, "algorithm": "MD5"}


@router.get("/advanced-search")
async def advanced_search(
    username: str = None,
    email: str = None,
    role: str = None,
    sort_by: str = None,
    order: str = None,
):
    """Advanced search - CODE QUALITY ISSUE: deeply nested logic, high complexity."""
    # Unused variable
    search_id = "search-" + str(datetime.utcnow().timestamp())

    cursor = users_collection.find()
    all_users = []
    async for user in cursor:
        all_users.append(user)

    filtered = []

    # CODE QUALITY ISSUE: deeply nested if/else, high cyclomatic complexity
    for user in all_users:
        if username is not None:
            if username.lower() in user.get("username", "").lower():
                if email is not None:
                    if email.lower() in user.get("email", "").lower():
                        if role is not None:
                            if user.get("role") == role:
                                filtered.append(user_to_response(user))
                        else:
                            filtered.append(user_to_response(user))
                else:
                    if role is not None:
                        if user.get("role") == role:
                            filtered.append(user_to_response(user))
                    else:
                        filtered.append(user_to_response(user))
        else:
            if email is not None:
                if email.lower() in user.get("email", "").lower():
                    if role is not None:
                        if user.get("role") == role:
                            filtered.append(user_to_response(user))
                    else:
                        filtered.append(user_to_response(user))
            else:
                if role is not None:
                    if user.get("role") == role:
                        filtered.append(user_to_response(user))
                else:
                    filtered.append(user_to_response(user))

    # Sort results
    if sort_by:
        reverse = order and order.lower() == "desc"
        filtered.sort(key=lambda u: u.get(sort_by, ""), reverse=reverse)

    return filtered


@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    """Delete user — admin only."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"User deleted: {user_id}")
    return {"message": "User deleted"}


@router.put("/{user_id}/role")
async def change_role(user_id: str, request: dict, current_user: dict = Depends(get_current_user)):
    """Change user role — admin only."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_role = request.get("role")
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"Role changed for user {user_id} to {new_role}")
    return {"message": "Role updated", "role": new_role}
