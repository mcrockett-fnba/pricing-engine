from fastapi import HTTPException

from app.models.package import PackageSummary, Package
from app.db.queries.loans import get_loans_by_package_id


def list_packages(conn) -> list[PackageSummary]:
    """List all available packages with summary stats."""
    query = """
        SELECT PackageID, Name, LoanCount, TotalUPB, PurchasePrice, PurchaseDate
        FROM Packages
        ORDER BY Name
    """
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()

    return [
        PackageSummary(
            package_id=row.PackageID,
            name=row.Name,
            loan_count=row.LoanCount,
            total_upb=row.TotalUPB,
            purchase_price=row.PurchasePrice,
            purchase_date=row.PurchaseDate,
        )
        for row in rows
    ]


def get_package_by_id(conn, package_id: str) -> Package:
    """Fetch a package with its associated loans."""
    query = """
        SELECT PackageID, Name, LoanCount, TotalUPB, PurchasePrice, PurchaseDate
        FROM Packages
        WHERE PackageID = ?
    """
    cursor = conn.cursor()
    cursor.execute(query, package_id)
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Package {package_id} not found")

    loans = get_loans_by_package_id(conn, package_id)

    return Package(
        package_id=row.PackageID,
        name=row.Name,
        loan_count=row.LoanCount,
        total_upb=row.TotalUPB,
        purchase_price=row.PurchasePrice,
        purchase_date=row.PurchaseDate,
        loans=loans,
    )
