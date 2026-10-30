"""
Module 8: Plain-English Explanation Engine (Jinja2).
- Renders one plain-English sentence per flag code from templates
- Formats amounts in Indian currency with digit grouping (e.g. ₹70,000)
- Groups and sorts explanations by severity: red, amber, green
"""

import os
from pathlib import Path
from typing import List, Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape
from backend.app.core.contracts import Flag, FlagCode, Severity

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "explanations"

def format_inr(val: Any) -> str:
    """Formats numeric value into Indian rupee notation (e.g. ₹70,000 / ₹1,50,000)."""
    if val is None:
        return "₹0"
    try:
        num = int(round(float(val)))
    except Exception:
        return f"₹{val}"

    is_negative = num < 0
    s = str(abs(num))
    if len(s) <= 3:
        formatted = s
    else:
        last3 = s[-3:]
        remaining = s[:-3]
        parts = []
        while len(remaining) > 2:
            parts.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            parts.insert(0, remaining)
        formatted = f"{','.join(parts)},{last3}"

    return f"-₹{formatted}" if is_negative else f"₹{formatted}"

# Initialize Jinja2 environment with custom filter
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True
)
jinja_env.filters["inr"] = format_inr

def render_flag_explanation(flag: Flag) -> str:
    """
    Renders human-readable explanation string for a given Flag using its Jinja2 template.
    Falls back to detail message if template is unavailable.
    """
    template_name = f"{flag.code.value}.j2"
    try:
        template = jinja_env.get_template(template_name)
        rendered = template.render(
            details=flag.details or {},
            severity=flag.severity.value,
            code=flag.code.value
        ).strip()
        # Clean extra spaces
        return " ".join(rendered.split())
    except Exception as e:
        # Fall back to detail message or generic description
        if flag.details and "message" in flag.details:
            return flag.details["message"]
        return f"{flag.code.value.replace('_', ' ').capitalize()}."

def explain_flags(flags: List[Flag]) -> Dict[str, Any]:
    """
    Produces human-readable explanations for all flags and groups them by severity.
    Returns:
      {
        "red": [{"code": ..., "module": ..., "explanation": ..., "score_impact": ...}],
        "amber": [...],
        "green": [...],
        "total_flags": int
      }
    """
    grouped = {
        "red": [],
        "amber": [],
        "green": []
    }

    for f in flags:
        explanation = render_flag_explanation(f)
        item = {
            "code": f.code.value,
            "module": f.module,
            "severity": f.severity.value,
            "score_impact": f.score_impact,
            "explanation": explanation,
            "details": f.details or {},
            "document_id": f.document_id
        }
        if f.severity == Severity.RED:
            grouped["red"].append(item)
        elif f.severity == Severity.AMBER:
            grouped["amber"].append(item)
        else:
            grouped["green"].append(item)

    return {
        "red": grouped["red"],
        "amber": grouped["amber"],
        "green": grouped["green"],
        "total_flags": len(flags)
    }
