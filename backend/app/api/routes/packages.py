from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.deps import get_db
from app.db.queries.packages import list_packages, get_package_by_id
from app.models.package import PackageSummary, Package
from app.services.tape_parser import parse_loan_tape

router = APIRouter(tags=["packages"])


@router.get("/packages", response_model=list[PackageSummary])
def get_packages(conn=Depends(get_db)):
    return list_packages(conn)


@router.post("/packages/upload", response_model=Package)
async def upload_loan_tape(file: UploadFile):
    """Upload an Excel loan tape and return a parsed Package."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("xlsx", "xls"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Please upload .xlsx or .xls",
        )

    try:
        package = parse_loan_tape(file.file, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return package


@router.get("/packages/{package_id}", response_model=Package)
def get_package(package_id: str, conn=Depends(get_db)):
    return get_package_by_id(conn, package_id)
