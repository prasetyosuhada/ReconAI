"""Background reconciliation service for matching bank transactions."""

import logging
import uuid
from typing import Any

from app.agents.reconciliation import run_reconciliation_agent
from app.db.session import SessionLocal
from app.models.audit import AuditEvent
from app.models.journal import JournalEntry
from app.models.reconciliation import (
    BankStatementImport,
    BankTransaction,
    ReconciliationMatch,
)
from app.models.review import ReviewItem
from app.services.accounting import find_exact_reconciliation_matches

logger = logging.getLogger(__name__)


def execute_reconciliation_workflow(import_id: str | uuid.UUID) -> None:
    """Execute bank statement reconciliation workflow asynchronously.

    Steps:
    1. Fetch bank statement import and its unreconciled transactions.
    2. Fetch posted candidate journal entries from database.
    3. Run deterministic exact matching (tolerance, date window, vendor).
    4. Fall back to LLM Reconciliation Agent for fuzzy candidates.
    5. Save ReconciliationMatch records, create ReviewItems & AuditEvents.
    """
    logger.info("Starting reconciliation workflow for import ID: %s", import_id)
    import_uuid = uuid.UUID(import_id) if isinstance(import_id, str) else import_id

    db = SessionLocal()
    try:
        imp_record = (
            db.query(BankStatementImport)
            .filter(BankStatementImport.id == import_uuid)
            .first()
        )
        if not imp_record:
            logger.error("BankStatementImport %s not found in DB.", import_id)
            return

        imp_record.status = "matching_in_progress"
        db.commit()

        transactions = (
            db.query(BankTransaction)
            .filter(BankTransaction.bank_statement_import_id == import_uuid)
            .all()
        )

        posted_entries = (
            db.query(JournalEntry).filter(JournalEntry.status == "posted").all()
        )

        # Prepare candidate dictionary list for matching
        candidate_dicts: list[dict[str, Any]] = []
        for je in posted_entries:
            tot_deb = sum(float(line.debit_amount) for line in je.lines)
            tot_cred = sum(float(line.credit_amount) for line in je.lines)
            ac_list = [line.account.account_code for line in je.lines if line.account]
            candidate_dicts.append(
                {
                    "id": str(je.id),
                    "entry_date": je.entry_date,
                    "description": je.description,
                    "total_debit": tot_deb,
                    "total_credit": tot_cred,
                    "accounts": ac_list,
                }
            )

        matched_count = 0

        for tx in transactions:
            if tx.status == "matched":
                matched_count += 1
                continue

            tx_dict = {
                "id": str(tx.id),
                "transaction_date": tx.transaction_date,
                "description": tx.description,
                "amount": float(tx.amount),
                "currency": tx.currency,
            }

            # Step 1: Deterministic Exact Match
            exact_res = find_exact_reconciliation_matches(tx_dict, candidate_dicts)

            if exact_res.is_exact_match and exact_res.matched_entry_id:
                matched_je_id = uuid.UUID(exact_res.matched_entry_id)
                match = ReconciliationMatch(
                    id=uuid.uuid4(),
                    bank_transaction_id=tx.id,
                    journal_entry_id=matched_je_id,
                    match_type="exact",
                    status="accepted",
                    confidence_score=1.00,
                    amount_score=1.00,
                    date_score=1.00,
                    vendor_score=1.00,
                    rationale="Exact amount, date window, and vendor match.",
                )
                db.add(match)
                tx.status = "matched"
                matched_count += 1

                audit = AuditEvent(
                    event_type="reconciliation_match_accepted",
                    source_type="reconciliation_match",
                    source_id=match.id,
                    actor_type="agent",
                    actor_name="ReconciliationEngine",
                    input_snapshot={
                        "tx_id": str(tx.id),
                        "je_id": str(matched_je_id),
                    },
                    output_snapshot={
                        "match_type": "exact",
                        "confidence_score": 1.00,
                    },
                )
                db.add(audit)

            else:
                # Step 2: Agent Fuzzy Matching
                try:
                    agent_res = run_reconciliation_agent(tx_dict, candidate_dicts)
                    top_matches = agent_res.result.matches or []

                    if top_matches:
                        best_match = top_matches[0]
                        matched_je_id = uuid.UUID(best_match.journal_entry_id)
                        conf = best_match.confidence_score
                        is_high_conf = conf >= 0.85

                        match_status = "accepted" if is_high_conf else "proposed"
                        match_type = "fuzzy"

                        match = ReconciliationMatch(
                            id=uuid.uuid4(),
                            bank_transaction_id=tx.id,
                            journal_entry_id=matched_je_id,
                            match_type=match_type,
                            status=match_status,
                            confidence_score=conf,
                            amount_score=best_match.amount_score,
                            date_score=best_match.date_score,
                            vendor_score=best_match.vendor_score,
                            rationale=best_match.rationale,
                        )
                        db.add(match)

                        if is_high_conf:
                            tx.status = "matched"
                            matched_count += 1
                        else:
                            # Create ReviewItem for human verification
                            review = ReviewItem(
                                id=uuid.uuid4(),
                                review_type="reconciliation",
                                status="pending",
                                priority="normal",
                                source_type="bank_transaction",
                                source_id=tx.id,
                                title=f"Review Match: {tx.description}",
                                summary=(
                                    f"Agent proposed match for bank transaction "
                                    f"({tx.amount} IDR) with confidence {conf:.2f}."
                                ),
                                suggested_action="Approve or edit match.",
                                original_payload={
                                    "tx_id": str(tx.id),
                                    "proposed_je_id": str(matched_je_id),
                                    "confidence": conf,
                                    "rationale": best_match.rationale,
                                },
                            )
                            db.add(review)

                        audit = AuditEvent(
                            event_type="reconciliation_match_proposed",
                            source_type="reconciliation_match",
                            source_id=match.id,
                            actor_type="agent",
                            actor_name="ReconciliationAgent",
                            input_snapshot={"tx_id": str(tx.id)},
                            output_snapshot={
                                "status": match_status,
                                "confidence_score": conf,
                            },
                        )
                        db.add(audit)
                    else:
                        # No matches found by agent
                        review = ReviewItem(
                            id=uuid.uuid4(),
                            review_type="reconciliation",
                            status="pending",
                            priority="high",
                            source_type="bank_transaction",
                            source_id=tx.id,
                            title=f"Unmatched Bank TX: {tx.description}",
                            summary=f"No matching entry for {tx.amount} IDR.",
                            suggested_action="Create journal or match manually.",
                            original_payload=tx_dict,
                        )
                        db.add(review)

                except Exception as ex:
                    logger.error(
                        "Error running reconciliation agent for tx %s: %s",
                        tx.id,
                        str(ex),
                    )

        # Final import status
        if matched_count == len(transactions) and len(transactions) > 0:
            imp_record.status = "matched"
        elif matched_count > 0:
            imp_record.status = "partially_matched"
        else:
            imp_record.status = "imported"

        db.commit()
        logger.info(
            "Completed reconciliation for import %s: %d/%d matched.",
            import_id,
            matched_count,
            len(transactions),
        )

    except Exception as e:
        logger.error(
            "Error executing reconciliation workflow for import %s: %s",
            import_id,
            str(e),
            exc_info=True,
        )
        db.rollback()
        try:
            imp_record = (
                db.query(BankStatementImport)
                .filter(BankStatementImport.id == import_uuid)
                .first()
            )
            if imp_record:
                imp_record.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
