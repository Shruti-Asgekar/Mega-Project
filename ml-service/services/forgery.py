"""
Module 6: Forgery Detection Lite (ml-service).
- pikepdf metadata analysis: detects editing software keywords, modified-after-created, missing metadata
- Salary slip arithmetic verification (gross - deductions == net; component breakdown checks)
- Error Level Analysis (ELA) for image forgery detection and heatmap generation
"""

import io
import os
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
import numpy as np
import cv2
from PIL import Image
import pikepdf
from backend.app.core.contracts import Flag, FlagCode, Severity

EDITING_SOFTWARE_KEYWORDS = [
    "photoshop", "illustrator", "gimp", "canva", "pixlr",
    "foxit", "smallpdf", "ilovepdf", "sejda", "nitro", "pdf-xchange"
]

def parse_pdf_date(date_str: Any) -> Optional[datetime]:
    """Parses PDF timestamp into datetime."""
    if not date_str:
        return None
    s = str(date_str).strip()
    if s.startswith("D:"):
        s = s[2:]
    s = s.replace("'", "")
    match = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})?", s)
    if match:
        y, m, d, hh, mm = [int(x) for x in match.groups()[:5]]
        ss = int(match.group(6)) if match.group(6) else 0
        return datetime(y, m, d, hh, mm, ss)
    try:
        return datetime.fromisoformat(s[:19])
    except Exception:
        return None

def analyze_pdf_metadata(file_bytes: bytes, document_id: Optional[str] = None) -> List[Flag]:
    """
    Scans PDF Producer, Creator, ModDate, CreationDate, and XMP metadata.
    """
    flags: List[Flag] = []
    try:
        with pikepdf.open(io.BytesIO(file_bytes)) as pdf:
            docinfo = pdf.docinfo
            producer = str(docinfo.get(pikepdf.Name("/Producer"), "")).lower()
            creator = str(docinfo.get(pikepdf.Name("/Creator"), "")).lower()

            # Also check XMP
            xmp_text = ""
            try:
                if "/Metadata" in pdf.Root:
                    xmp_bytes = pdf.Root["/Metadata"].read_bytes()
                    xmp_text = xmp_bytes.decode("utf-8", errors="ignore").lower()
            except Exception:
                pass

            combined_meta = f"{producer} {creator} {xmp_text}"

            # 1. Check for editing software
            detected_software = []
            for kw in EDITING_SOFTWARE_KEYWORDS:
                if kw in combined_meta:
                    detected_software.append(kw)

            if detected_software:
                sw_str = ", ".join(detected_software)
                flags.append(
                    Flag(
                        code=FlagCode.META_EDITING_SOFTWARE,
                        module=6,
                        severity=Severity.RED,
                        score_impact=35,
                        details={
                            "detected_keywords": detected_software,
                            "producer": producer,
                            "creator": creator,
                            "message": f"Document metadata indicates editing software used: {sw_str}"
                        },
                        document_id=document_id
                    )
                )

            # 2. Check ModDate vs CreationDate
            creation_str = docinfo.get(pikepdf.Name("/CreationDate"), None)
            mod_str = docinfo.get(pikepdf.Name("/ModDate"), None)

            c_date = parse_pdf_date(creation_str)
            m_date = parse_pdf_date(mod_str)

            if c_date and m_date:
                diff_seconds = (m_date - c_date).total_seconds()
                if diff_seconds > 60: # modified after created + 1 min
                    flags.append(
                        Flag(
                            code=FlagCode.META_MODIFIED_AFTER_CREATED,
                            module=6,
                            severity=Severity.AMBER,
                            score_impact=8,
                            details={
                                "creation_date": str(c_date),
                                "mod_date": str(m_date),
                                "diff_seconds": diff_seconds,
                                "message": f"Document modified {int(diff_seconds // 60)} minutes after initial creation."
                            },
                            document_id=document_id
                        )
                    )

            # 3. Check for missing metadata
            if not producer and not creator and not c_date:
                flags.append(
                    Flag(
                        code=FlagCode.META_MISSING,
                        module=6,
                        severity=Severity.AMBER,
                        score_impact=5,
                        details={"message": "Document metadata is stripped or completely missing."},
                        document_id=document_id
                    )
                )

            if not flags:
                flags.append(
                    Flag(
                        code=FlagCode.META_CLEAN,
                        module=6,
                        severity=Severity.GREEN,
                        score_impact=0,
                        details={"producer": producer, "creator": creator},
                        document_id=document_id
                    )
                )

    except Exception as e:
        flags.append(
            Flag(
                code=FlagCode.DOC_UNREADABLE,
                module=6,
                severity=Severity.RED,
                score_impact=20,
                details={"error": f"Failed to parse PDF metadata: {str(e)}"},
                document_id=document_id
            )
        )
    return flags

