"""
Unit Tests for Module 7 (Fraud Ring Graph).
"""

import pytest
from backend.app.core.contracts import FlagCode, Severity
from backend.app.modules.m7_fraudring import (
    build_fraud_graph,
    cluster_addresses,
    generate_offline_graph_html
)

def test_fraud_ring_4_applicants_detected():
    # 4 applicants linked together in a syndicate
    ring_applicants = [
        {
            "applicant_id": "ring-1",
            "name_masked": "Vijay Sharma",
            "phone": "9876543210", # Shared with ring-2
            "account_number": "1122334455",
            "address": "Flat 101, Galaxy Apts, Sector 4, Noida"
        },
        {
            "applicant_id": "ring-2",
            "name_masked": "Ajay Sharma",
            "phone": "9876543210", # Shared with ring-1
            "account_number": "9988776655", # Shared with ring-3
            "address": "Flat 102, Galaxy Apts, Sector 4, Noida" # Similar address
        },
        {
            "applicant_id": "ring-3",
            "name_masked": "Sanjay Sharma",
            "phone": "9123456789",
            "account_number": "9988776655", # Shared with ring-2
            "address": "101 Galaxy Apartments Sector 4 Noida" # Fuzzy matches ring-1/2 >= 92%
        },
        {
            "applicant_id": "ring-4",
            "name_masked": "Karan Sharma",
            "phone": "9123456789", # Shared with ring-3
            "account_number": "5544332211",
            "address": "Flat 101, Galaxy Apts, Sector 4, Noida"
        },
        # Benign standalone applicant
        {
            "applicant_id": "benign-1",
            "name_masked": "Pooja Hegde",
            "phone": "9998887776",
            "account_number": "3322110099",
            "address": "Plot 88, Green Meadows, JP Nagar, Bengaluru"
        }
    ]

    G, flags, summary = build_fraud_graph(ring_applicants)

    # 4 ring applicants must be flagged with FRAUD_RING_SUSPECTED
    ring_flags = [f for f in flags if f.code == FlagCode.FRAUD_RING_SUSPECTED]
    assert len(ring_flags) == 4
    for rf in ring_flags:
        assert rf.severity == Severity.RED
        assert rf.details["cluster_size"] == 4

    # Benign applicant has NO_FRAUD_RING
    benign_flags = [f for f in flags if f.code == FlagCode.NO_FRAUD_RING]
    assert len(benign_flags) == 1
    assert benign_flags[0].details["applicant_id"] == "benign-1"

    # Check node colors
    assert G.nodes["app:ring-1"]["color"] == "#dc3545" # Red
    assert G.nodes["app:benign-1"]["color"] == "#6c757d" # Grey

    # Check standalone HTML generation
    html = generate_offline_graph_html(G)
    assert "<title>Fraud Ring Bipartite Graph</title>" in html
    assert "XXXXXXX210" in html # Masked phone
    assert "9876543210" not in html # No unmasked phone
