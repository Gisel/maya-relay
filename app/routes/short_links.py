from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.db import RelayRepository
from app.dependencies import get_repository


router = APIRouter(tags=["short-links"])


@router.get("/i/{token}", include_in_schema=False)
def resolve_short_link(token: str, repository: RelayRepository = Depends(get_repository)) -> RedirectResponse:
    target_url = repository.get_short_link(token)
    if target_url is None:
        raise HTTPException(status_code=404)
    return RedirectResponse(target_url, status_code=302)
