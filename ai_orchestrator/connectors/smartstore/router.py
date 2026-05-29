"""스마트스토어 통합 라우터 — 하위 모듈을 하나의 APIRouter로 조합합니다."""
from fastapi import APIRouter

from .catalog      import router as catalog_router
from .products     import router as products_router
from .orders       import router as orders_router
from .settlements  import router as settlements_router
from .reviews      import router as reviews_router
from .stats        import router as stats_router
from .marketing    import router as marketing_router
from .description  import router as description_router
from .popup        import router as popup_router
from .seller_center import router as seller_center_router

smartstore_router = APIRouter(prefix="/smartstore", tags=["smartstore"])

smartstore_router.include_router(catalog_router)
smartstore_router.include_router(products_router)
smartstore_router.include_router(orders_router)
smartstore_router.include_router(settlements_router)
smartstore_router.include_router(reviews_router)
smartstore_router.include_router(stats_router)
smartstore_router.include_router(marketing_router)
smartstore_router.include_router(description_router)
smartstore_router.include_router(popup_router)
smartstore_router.include_router(seller_center_router)

__all__ = ["smartstore_router"]
