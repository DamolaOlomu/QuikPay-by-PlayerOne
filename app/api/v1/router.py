"""
app/api/v1/router.py
"""
from fastapi import APIRouter

from app.api.v1.endpoints import users, transactions, wallets, kyc, payment_links, webhooks

api_router = APIRouter()

api_router.include_router(users.router)
api_router.include_router(transactions.router)
api_router.include_router(wallets.router)
api_router.include_router(kyc.router)
api_router.include_router(payment_links.router)
api_router.include_router(webhooks.router)
