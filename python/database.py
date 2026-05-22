from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

client = AsyncIOMotorClient(
    settings.database_url,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
)

# Extract database name from URL, default to "sgarden"
db_name = settings.database_url.rsplit("/", 1)[-1].split("?")[0] if "/" in settings.database_url else "sgarden"
db = client[db_name]

users_collection = db["users"]
products_collection = db["products"]
orders_collection = db["orders"]
settings_collection = db["settings"]


async def init_indexes():
    await users_collection.create_index("username", unique=True)
    await users_collection.create_index("email", unique=True)
    await products_collection.create_index("category")
    await products_collection.create_index("price")
    await products_collection.create_index("stock")
    await products_collection.create_index([("name", "text"), ("description", "text")])
    await orders_collection.create_index("status")
    await orders_collection.create_index("createdAt")
