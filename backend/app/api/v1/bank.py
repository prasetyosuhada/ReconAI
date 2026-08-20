"""FastAPI Bank Statements API Router (CSV Import & Transactions)."""

import csv
import io
import logging
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.reconciliation import BankStatementImport, BankTransaction
from app.services.audit_service import log_event
from app.schemas.bank import (
    BankStatementImportListResponse,
    BankStatementImportResponse,
    BankTransactionListResponse,
    BankTransactionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bank-statements", tags=["Bank Statements"])
bank_router = APIRouter(prefix="/bank", tags=["Bank Statements"])

UPLOAD_STORAGE_DIR = Path("./storage/bank_imports")


def _get_bank_storage_dir() -> Path:
    UPLOAD_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_STORAGE_DIR


def _parse_date_string(date_str: str) -> date | None:
    """Parse date from common CSV date string formats."""
    d_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(d_str, fmt).date()
        except ValueError:
            continue
    return None


@router.post(
    "/import",
    response_model=BankStatementImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import bank statement CSV file",
)
@bank_router.post(
    "/upload-mock",
    response_model=BankStatementImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload mock bank statement CSV",
)
async def upload_bank_statement_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BankStatementImportResponse:
    """Upload and parse mock bank statement CSV file.

    Expected CSV header columns:
    - transaction_date, description, amount, currency, reference_number
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename.",
        )

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only CSV files are supported.",
        )

    content_bytes = await file.read()
    if not content_bytes or len(content_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded CSV file is empty.",
        )

    # Save CSV file to disk
    storage_dir = _get_bank_storage_dir()
    import_uuid = uuid.uuid4()
    safe_filename = f"{import_uuid}_{Path(file.filename).name}"
    stored_path = storage_dir / safe_filename

    with open(stored_path, "wb") as f:
        f.write(content_bytes)

    # Parse CSV content
    csv_text = content_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(csv_text))

    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file header is missing or invalid.",
        )

    # Normalize headers
    header_map: dict[str, str] = {}
    for raw_h in reader.fieldnames:
        norm_h = raw_h.strip().lower().replace(" ", "_")
        header_map[norm_h] = raw_h

    date_keys = ("transaction_date", "date", "tx_date", "tanggal")
    desc_keys = ("description", "desc", "keterangan", "memo", "details")
    amount_keys = ("amount", "jumlah", "value", "total")
    curr_keys = ("currency", "mata_uang")
    ref_keys = ("reference_number", "ref", "no_ref", "reference")

    date_col = next((header_map[h] for h in date_keys if h in header_map), None)
    desc_col = next((header_map[h] for h in desc_keys if h in header_map), None)
    amount_col = next((header_map[h] for h in amount_keys if h in header_map), None)
    currency_col = next((header_map[h] for h in curr_keys if h in header_map), None)
    ref_col = next((header_map[h] for h in ref_keys if h in header_map), None)

    if not date_col or not desc_col or not amount_col:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV missing required headers: date, description, amount.",
        )

    tx_objects: list[BankTransaction] = []
    now_utc = datetime.now(UTC)

    for idx, row in enumerate(reader, start=1):
        raw_date = row.get(date_col, "")
        raw_desc = row.get(desc_col, "")
        raw_amt = row.get(amount_col, "")

        if not raw_date or not raw_desc or not raw_amt:
            continue

        tx_date = _parse_date_string(raw_date)
        if not tx_date:
            logger.warning(
                "Row #%d: Could not parse date '%s', skipping.", idx, raw_date
            )
            continue

        try:
            amt_clean = raw_amt.replace(",", "").strip()
            amt_float = float(amt_clean)
        except ValueError:
            logger.warning(
                "Row #%d: Could not parse amount '%s', skipping.", idx, raw_amt
            )
            continue

        curr = row.get(currency_col, "IDR").strip() if currency_col else "IDR"
        ref_num = row.get(ref_col, "").strip() if ref_col else None

        tx = BankTransaction(
            id=uuid.uuid4(),
            bank_statement_import_id=import_uuid,
            transaction_date=tx_date,
            description=raw_desc.strip(),
            amount=amt_float,
            currency=curr or "IDR",
            reference_number=ref_num or None,
            status="imported",
        )
        tx_objects.append(tx)

    if not tx_objects:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid bank transactions could be parsed from CSV file.",
        )

    # Save Import Record & Transactions to DB
    import_record = BankStatementImport(
        id=import_uuid,
        original_filename=file.filename,
        stored_file_path=str(stored_path.resolve()),
        status="imported",
        row_count=len(tx_objects),
        imported_at=now_utc,
    )
    db.add(import_record)
    db.add_all(tx_objects)

    # Audit Trail Event
    log_event(
        db=db,
        event_type="bank_statement_imported",
        source_type="bank_statement_import",
        source_id=import_uuid,
        actor_type="human",
        actor_name="api_user",
        input_snapshot={
            "original_filename": file.filename,
            "row_count": len(tx_objects),
        },
        output_snapshot={"status": "imported", "row_count": len(tx_objects)},
    )
    db.commit()

    self_tx_link = f"{settings.API_V1_STR}/bank-statements/{import_uuid}/transactions"
    recon_link = f"{settings.API_V1_STR}/reconciliation/run"

    return BankStatementImportResponse(
        id=import_record.id,
        original_filename=import_record.original_filename,
        status=import_record.status,
        row_count=import_record.row_count,
        imported_at=import_record.imported_at,
        links={
            "transactions": self_tx_link,
            "run_reconciliation": recon_link,
        },
    )


@router.get(
    "",
    response_model=BankStatementImportListResponse,
    status_code=status.HTTP_200_OK,
    summary="List bank statement imports",
)
def list_bank_statement_imports(
    limit: int = Query(50, ge=1, le=250, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> BankStatementImportListResponse:
    """Fetch paginated bank statement import records."""
    query = db.query(BankStatementImport)
    total_count = query.with_entities(func.count(BankStatementImport.id)).scalar() or 0

    items = (
        query.order_by(BankStatementImport.imported_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return BankStatementImportListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{bank_statement_import_id}/transactions",
    response_model=BankTransactionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List transactions for a bank statement import",
)
def list_bank_statement_transactions(
    bank_statement_import_id: str,
    limit: int = Query(50, ge=1, le=250, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> BankTransactionListResponse:
    """Fetch paginated bank transactions for a specific import."""
    try:
        import_uuid = uuid.UUID(bank_statement_import_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bank statement import UUID format.",
        ) from None

    query = db.query(BankTransaction).filter(
        BankTransaction.bank_statement_import_id == import_uuid
    )
    total_count = query.with_entities(func.count(BankTransaction.id)).scalar() or 0

    items = (
        query.order_by(BankTransaction.transaction_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return BankTransactionListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/transactions/{transaction_id}",
    response_model=BankTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single bank transaction by ID",
)
@bank_router.get(
    "/transactions/{transaction_id}",
    response_model=BankTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single bank transaction by ID",
)
def get_bank_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
) -> BankTransactionResponse:
    """Fetch single bank transaction by UUID."""
    try:
        tx_uuid = uuid.UUID(transaction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bank transaction UUID format.",
        ) from None

    tx = db.query(BankTransaction).filter(BankTransaction.id == tx_uuid).first()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bank transaction [{transaction_id}] not found.",
        )
    return tx

