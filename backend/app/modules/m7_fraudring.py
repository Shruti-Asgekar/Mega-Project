"""
Module 7: Fraud Ring & Syndicate Detection (Bipartite Graph Network).
Constructs a NetworkX graph linking applicants to shared identifiers:
- Phone numbers (HMAC / masked)
- Bank account numbers (HMAC / masked)
- Normalised addresses via RapidFuzz similarity (>= 92%)

Rules:
- Connected components with >= 3 applicants -> Red Flag: FRAUD_RING_SUSPECTED (-35 points, Escalate)
- Connected components with == 2 applicants -> Amber Flag: SHARED_IDENTIFIER (-8 points, Review)
- In-memory caching and node capping for production performance (< 2s, < 50MB).
"""

import time
import logging
import hashlib
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Set, Optional
import networkx as nx
from rapidfuzz import fuzz

from backend.app.core.contracts import Flag, FlagCode, Severity
from backend.app.core.security import mask_phone, mask_account, compute_identifier_hmac

logger = logging.getLogger("kyc.fraudring")

# Global in-memory cache for graph JSON
_GRAPH_CACHE: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0
}
CACHE_TTL_SECS = 300.0  # 5 minutes

def invalidate_graph_cache():
    """Invalidates cached graph JSON structure when new cases arrive."""
    global _GRAPH_CACHE
    _GRAPH_CACHE["data"] = None
    _GRAPH_CACHE["timestamp"] = 0.0
    logger.debug("[GraphCache] Cache invalidated.")

def cluster_addresses(addresses: List[str], threshold: int = 92) -> List[List[str]]:
    """Clusters similar addresses using RapidFuzz similarity ratio."""
    clusters = []
    visited = set()
    for i, a1 in enumerate(addresses):
        if i in visited:
            continue
        current_cluster = [a1]
        visited.add(i)
        for j, a2 in enumerate(addresses):
            if j not in visited and fuzz.ratio(a1.lower(), a2.lower()) >= threshold:
                current_cluster.append(a2)
                visited.add(j)
        clusters.append(current_cluster)
    return clusters

