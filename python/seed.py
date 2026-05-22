import logging
from datetime import datetime

from database import users_collection, products_collection
from security.jwt_handler import hash_password

logger = logging.getLogger(__name__)


SEED_USERS = [
    {
        "username": "admin",
        "email": "admin@sgarden.com",
        "password": hash_password("admin123"),
        "role": "admin",
        "lastActiveAt": datetime.utcnow(),
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
    {
        "username": "user",
        "email": "user@sgarden.com",
        "password": hash_password("user1234"),
        "role": "user",
        "lastActiveAt": datetime.utcnow(),
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    },
]

SEED_PRODUCTS = [
    {"name": "Wireless Mouse", "description": "Ergonomic wireless mouse with USB receiver", "category": "Electronics", "price": 29.99, "stock": 150},
    {"name": "Mechanical Keyboard", "description": "RGB mechanical keyboard with Cherry MX switches", "category": "Electronics", "price": 89.99, "stock": 75},
    {"name": "USB-C Hub", "description": "7-in-1 USB-C hub with HDMI and Ethernet", "category": "Electronics", "price": 45.99, "stock": 200},
    {"name": "Monitor Stand", "description": "Adjustable monitor stand with USB ports", "category": "Accessories", "price": 34.99, "stock": 120},
    {"name": "Webcam HD", "description": "1080p HD webcam with built-in microphone", "category": "Electronics", "price": 59.99, "stock": 90},
    {"name": "Desk Lamp", "description": "LED desk lamp with adjustable brightness", "category": "Accessories", "price": 24.99, "stock": 180},
    {"name": "Cable Organizer", "description": "Silicone cable management clips, pack of 10", "category": "Accessories", "price": 9.99, "stock": 500},
    {"name": "Laptop Sleeve", "description": "Neoprene laptop sleeve for 15-inch laptops", "category": "Accessories", "price": 19.99, "stock": 250},
    {"name": "External SSD", "description": "1TB portable external SSD, USB 3.2", "category": "Storage", "price": 79.99, "stock": 60},
    {"name": "USB Flash Drive", "description": "64GB USB 3.0 flash drive", "category": "Storage", "price": 12.99, "stock": 400},
    {"name": "Ethernet Cable", "description": "Cat6 ethernet cable, 10 meters", "category": "Networking", "price": 8.99, "stock": 300},
    {"name": "Wi-Fi Router", "description": "Dual-band Wi-Fi 6 router", "category": "Networking", "price": 129.99, "stock": 45},
    {"name": "Mouse Pad XL", "description": "Extended gaming mouse pad, 900x400mm", "category": "Accessories", "price": 15.99, "stock": 200},
    {"name": "Headphone Stand", "description": "Aluminum headphone stand", "category": "Accessories", "price": 22.99, "stock": 100},
    {"name": "Power Strip", "description": "6-outlet power strip with USB charging", "category": "Electronics", "price": 18.99, "stock": 350},
]


async def seed_data():
    """Seed test users and sample products if they don't exist."""
    # Seed users
    for user_data in SEED_USERS:
        existing = await users_collection.find_one({"username": user_data["username"]})
        if not existing:
            await users_collection.insert_one(user_data.copy())
            logger.info("Seeded user: %s", user_data["username"])

    # Seed products
    count = await products_collection.count_documents({})
    if count == 0:
        products_to_insert = []
        for p in SEED_PRODUCTS:
            product = {**p, "createdAt": datetime.utcnow(), "updatedAt": datetime.utcnow()}
            products_to_insert.append(product)
        await products_collection.insert_many(products_to_insert)
        logger.info("Seeded %d products", len(products_to_insert))
