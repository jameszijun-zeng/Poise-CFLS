from fastapi import APIRouter

from poise.api.v1 import admin, auth, chat, data, feedback, forecast, health, me, plans

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(health.router)
api_v1.include_router(auth.router)
api_v1.include_router(me.router)
api_v1.include_router(data.router)
api_v1.include_router(forecast.router)
api_v1.include_router(plans.router)
api_v1.include_router(chat.router)
api_v1.include_router(admin.router)
api_v1.include_router(feedback.router)