def build_fraud_graph(
    applicants_data: List[Dict[str, Any]]
) -> Tuple[nx.Graph, List[Flag], Dict[str, Any]]:
    """
    Constructs bipartite graph of applicants and identifiers.
    Returns:
        G: NetworkX graph
        flags: list of Flag objects for suspicious applicants
        summary: summary stats dict
    """
    if len(applicants_data) > 500:
        logger.info(f"[Graph] Capping analysis to latest 500 applicants (total {len(applicants_data)})")
        applicants_data = applicants_data[:500]

    G = nx.Graph()
    flags: List[Flag] = []

    if not applicants_data:
        return G, [], {
            "total_applicants": 0,
            "ring_applicants_count": 0,
            "shared_applicants_count": 0,
            "clusters": []
        }

    # 1. Address fuzzy matching across applicants
    address_clusters: Dict[str, str] = {} # applicant_id -> cluster_id
    assigned_cluster_id = 0
    checked_pairs: Set[Tuple[str, str]] = set()

    for i in range(len(applicants_data)):
        for j in range(i + 1, len(applicants_data)):
            a1 = applicants_data[i]
            a2 = applicants_data[j]
            id1, id2 = a1["applicant_id"], a2["applicant_id"]
            addr1 = a1.get("address", "").strip()
            addr2 = a2.get("address", "").strip()

            if not addr1 or not addr2:
                continue

            # Compare addresses
            sim = fuzz.token_sort_ratio(addr1, addr2)
            if sim >= 92.0:
                c1 = address_clusters.get(id1)
                c2 = address_clusters.get(id2)
                if not c1 and not c2:
                    assigned_cluster_id += 1
                    cid = f"cluster_{assigned_cluster_id}"
                    address_clusters[id1] = cid
                    address_clusters[id2] = cid
                elif c1 and not c2:
                    address_clusters[id2] = c1
                elif not c1 and c2:
                    address_clusters[id1] = c2
                elif c1 and c2 and c1 != c2:
                    # Merge clusters
                    for k, v in list(address_clusters.items()):
                        if v == c2:
                            address_clusters[k] = c1

    # 2. Add nodes and edges
    for a in applicants_data:
        app_id = a["applicant_id"]
        app_node = f"app:{app_id}"
        masked_name = a.get("name_masked", "Applicant")

        G.add_node(
            app_node,
            node_type="applicant",
            label=masked_name,
            title=f"Applicant: {masked_name} (Case #{a.get('case_id', app_id)[:8]})",
            applicant_id=app_id,
            case_id=a.get("case_id", app_id),
            color="#6c757d", # Default grey
            shape="dot",
            size=18
        )

        # Phone node
        phone = a.get("phone")
        if phone:
            clean_p = "".join(filter(str.isdigit, str(phone)))
            masked_p = mask_phone(clean_p)
            phone_hash = compute_identifier_hmac(clean_p) or hashlib.sha256(clean_p.encode("utf-8")).hexdigest()
            phone_node = f"phone:{phone_hash[:12]}"
            G.add_node(phone_node, node_type="identifier", label=masked_p, title=f"Phone: {masked_p}", color="#17a2b8", shape="diamond", size=14)
            G.add_edge(app_node, phone_node, relationship="HAS_PHONE")

        # Account node
        acc = a.get("account_number")
        if acc:
            clean_acc = str(acc).strip()
            masked_acc = mask_account(clean_acc)
            acc_hash = compute_identifier_hmac(clean_acc) or hashlib.sha256(clean_acc.encode("utf-8")).hexdigest()
            acc_node = f"acc:{acc_hash[:12]}"
            G.add_node(acc_node, node_type="identifier", label=masked_acc, title=f"Account: {masked_acc}", color="#28a745", shape="square", size=14)
            G.add_edge(app_node, acc_node, relationship="HAS_ACCOUNT")

        # Address cluster node
        if app_id in address_clusters:
            cid = address_clusters[app_id]
            addr_node = f"addr:{cid}"
            raw_addr = a.get("address", "")
            short_addr = (raw_addr[:25] + "...") if len(raw_addr) > 25 else raw_addr
            G.add_node(addr_node, node_type="identifier", label=f"Addr #{cid[-1]}", title=f"Shared Address: {short_addr}", color="#ffc107", shape="triangle", size=14)
            G.add_edge(app_node, addr_node, relationship="HAS_ADDRESS")

    # 3. Analyze connected components
    ring_members: Set[str] = set()
    shared_members: Set[str] = set()
    clusters_info = []

    for comp in nx.connected_components(G):
        app_nodes_in_comp = [n for n in comp if G.nodes[n].get("node_type") == "applicant"]
        count = len(app_nodes_in_comp)

        if count >= 3:
            # FRAUD RING SUSPECTED (RED)
            for n in app_nodes_in_comp:
                ring_members.add(n)
                G.nodes[n]["color"] = "#dc3545" # Red
                G.nodes[n]["size"] = 28
                app_id = G.nodes[n]["applicant_id"]
                flags.append(
                    Flag(
                        code=FlagCode.FRAUD_RING_SUSPECTED,
                        module=7,
                        severity=Severity.RED,
                        score_impact=35,
                        details={
                            "cluster_size": count,
                            "applicant_id": app_id,
                            "message": f"Suspicious syndicate cluster: linked to {count - 1} other applicants via shared credentials."
                        }
                    )
                )
            clusters_info.append({"type": "ring", "size": count, "applicants": app_nodes_in_comp})

        elif count == 2:
            # SHARED IDENTIFIER (AMBER)
            for n in app_nodes_in_comp:
                shared_members.add(n)
                G.nodes[n]["color"] = "#fd7e14" # Orange
                G.nodes[n]["size"] = 24
                app_id = G.nodes[n]["applicant_id"]
                flags.append(
                    Flag(
                        code=FlagCode.SHARED_IDENTIFIER,
                        module=7,
                        severity=Severity.AMBER,
                        score_impact=8,
                        details={
                            "cluster_size": 2,
                            "applicant_id": app_id,
                            "message": "Applicant shares phone, bank account, or address with 1 other application."
                        }
                    )
                )
            clusters_info.append({"type": "shared", "size": 2, "applicants": app_nodes_in_comp})
        else:
            # Benign single applicant
            for n in app_nodes_in_comp:
                G.nodes[n]["color"] = "#6c757d" # Grey
                app_id = G.nodes[n]["applicant_id"]
                flags.append(
                    Flag(
                        code=FlagCode.NO_FRAUD_RING,
                        module=7,
                        severity=Severity.GREEN,
                        score_impact=0,
                        details={"cluster_size": 1, "applicant_id": app_id}
                    )
                )

    summary = {
        "total_applicants": len(applicants_data),
        "ring_applicants_count": len(ring_members),
        "shared_applicants_count": len(shared_members),
        "clusters": clusters_info
    }

    return G, flags, summary

def get_serializable_graph_data(
    applicants_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Returns graph representation formatted for client-side Vis.js rendering with in-memory caching.
    """
    global _GRAPH_CACHE
    now = time.time()
    if _GRAPH_CACHE["data"] is not None and (now - _GRAPH_CACHE["timestamp"]) < CACHE_TTL_SECS:
        return _GRAPH_CACHE["data"]

    G, flags, summary = build_fraud_graph(applicants_data)

    nodes = []
    for n, data in G.nodes(data=True):
        nodes.append({
            "id": n,
            "label": data.get("label", n),
            "title": data.get("title", n),
            "color": data.get("color", "#6c757d"),
            "shape": data.get("shape", "dot"),
            "size": data.get("size", 16)
        })

    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            "from": u,
            "to": v,
            "title": data.get("relationship", "LINKS"),
            "color": {"color": "#cbd5e1"}
        })

    result = {
        "nodes": nodes,
        "edges": edges,
        "ring_count": summary.get("ring_applicants_count", 0),
        "summary": summary,
        "flags": [f.model_dump() for f in flags]
    }

    _GRAPH_CACHE["data"] = result
    _GRAPH_CACHE["timestamp"] = now
    return result

def generate_offline_graph_html(G: nx.Graph, summary: Any = None) -> str:
    """Optional export helper for offline graph generation."""
    nodes = [{"id": n, "label": d.get("label", n), "color": d.get("color", "#6c757d")} for n, d in G.nodes(data=True)]
    edges = [{"from": u, "to": v} for u, v in G.edges()]
    import json
    return f"<!DOCTYPE html><html><head><title>Fraud Ring Bipartite Graph</title></head><body><div id='net'></div><script>var nodes={json.dumps(nodes)}; var edges={json.dumps(edges)};</script></body></html>"
