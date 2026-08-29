import logging

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.coa import ChartOfAccount

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INITIAL_COA = [
    {
        "account_code": "1000",
        "account_name": "Cash",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": True,
        "description": "Physical cash on hand.",
    },
    {
        "account_code": "1010",
        "account_name": "Bank Account",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": True,
        "description": "Primary operating bank account.",
    },
    {
        "account_code": "1100",
        "account_name": "Accounts Receivable",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Amounts owed by customers for invoices.",
    },
    {
        "account_code": "1200",
        "account_name": "Inventory",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Goods held for sale.",
    },
    {
        "account_code": "1300",
        "account_name": "Prepaid Expenses",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Payments made in advance for services/goods.",
    },
    {
        "account_code": "1400",
        "account_name": "Input VAT",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Recoverable input VAT/PPN paid to vendors on purchases.",
    },
    {
        "account_code": "2000",
        "account_name": "Accounts Payable",
        "account_type": "liability",
        "normal_balance": "credit",
        "is_sensitive": False,
        "description": "Amounts owed to vendors and suppliers.",
    },
    {
        "account_code": "2100",
        "account_name": "Tax Payable",
        "account_type": "liability",
        "normal_balance": "credit",
        "is_sensitive": True,
        "description": "Taxes collected or accrued payable to government.",
    },
    {
        "account_code": "2200",
        "account_name": "Loans Payable",
        "account_type": "liability",
        "normal_balance": "credit",
        "is_sensitive": True,
        "description": "Outstanding principal on business loans.",
    },
    {
        "account_code": "3000",
        "account_name": "Owner Equity",
        "account_type": "equity",
        "normal_balance": "credit",
        "is_sensitive": True,
        "description": "Owner capital and retained earnings.",
    },
    {
        "account_code": "4000",
        "account_name": "Sales Revenue",
        "account_type": "revenue",
        "normal_balance": "credit",
        "is_sensitive": False,
        "description": "Income earned from sales of products or services.",
    },
    {
        "account_code": "5000",
        "account_name": "Cost of Goods Sold",
        "account_type": "expense",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Direct costs attributable to production/purchases.",
    },
    {
        "account_code": "5100",
        "account_name": "Office Supplies Expense",
        "account_type": "expense",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Expenditures for office stationery and consumables.",
    },
    {
        "account_code": "5200",
        "account_name": "Meals and Entertainment Expense",
        "account_type": "expense",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Business meals and client entertainment costs.",
    },
    {
        "account_code": "5300",
        "account_name": "Travel Expense",
        "account_type": "expense",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Lodging, transport, and travel-related costs.",
    },
    {
        "account_code": "5400",
        "account_name": "Software Subscription Expense",
        "account_type": "expense",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "SaaS software licenses and digital tools.",
    },
    {
        "account_code": "5900",
        "account_name": "Miscellaneous Expense",
        "account_type": "expense",
        "normal_balance": "debit",
        "is_sensitive": False,
        "description": "Other general operational expenses.",
    },
    {
        "account_code": "9999",
        "account_name": "Suspense Account",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": True,
        "description": "Temporary holding account for unclassified transactions.",
    },
]


def seed_chart_of_accounts(db: Session) -> None:
    """Seed initial Chart of Accounts idempotently."""
    logger.info("Seeding Chart of Accounts...")
    created_count = 0
    updated_count = 0

    for coa_data in INITIAL_COA:
        existing = (
            db.query(ChartOfAccount)
            .filter(ChartOfAccount.account_code == coa_data["account_code"])
            .first()
        )
        if not existing:
            account = ChartOfAccount(**coa_data)
            db.add(account)
            created_count += 1
        else:
            existing.account_name = coa_data["account_name"]
            existing.account_type = coa_data["account_type"]
            existing.normal_balance = coa_data["normal_balance"]
            existing.is_sensitive = coa_data["is_sensitive"]
            existing.description = coa_data["description"]
            updated_count += 1

    db.commit()
    logger.info(
        f"Seeding COA completed. Created: {created_count}, Updated: {updated_count}"
    )


def main() -> None:
    db = SessionLocal()
    try:
        seed_chart_of_accounts(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
