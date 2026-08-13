from fastapi import APIRouter


def scaffold_router(*, prefix: str, tag: str, owner: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("/meta", name=f"{tag}_module_meta")
    def module_meta() -> dict[str, str]:
        return {"module": tag, "owner": owner, "status": "scaffolded"}

    return router
