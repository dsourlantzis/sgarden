import logging
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status

from database import users_collection
from models.user import AuthResponse, LoginRequest, RegisterRequest
from security.jwt_handler import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger(__name__)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthResponse)
async def register(request: RegisterRequest):
    existing_user = await users_collection.find_one({"username": request.username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    existing_email = await users_collection.find_one({"email": request.email})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )

    user_doc = {
        "username": request.username,
        "email": request.email,
        "password": hash_password(request.password),
        "role": "user",
        "lastActiveAt": datetime.utcnow(),
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }

    result = await users_collection.insert_one(user_doc)
    user_id = str(result.inserted_id)

    token = create_token(user_id, request.username, "user")
    logger.info("User registered: %s", request.username)
    return AuthResponse(token=token, username=request.username, role="user")


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    user = await users_collection.find_one({"username": request.username})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not verify_password(request.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"lastActiveAt": datetime.utcnow()}},
    )

    user_id = str(user["_id"])
    token = create_token(user_id, user["username"], user["role"])
    logger.info("User logged in: %s", user["username"])
    return AuthResponse(token=token, username=user["username"], role=user["role"])
