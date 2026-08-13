from fastapi import APIRouter

from novel_signal.modules.actions.router import router as actions_router
from novel_signal.modules.ads.router import router as ads_router
from novel_signal.modules.alerts.router import router as alerts_router
from novel_signal.modules.collection.router import router as collection_router
from novel_signal.modules.commerce.router import router as commerce_router
from novel_signal.modules.keywords.router import router as keywords_router
from novel_signal.modules.listings.router import router as listings_router
from novel_signal.modules.market_share.router import router as market_share_router
from novel_signal.modules.reviews.router import router as reviews_router
from novel_signal.modules.scorecards.router import router as scorecards_router
from novel_signal.modules.universe.router import router as universe_router
from novel_signal.modules.visibility.router import router as visibility_router

module_routers: tuple[APIRouter, ...] = (
    universe_router,
    keywords_router,
    visibility_router,
    ads_router,
    listings_router,
    commerce_router,
    reviews_router,
    market_share_router,
    scorecards_router,
    actions_router,
    alerts_router,
    collection_router,
)
