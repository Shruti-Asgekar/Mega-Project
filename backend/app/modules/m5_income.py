"""
Module 5: Income and Bank Statement Analyzer (Backend).
- Calculates average monthly credits and salary credits
- Detects recurring EMIs (>= 2 distinct months) and computes EMI burden ratio
- Detects bounced payments (returns, insufficient funds, ECS/NACH failures)
- Cross-verifies Salary Slip Net vs Bank Statement Salary Credits
"""

import re
import csv
import io
from collections import defaultdict
from typing import List, Dict, Any, Optional
from backend.app.core.contracts import Flag, FlagCode, Severity, Transaction

EMI_REGEX = re.compile(r"\b(EMI|LOAN|ECS|NACH|ACH\s?D)\b", re.IGNORECASE)
BOUNCE_REGEX = re.compile(r"\b(BOUNCE|RETURN|INSUFFICIENT|CHQ\s?RET|ECS\s?RETURN|NACH\s?RETURN)\b", re.IGNORECASE)
SALARY_KEYWORDS_REGEX = re.compile(r"\b(SALARY|SAL|NEFT|PAYROLL|CMS)\b", re.IGNORECASE)

def parse_bank_transactions_from_csv(csv_content: str) -> List[Transaction]:
    """Parses standard bank statement CSV into Transaction objects."""
    transactions = []
    reader = csv.DictReader(io.StringIO(csv_content))
    for row in reader:
        date_val = row.get("Date") or row.get("date") or ""
        desc = row.get("Description") or row.get("narration") or row.get("Narration") or ""
        debit = float(row.get("Debit") or row.get("debit") or 0.0)
        credit = float(row.get("Credit") or row.get("credit") or 0.0)
        balance = float(row.get("Balance") or row.get("balance") or 0.0)
        transactions.append(
            Transaction(
                date=date_val.strip(),
                description=desc.strip(),
                debit=debit,
                credit=credit,
                balance=balance
            )
        )
    return transactions

def extract_month_key(date_str: str) -> str:
    """Extracts YYYY-MM from date string (handles DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY)."""
    cleaned = date_str.strip()
    match_iso = re.match(r"^(\d{4})-(\d{2})", cleaned)
    if match_iso:
        return f"{match_iso.group(1)}-{match_iso.group(2)}"
    match_dmy = re.match(r"^\d{1,2}[/-](\d{1,2})[/-](\d{4})", cleaned)
    if match_dmy:
        month = int(match_dmy.group(1))
        year = int(match_dmy.group(2))
        return f"{year:04d}-{month:02d}"
    return "UNKNOWN"

