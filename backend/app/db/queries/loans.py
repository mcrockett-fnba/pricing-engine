from app.models.loan import Loan

# Map Pydantic field names to SQL column names.
# Update these values once the actual SQL Server schema is confirmed.
COLUMN_MAP = {
    "loan_id": "LoanID",
    "unpaid_balance": "UnpaidBalance",
    "interest_rate": "InterestRate",
    "original_term": "OriginalTerm",
    "remaining_term": "RemainingTerm",
    "loan_age": "LoanAge",
    "credit_score": "CreditScore",
    "ltv": "LTV",
    "dti": "DTI",
    "property_type": "PropertyType",
    "occupancy_type": "OccupancyType",
    "state": "State",
    "origination_date": "OriginationDate",
}

_SQL_COLUMNS = ", ".join(COLUMN_MAP.values())


def get_loans_by_package_id(conn, package_id: str) -> list[Loan]:
    """Fetch all loans belonging to a package."""
    query = f"""
        SELECT {_SQL_COLUMNS}
        FROM Loans
        WHERE PackageID = ?
    """
    cursor = conn.cursor()
    cursor.execute(query, package_id)
    rows = cursor.fetchall()

    reverse_map = {v: k for k, v in COLUMN_MAP.items()}
    columns = [reverse_map.get(desc[0], desc[0]) for desc in cursor.description]

    loans = []
    for row in rows:
        data = dict(zip(columns, row))
        loans.append(Loan(**data))
    return loans
