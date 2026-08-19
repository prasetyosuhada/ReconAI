import json
import logging
import uuid
from collections.abc import Generator
from typing import Any

from app.agents.bookkeeping import run_bookkeeping_agent
from app.agents.reconciliation import run_reconciliation_agent
from app.db.session import SessionLocal
from app.models.adjustment_suggestion import AdjustmentSuggestion
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.journal import JournalEntry
from app.models.reconciliation import (
    BankStatementImport,
    BankTransaction,
    ReconciliationMatch,
)
from app.models.review import ReviewItem
from app.services.accounting import find_exact_reconciliation_matches

logger = logging.getLogger(__name__)


def stream_reconciliation_workflow(
    import_id: str | uuid.UUID,
) -> Generator[str, None, None]:
    """Execute bank statement reconciliation workflow and yield real-time SSE events."""
    logger.info("Starting streaming reconciliation workflow for import ID: %s", import_id)
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
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Bank statement import [{import_id}] not found.'})}\n\n"
            return

        imp_record.status = "matching_in_progress"
        db.commit()

        yield f"data: {json.dumps({'stage': 'init', 'message': 'Reconciliation Engine initialized. Fetching statement records...', 'percentage': 5})}\n\n"

        transactions = (
            db.query(BankTransaction)
            .filter(BankTransaction.bank_statement_import_id == import_uuid)
            .all()
        )

        posted_entries = (
            db.query(JournalEntry).filter(JournalEntry.status == "posted").all()
        )

        # Load active COA once — shared across BookkeepingAgent calls for unmatched txs
        coa_rows = (
            db.query(ChartOfAccount)
            .filter(ChartOfAccount.is_active == True)  # noqa: E712
            .order_by(ChartOfAccount.account_code)
            .all()
        )
        coa_list = [
            {
                "account_code": c.account_code,
                "account_name": c.account_name,
                "account_type": c.account_type,
                "normal_balance": c.normal_balance,
                "is_sensitive": c.is_sensitive,
                "description": c.description,
            }
            for c in coa_rows
        ]

        total_tx = len(transactions)
        yield f"data: {json.dumps({'stage': 'candidates_loaded', 'message': f'Loaded {len(posted_entries)} posted GL entries and {total_tx} bank transactions.', 'total': total_tx, 'percentage': 10})}\n\n"

        # Prepare candidate dictionary list for matching
        candidate_dicts: list[dict[str, Any]] = []
        for je in posted_entries:
            tot_deb = sum(float(line.debit_amount) for line in je.lines)
            tot_cred = sum(float(line.credit_amount) for line in je.lines)
            ac_list = [line.account.account_code for line in je.lines if line.account]
            candidate_dicts.append(
                {
                    "id": str(je.id),
                    "entry_date": (
                        je.entry_date.isoformat()
                        if hasattr(je.entry_date, "isoformat")
                        else str(je.entry_date)
                    ),
                    "description": je.description,
                    "total_debit": tot_deb,
                    "total_credit": tot_cred,
                    "accounts": ac_list,
                }
            )

        matched_count = 0
        proposed_count = 0
        unmatched_count = 0

        for idx, tx in enumerate(transactions, start=1):
            pct = 10 + int((idx / total_tx) * 85) if total_tx > 0 else 95

            if tx.status == "matched":
                matched_count += 1
                yield f"data: {json.dumps({'stage': 'already_matched', 'tx_id': str(tx.id), 'description': tx.description, 'amount': float(tx.amount), 'current': idx, 'total': total_tx, 'matched_count': matched_count, 'percentage': pct, 'message': f'#{idx}: {tx.description} is already reconciled.'})}\n\n"
                continue

            tx_dict = {
                "id": str(tx.id),
                "transaction_date": (
                    tx.transaction_date.isoformat()
                    if hasattr(tx.transaction_date, "isoformat")
                    else str(tx.transaction_date)
                ),
                "description": tx.description,
                "amount": float(tx.amount),
                "currency": tx.currency,
            }

            yield f"data: {json.dumps({'stage': 'evaluating', 'tx_id': str(tx.id), 'description': tx.description, 'amount': float(tx.amount), 'current': idx, 'total': total_tx, 'matched_count': matched_count, 'percentage': pct, 'message': f'Evaluating #{idx}/{total_tx}: {tx.description} (Rp{abs(tx.amount):,.0f}) via Exact Matching...' })}\n\n"

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
                db.commit()

                yield f"data: {json.dumps({'stage': 'exact_match_found', 'tx_id': str(tx.id), 'matched_je_id': str(matched_je_id), 'confidence': 1.0, 'matched_count': matched_count, 'current': idx, 'total': total_tx, 'percentage': pct, 'message': f'✓ Exact Match (100%) for {tx.description} with #JE-{str(matched_je_id)[:8]}'})}\n\n"

            else:
                # Step 2: Agent Fuzzy Matching
                yield f"data: {json.dumps({'stage': 'agent_invoked', 'tx_id': str(tx.id), 'description': tx.description, 'current': idx, 'total': total_tx, 'percentage': pct, 'message': f'No exact match. Invoking AI Reconciliation Agent for {tx.description}...' })}\n\n"

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
                            proposed_count += 1
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
                                    "transaction_date": str(tx.transaction_date),
                                    "amount": float(tx.amount),
                                    "description": tx.description,
                                    "currency": tx.currency or "IDR",
                                    "reference_number": tx.reference_number,
                                    "proposed_journal_entry_id": str(matched_je_id),
                                    "confidence_score": conf,
                                    "amount_score": best_match.amount_score,
                                    "date_score": best_match.date_score,
                                    "vendor_score": best_match.vendor_score,
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
                        db.commit()

                        if is_high_conf:
                            yield f"data: {json.dumps({'stage': 'agent_match_accepted', 'tx_id': str(tx.id), 'matched_je_id': str(matched_je_id), 'confidence': conf, 'matched_count': matched_count, 'current': idx, 'total': total_tx, 'percentage': pct, 'message': f'✨ AI Agent matched {tx.description} with #JE-{str(matched_je_id)[:8]} ({int(conf*100)}% conf)'})}\n\n"
                        else:
                            yield f"data: {json.dumps({'stage': 'review_queued', 'tx_id': str(tx.id), 'matched_je_id': str(matched_je_id), 'confidence': conf, 'proposed_count': proposed_count, 'current': idx, 'total': total_tx, 'percentage': pct, 'message': f'⚠️ AI Agent proposed match for {tx.description} ({int(conf*100)}% conf). Queued for Human Review.'})}\n\n"

                    else:
                        unmatched_count += 1
                        # No matches found by agent — save to ReviewItem
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
                        db.commit()

                        yield f"data: {json.dumps({'stage': 'unmatched_queued', 'tx_id': str(tx.id), 'unmatched_count': unmatched_count, 'current': idx, 'total': total_tx, 'percentage': pct, 'message': f'✕ No matching GL entry for {tx.description}. Marked as Bank Only.'})}\n\n"

                        # --- BookkeepingAgent: classify the unmatched tx & save to DB ---
                        yield f"data: {json.dumps({'stage': 'bookkeeping_classifying', 'tx_id': str(tx.id), 'message': f'🤖 BookkeepingAgent classifying {tx.description} for COA suggestion...'})}\n\n"

                        try:
                            raw_amount = float(tx.amount)
                            abs_amount = abs(raw_amount)
                            tx_direction = (
                                "DEBIT (outflow / expense / payment)"
                                if raw_amount < 0
                                else "CREDIT (inflow / revenue / receipt)"
                            )

                            bk_extraction = {
                                "vendor_name": tx.description,
                                "transaction_date": str(tx.transaction_date),
                                "total_amount": abs_amount,
                                "currency": tx.currency,
                                "document_type": "bank_transaction",
                                "line_items": [],
                                "extraction_notes": (
                                    f"Unmatched bank statement mutation: '{tx.description}'. "
                                    f"Ref: {tx.reference_number or 'N/A'}. "
                                    f"Transaction direction: {tx_direction}. "
                                    f"Original signed amount: {raw_amount:,.2f} {tx.currency}. "
                                    "Please classify to the most appropriate account and "
                                    "generate a balanced journal entry."
                                ),
                            }

                            bk_resp = run_bookkeeping_agent(
                                extraction_data=bk_extraction,
                                chart_of_accounts=coa_list,
                            )

                            # Upsert: delete existing suggestion first, then insert
                            db.query(AdjustmentSuggestion).filter(
                                AdjustmentSuggestion.bank_transaction_id == tx.id
                            ).delete(synchronize_session=False)

                            suggestion = AdjustmentSuggestion(
                                id=uuid.uuid4(),
                                bank_transaction_id=tx.id,
                                confidence_score=bk_resp.confidence_score,
                                rationale=bk_resp.rationale,
                                is_balanced=bk_resp.result.is_balanced,
                                uses_sensitive_account=bk_resp.result.uses_sensitive_account,
                                risk_flags=list(bk_resp.result.risk_flags or []),
                                suggested_lines=[
                                    {
                                        "account_code": line.account_code,
                                        "account_name": line.account_name,
                                        "description": line.description,
                                        "debit_amount": line.debit_amount,
                                        "credit_amount": line.credit_amount,
                                    }
                                    for line in bk_resp.result.journal_lines
                                ],
                                agent_name=bk_resp.agent_name,
                            )
                            db.add(suggestion)
                            db.commit()

                            yield f"data: {json.dumps({'stage': 'bookkeeping_suggestion_saved', 'tx_id': str(tx.id), 'confidence': bk_resp.confidence_score, 'message': f'💡 COA suggestion saved for {tx.description} (confidence {int(bk_resp.confidence_score * 100)}%).'})}\n\n"

                        except Exception as bk_err:
                            logger.warning(
                                "BookkeepingAgent failed for unmatched tx [%s]: %s",
                                tx.id,
                                str(bk_err),
                            )
                            db.rollback()
                            yield f"data: {json.dumps({'stage': 'bookkeeping_suggestion_failed', 'tx_id': str(tx.id), 'message': f'⚠️ COA suggestion failed for {tx.description}: {str(bk_err)[:80]}'})}\n\n"


                except Exception as ex:
                    logger.error(
                        "Error running reconciliation agent for tx %s: %s",
                        tx.id,
                        str(ex),
                    )
                    yield f"data: {json.dumps({'stage': 'agent_error', 'tx_id': str(tx.id), 'message': f'Agent error for {tx.description}: {str(ex)}'})}\n\n"

        # Final import status
        if matched_count == len(transactions) and len(transactions) > 0:
            imp_record.status = "matched"
        elif matched_count > 0:
            imp_record.status = "partially_matched"
        else:
            imp_record.status = "imported"

        db.commit()
        yield f"data: {json.dumps({'stage': 'completed', 'matched_count': matched_count, 'proposed_count': proposed_count, 'unmatched_count': unmatched_count, 'total_count': total_tx, 'percentage': 100, 'message': f'🎉 Reconciliation Run Complete! {matched_count}/{total_tx} matched, {proposed_count} review required.'})}\n\n"

    except Exception as e:
        logger.error(
            "Error executing reconciliation workflow for import %s: %s",
            import_id,
            str(e),
            exc_info=True,
        )
        db.rollback()
        yield f"data: {json.dumps({'stage': 'error', 'message': f'Execution failed: {str(e)}'})}\n\n"
    finally:
        db.close()


def execute_reconciliation_workflow(import_id: str | uuid.UUID) -> None:
    """Execute background reconciliation by consuming the stream generator."""
    for _ in stream_reconciliation_workflow(import_id):
        pass