def analyze_bank_statement_and_income(
    transactions: List[Transaction],
    slip_net_salary: Optional[float] = None,
    employer: Optional[str] = None
) -> tuple[List[Flag], Dict[str, Any]]:
    """
    Analyzes transactions and compares with declared slip net income.
    Returns:
        flags: list of Flag objects
        metrics: summary dictionary for UI metrics table
    """
    flags: List[Flag] = []

    # 1. Group credits and debits by month
    monthly_credits = defaultdict(float)
    monthly_salary_credits = defaultdict(float)
    emi_debit_candidates = defaultdict(lambda: defaultdict(list)) # month -> amount -> list of desc
    bounced_transactions = []

    employer_pattern = re.compile(re.escape(employer.strip()), re.IGNORECASE) if employer else None

    for tx in transactions:
        m_key = extract_month_key(tx.date)
        desc = tx.description

        # Check Bounced
        if BOUNCE_REGEX.search(desc):
            bounced_transactions.append(tx)

        # Credits
        if tx.credit > 0:
            monthly_credits[m_key] += tx.credit
            is_salary = bool(SALARY_KEYWORDS_REGEX.search(desc))
            if employer_pattern and employer_pattern.search(desc):
                is_salary = True
            if is_salary:
                monthly_salary_credits[m_key] += tx.credit

        # Debits for EMI
        if tx.debit > 0 and EMI_REGEX.search(desc):
            # bucket amount rounded to nearest 100 for small variance
            amount_bucket = round(tx.debit, -2)
            emi_debit_candidates[amount_bucket][m_key].append(tx.debit)

    # Calculate active months
    active_months = [m for m in monthly_credits.keys() if m != "UNKNOWN"]
    num_months = max(len(active_months), 1)

    avg_monthly_credits = round(sum(monthly_credits.values()) / num_months, 2)
    avg_salary_credits = round(sum(monthly_salary_credits.values()) / num_months, 2)

    # 2. Recurring EMI detection (recurs in >= 2 distinct months)
    total_monthly_emi = 0.0
    detected_emis = []
    for amount_bucket, months_map in emi_debit_candidates.items():
        if len(months_map) >= 2:
            # Consistent EMI detected
            avg_amount = sum(sum(vals) for vals in months_map.values()) / sum(len(vals) for vals in months_map.values())
            total_monthly_emi += avg_amount
            detected_emis.append({
                "estimated_emi": round(avg_amount, 2),
                "months_observed": len(months_map)
            })

    total_monthly_emi = round(total_monthly_emi, 2)

    # 3. Income Mismatch check (Slip Net vs Average Salary Credits)
    declared_income = slip_net_salary or avg_salary_credits or 0.0
    deviation_pct = 0.0

    if slip_net_salary and avg_salary_credits > 0:
        diff = slip_net_salary - avg_salary_credits
        deviation_pct = round((abs(diff) / avg_salary_credits) * 100, 1)

        if deviation_pct > 25.0:
            pct_int = int(round(deviation_pct))
            slip_fmt = f"₹{int(slip_net_salary):,}"
            bank_fmt = f"₹{int(avg_salary_credits):,}"
            comparison = "higher" if slip_net_salary > avg_salary_credits else "lower"
            flags.append(
                Flag(
                    code=FlagCode.INCOME_MISMATCH,
                    module=5,
                    severity=Severity.RED,
                    score_impact=20,
                    details={
                        "slip_net": slip_net_salary,
                        "avg_salary_credits": avg_salary_credits,
                        "deviation_pct": deviation_pct,
                        "message": f"Salary slip net income {slip_fmt} is {pct_int}% {comparison} than average bank salary credits of {bank_fmt}."
                    }
                )
            )
        elif 15.0 < deviation_pct <= 25.0:
            flags.append(
                Flag(
                    code=FlagCode.INCOME_MISMATCH,
                    module=5,
                    severity=Severity.AMBER,
                    score_impact=8,
                    details={
                        "slip_net": slip_net_salary,
                        "avg_salary_credits": avg_salary_credits,
                        "deviation_pct": deviation_pct,
                        "message": f"Moderate income deviation of {deviation_pct}% between salary slip and bank credits."
                    }
                )
            )
        else:
            flags.append(
                Flag(
                    code=FlagCode.INCOME_VERIFIED,
                    module=5,
                    severity=Severity.GREEN,
                    score_impact=0,
                    details={
                        "slip_net": slip_net_salary,
                        "avg_salary_credits": avg_salary_credits,
                        "deviation_pct": deviation_pct
                    }
                )
            )

    # 4. EMI Burden Check
    emi_burden_pct = round((total_monthly_emi / declared_income * 100), 1) if declared_income > 0 else 0.0
    if emi_burden_pct > 60.0:
        flags.append(
            Flag(
                code=FlagCode.EMI_BURDEN_HIGH,
                module=5,
                severity=Severity.RED,
                score_impact=20,
                details={
                    "total_monthly_emi": total_monthly_emi,
                    "declared_income": declared_income,
                    "burden_pct": emi_burden_pct,
                    "message": f"Critical EMI burden of {emi_burden_pct}% exceeding 60% threshold."
                }
            )
        )
    elif 40.0 < emi_burden_pct <= 60.0:
        flags.append(
            Flag(
                code=FlagCode.EMI_BURDEN_HIGH,
                module=5,
                severity=Severity.AMBER,
                score_impact=8,
                details={
                    "total_monthly_emi": total_monthly_emi,
                    "declared_income": declared_income,
                    "burden_pct": emi_burden_pct,
                    "message": f"Elevated EMI burden of {emi_burden_pct}% (threshold: 40%)."
                }
            )
        )
    else:
        flags.append(
            Flag(
                code=FlagCode.EMI_BURDEN_NORMAL,
                module=5,
                severity=Severity.GREEN,
                score_impact=0,
                details={"total_monthly_emi": total_monthly_emi, "burden_pct": emi_burden_pct}
            )
        )

    # 5. Bounced Payments Check
    bounced_count = len(bounced_transactions)
    if bounced_count >= 2:
        flags.append(
            Flag(
                code=FlagCode.BOUNCED_PAYMENTS,
                module=5,
                severity=Severity.RED,
                score_impact=min(bounced_count * 6, 18),
                details={
                    "count": bounced_count,
                    "message": f"Detected {bounced_count} bounced/returned payment transactions."
                }
            )
        )
    elif bounced_count == 1:
        flags.append(
            Flag(
                code=FlagCode.BOUNCED_PAYMENTS,
                module=5,
                severity=Severity.AMBER,
                score_impact=6,
                details={
                    "count": 1,
                    "message": "Detected 1 bounced transaction in bank statement."
                }
            )
        )
    else:
        flags.append(
            Flag(
                code=FlagCode.NO_BOUNCED_PAYMENTS,
                module=5,
                severity=Severity.GREEN,
                score_impact=0,
                details={"count": 0}
            )
        )

    metrics = {
        "avg_monthly_credits": avg_monthly_credits,
        "avg_salary_credits": avg_salary_credits,
        "slip_net_salary": slip_net_salary or 0.0,
        "deviation_pct": deviation_pct,
        "total_monthly_emi": total_monthly_emi,
        "emi_burden_pct": emi_burden_pct,
        "bounced_count": bounced_count,
        "active_months_count": num_months,
        "detected_emis": detected_emis
    }

    return flags, metrics