def verify_salary_slip_arithmetic(
    gross: Optional[float],
    deductions: Optional[float],
    net: Optional[float],
    basic: Optional[float] = None,
    hra: Optional[float] = None,
    allowances: Optional[float] = None,
    pf: Optional[float] = None,
    tax: Optional[float] = None,
    other_deductions: Optional[float] = None,
    document_id: Optional[str] = None
) -> List[Flag]:
    """
    Verifies that gross - deductions == net (tolerance 1.0).
    Checks breakdown if subcomponents are present.
    """
    flags: List[Flag] = []
    if gross is None or deductions is None or net is None:
        return []

    # 1. Primary equation: gross - deductions == net
    expected_net = gross - deductions
    if abs(expected_net - net) > 1.0:
        flags.append(
            Flag(
                code=FlagCode.SLIP_ARITHMETIC_MISMATCH,
                module=6,
                severity=Severity.RED,
                score_impact=30,
                details={
                    "gross": gross,
                    "deductions": deductions,
                    "found_net": net,
                    "expected_net": expected_net,
                    "discrepancy": round(abs(expected_net - net), 2),
                    "message": f"Salary slip arithmetic mismatch: Gross ({gross:,}) - Deductions ({deductions:,}) = Expected Net ({expected_net:,}), but found {net:,}."
                },
                document_id=document_id
            )
        )
        return flags

    # 2. Earnings component breakdown check
    if basic is not None and hra is not None:
        sum_earnings = basic + hra + (allowances or 0.0)
        if abs(sum_earnings - gross) > 1.0:
            flags.append(
                Flag(
                    code=FlagCode.SLIP_ARITHMETIC_MISMATCH,
                    module=6,
                    severity=Severity.RED,
                    score_impact=30,
                    details={
                        "basic": basic,
                        "hra": hra,
                        "allowances": allowances,
                        "sum_earnings": sum_earnings,
                        "declared_gross": gross,
                        "message": f"Salary breakdown mismatch: basic+hra+allowances ({sum_earnings:,}) != gross ({gross:,})."
                    },
                    document_id=document_id
                )
            )
            return flags

    # 3. Deductions component breakdown check
    if pf is not None and tax is not None:
        sum_deductions = pf + tax + (other_deductions or 0.0)
        if abs(sum_deductions - deductions) > 1.0:
            flags.append(
                Flag(
                    code=FlagCode.SLIP_ARITHMETIC_MISMATCH,
                    module=6,
                    severity=Severity.RED,
                    score_impact=30,
                    details={
                        "pf": pf,
                        "tax": tax,
                        "other": other_deductions,
                        "sum_deductions": sum_deductions,
                        "declared_deductions": deductions,
                        "message": f"Deductions breakdown mismatch: pf+tax+other ({sum_deductions:,}) != total deductions ({deductions:,})."
                    },
                    document_id=document_id
                )
            )
            return flags

    flags.append(
        Flag(
            code=FlagCode.SLIP_ARITHMETIC_OK,
            module=6,
            severity=Severity.GREEN,
            score_impact=0,
            details={"gross": gross, "deductions": deductions, "net": net},
            document_id=document_id
        )
    )
    return flags

def perform_error_level_analysis(
    image_bytes: bytes,
    output_heatmap_path: Optional[str] = None,
    document_id: Optional[str] = None
) -> tuple[List[Flag], Optional[str]]:
    """
    Performs ELA on image: re-saves JPEG at quality 90, computes absolute difference,
    checks if localized block error exceeds median by 3x threshold.
    Saves heatmap if requested.
    """
    flags: List[Flag] = []
    heatmap_rel_path = None
    try:
        orig_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_np = np.array(orig_pil, dtype=np.float32)

        # Re-save at 90% quality
        buf = io.BytesIO()
        orig_pil.save(buf, format="JPEG", quality=90)
        resaved_pil = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        resaved_np = np.array(resaved_pil, dtype=np.float32)

        # Difference
        diff = np.abs(orig_np - resaved_np)
        max_diff = np.max(diff)
        scale = 255.0 / max_diff if max_diff > 0 else 1.0
        ela_map = np.clip(diff * scale, 0, 255).astype(np.uint8)

        # Compute block errors (16x16 grid)
        h, w, _ = diff.shape
        block_size = 16
        block_means = []
        for y in range(0, h - block_size, block_size):
            for x in range(0, w - block_size, block_size):
                blk = diff[y:y+block_size, x:x+block_size]
                block_means.append(float(np.mean(blk)))

        if block_means:
            median_err = float(np.median(block_means))
            max_err = float(np.max(block_means))

            # Rule: localized region far exceeds median (3x + 10 margin)
            if max_err > (3.0 * median_err + 10.0) and max_err > 25.0:
                flags.append(
                    Flag(
                        code=FlagCode.ELA_ANOMALY,
                        module=6,
                        severity=Severity.AMBER,
                        score_impact=8,
                        details={
                            "max_block_error": round(max_err, 2),
                            "median_error": round(median_err, 2),
                            "message": "Localized compression error anomaly detected (possible image splicing or copy-move forgery)."
                        },
                        document_id=document_id
                    )
                )
            else:
                flags.append(
                    Flag(
                        code=FlagCode.ELA_NORMAL,
                        module=6,
                        severity=Severity.GREEN,
                        score_impact=0,
                        details={"max_block_error": round(max_err, 2), "median_error": round(median_err, 2)},
                        document_id=document_id
                    )
                )

        if output_heatmap_path:
            # Save heatmap using OpenCV color map
            gray_ela = cv2.cvtColor(ela_map, cv2.COLOR_RGB2GRAY)
            heatmap = cv2.applyColorMap(gray_ela, cv2.COLORMAP_JET)
            cv2.imwrite(output_heatmap_path, heatmap)
            heatmap_rel_path = output_heatmap_path

    except Exception as e:
        pass

    return flags, heatmap_rel_path
