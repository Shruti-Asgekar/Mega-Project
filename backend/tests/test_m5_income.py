"""
Unit Tests for Module 5 (Income and Bank Statement Analyzer).
"""

import pytest
from backend.app.core.contracts import FlagCode, Severity, Transaction
from backend.app.modules.m5_income import (
    analyze_bank_statement_and_income,
    parse_bank_transactions_from_csv
)

def test_income_mismatch_demo_scenario():
    # Demo Case 5: Slip Net Rs 70,000 vs Bank Salary Credits ~ Rs 50,000, 2 EMIs, 1 bounce
    transactions = [
        # Month 1 (May 2026)
        Transaction(date="05/05/2026", description="SALARY CREDIT FROM ACME CORP", debit=0.0, credit=50000.0, balance=60000.0),
        Transaction(date="10/05/2026", description="ACH D - HDFC HOME LOAN EMI", debit=12000.0, credit=0.0, balance=48000.0),
        Transaction(date="15/05/2026", description="NACH - BAJAJ FINSERV LOAN EMI", debit=5000.0, credit=0.0, balance=43000.0),

        # Month 2 (June 2026)
        Transaction(date="05/06/2026", description="SALARY CREDIT FROM ACME CORP", debit=0.0, credit=50000.0, balance=75000.0),
        Transaction(date="10/06/2026", description="ACH D - HDFC HOME LOAN EMI", debit=12000.0, credit=0.0, balance=63000.0),
        Transaction(date="15/06/2026", description="NACH - BAJAJ FINSERV LOAN EMI", debit=5000.0, credit=0.0, balance=58000.0),
        Transaction(date="20/06/2026", description="CHQ RET - INSUFFICIENT FUNDS ECS BOUNCE", debit=500.0, credit=0.0, balance=57500.0),
    ]

    slip_net = 70000.0
    flags, metrics = analyze_bank_statement_and_income(
        transactions=transactions,
        slip_net_salary=slip_net,
        employer="ACME CORP"
    )

    # 1. Income Mismatch: 70,000 vs 50,000 is 40% deviation -> RED
    inc_flags = [f for f in flags if f.code == FlagCode.INCOME_MISMATCH]
    assert len(inc_flags) == 1
    assert inc_flags[0].severity == Severity.RED
    assert metrics["deviation_pct"] == 40.0
    assert "40% higher" in inc_flags[0].details["message"]

    # 2. EMI Burden: Total EMI = 12000 + 5000 = 17000. On 70k income = 24.3% (normal < 40%)
    assert metrics["total_monthly_emi"] == 17000.0
    assert len(metrics["detected_emis"]) == 2

    # 3. Bounced Payments: 1 bounce -> AMBER
    bounce_flags = [f for f in flags if f.code == FlagCode.BOUNCED_PAYMENTS]
    assert len(bounce_flags) == 1
    assert bounce_flags[0].severity == Severity.AMBER
    assert metrics["bounced_count"] == 1

def test_csv_parser():
    csv_text = """Date,Description,Debit,Credit,Balance
01/04/2026,OPENING BALANCE,0,0,10000
05/04/2026,SALARY CREDIT,0,65000,75000
10/04/2026,EMI HDFC,15000,0,60000
"""
    txs = parse_bank_transactions_from_csv(csv_text)
    assert len(txs) == 3
    assert txs[1].credit == 65000.0
    assert txs[2].debit == 15000.0
