from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.db.queries.packages import list_packages, get_package_by_id
from app.models.package import PackageSummary, Package

router = APIRouter(tags=["packages"])


@router.get("/packages", response_model=list[PackageSummary])
def get_packages(conn=Depends(get_db)):
    return list_packages(conn)


@router.get("/packages/{package_id}", response_model=Package)
def get_package(package_id: str, conn=Depends(get_db)):
    return get_package_by_id(conn, package_id)
