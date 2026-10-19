from bot.handlers.private import router as private_router
from bot.handlers.group import router as group_router
from bot.handlers.stats import router as stats_router
from bot.handlers.themes import router as themes_router

__all__ = ["private_router", "group_router", "stats_router", "themes_router"]
