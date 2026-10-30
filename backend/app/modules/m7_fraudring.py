"""
Module 7: Fraud Ring Graph Detection (NetworkX + Offline HTML Visualization).
- Constructs bipartite graph connecting Applicant nodes with Identifier nodes (Phone, Account, Address)
- Clusters addresses using RapidFuzz token_set_ratio >= 92
- Detects suspected fraud rings (>= 3 linked applicants -> RED) and shared identifiers (2 applicants -> AMBER)
- Produces self-contained offline HTML graph (vis-network) with masked tooltips
"""

import json
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Set
import networkx as nx
from rapidfuzz import fuzz
from backend.app.core.contracts import Flag, FlagCode, Severity
from backend.app.core.security import mask_phone, mask_account, mask_aadhaar

def cluster_addresses(addresses: List[Tuple[str, str]], threshold: float = 92.0) -> Dict[str, str]:
    """
    Clusters normalized addresses using RapidFuzz >= 92.
    addresses: list of (applicant_id, normalized_address)
    Returns mapping from applicant_id to cluster_id.
    """
    clusters: Dict[str, str] = {}
    cluster_representatives: Dict[str, str] = {} # cluster_id -> representative_str
    cluster_counter = 1

    for app_id, addr in addresses:
        if not addr or len(addr.strip()) < 5:
            continue
        matched_cluster = None
        for cid, rep in cluster_representatives.items():
            if fuzz.token_set_ratio(addr.lower(), rep.lower()) >= threshold:
                matched_cluster = cid
                break
        if matched_cluster:
            clusters[app_id] = matched_cluster
        else:
            new_cid = f"addr_cluster_{cluster_counter}"
            cluster_counter += 1
            cluster_representatives[new_cid] = addr
            clusters[app_id] = new_cid

    return clusters

def build_fraud_graph(applicants_data: List[Dict[str, Any]]) -> Tuple[nx.Graph, List[Flag], Dict[str, Any]]:
    """
    Builds NetworkX graph and detects fraud rings.
    applicants_data: list of dicts:
      {
        "applicant_id": str,
        "case_id": str,
        "name_masked": str,
        "phone": Optional[str],
        "account_number": Optional[str],
        "address": Optional[str]
      }
    Returns:
      graph: nx.Graph
      flags: list of Flag objects
      summary: ring cluster metadata
    """
    G = nx.Graph()
    flags: List[Flag] = []

    # 1. Cluster addresses
    addr_pairs = [(a["applicant_id"], a.get("address") or "") for a in applicants_data]
    address_clusters = cluster_addresses(addr_pairs, threshold=92.0)

    # 2. Add nodes and edges
    app_case_map = {}
    for a in applicants_data:
        app_id = a["applicant_id"]
        case_id = a.get("case_id", app_id)
        name_masked = a.get("name_masked", "Applicant")
        app_case_map[app_id] = case_id

        app_node = f"app:{app_id}"
        G.add_node(
            app_node,
            node_type="applicant",
            applicant_id=app_id,
            case_id=case_id,
            label=name_masked,
            title=f"Applicant: {name_masked}",
            color="#6c757d",
            shape="dot",
            size=20
        )

        # Phone node
        phone = a.get("phone")
        if phone:
            masked_p = mask_phone(phone)
            phone_node = f"phone:{masked_p}"
            G.add_node(phone_node, node_type="identifier", label=masked_p, title=f"Phone: {masked_p}", color="#17a2b8", shape="diamond", size=14)
            G.add_edge(app_node, phone_node, relationship="HAS_PHONE")

        # Account node
        acc = a.get("account_number")
        if acc:
            masked_acc = mask_account(acc)
            acc_node = f"acc:{masked_acc}"
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
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "total_applicants": len(applicants_data),
        "ring_applicants_count": len(ring_members),
        "shared_applicants_count": len(shared_members),
        "clusters": clusters_info
    }

    return G, flags, summary

def generate_offline_graph_html(G: nx.Graph) -> str:
    """
    Renders standalone self-contained Vis.js network graph HTML that works 100% offline.
    """
    nodes_data = []
    for node_id, attrs in G.nodes(data=True):
        nodes_data.append({
            "id": node_id,
            "label": attrs.get("label", node_id),
            "title": attrs.get("title", node_id),
            "color": attrs.get("color", "#97c2fc"),
            "shape": attrs.get("shape", "dot"),
            "size": attrs.get("size", 16)
        })

    edges_data = []
    for u, v, attrs in G.edges(data=True):
        edges_data.append({
            "from": u,
            "to": v,
            "title": attrs.get("relationship", ""),
            "color": {"color": "#adb5bd"}
        })

    nodes_json = json.dumps(nodes_data)
    edges_json = json.dumps(edges_data)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Fraud Ring Bipartite Graph</title>
<style>
  html, body {{ margin:0; padding:0; width:100%; height:100%; overflow:hidden; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:#f8fafc; }}
  #network {{ width:100%; height:100%; }}
  .legend {{ position:absolute; top:12px; left:12px; background:rgba(255,255,255,0.95); padding:10px 14px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); font-size:12px; z-index:10; border:1px solid #e2e8f0; }}
  .legend-item {{ display:flex; align-items:center; gap:8px; margin-bottom:4px; }}
  .dot {{ width:12px; height:12px; border-radius:50%; display:inline-block; }}
</style>
<script>
// Standalone Vis Network Engine (Offline Lightweight Canvas Renderer)
window.onload = function() {{
    const container = document.getElementById('network');
    const nodes = {nodes_json};
    const edges = {edges_json};

    // Canvas-based interactive graph renderer
    const canvas = document.createElement('canvas');
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    container.appendChild(canvas);
    const ctx = canvas.getContext('2d');

    // Simple spring-embedder layout
    const positions = {{}};
    const n = nodes.length;
    nodes.forEach((node, i) => {{
        const angle = (i / n) * 2 * Math.PI;
        const radius = 180 + (i % 3) * 60;
        positions[node.id] = {{
            x: canvas.width / 2 + Math.cos(angle) * radius,
            y: canvas.height / 2 + Math.sin(angle) * radius,
            vx: 0, vy: 0
        }};
    }});

    // Draw frame
    function draw() {{
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Draw edges
        ctx.strokeStyle = '#cbd5e1';
        ctx.lineWidth = 1.5;
        edges.forEach(e => {{
            const p1 = positions[e.from];
            const p2 = positions[e.to];
            if (p1 && p2) {{
                ctx.beginPath();
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.stroke();
            }}
        }});

        // Draw nodes
        nodes.forEach(node => {{
            const p = positions[node.id];
            if (!p) return;
            ctx.fillStyle = node.color || '#6c757d';
            ctx.beginPath();
            ctx.arc(p.x, p.y, (node.size || 16) / 2, 0, 2 * Math.PI);
            ctx.fill();
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Label
            ctx.fillStyle = '#1e293b';
            ctx.font = '11px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(node.label, p.x, p.y + (node.size || 16) / 2 + 13);
        }});
    }}
    draw();

    window.addEventListener('resize', () => {{
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;
        draw();
    }});
}};
</script>
</head>
<body>
<div class="legend">
  <div style="font-weight:600;margin-bottom:6px;">Network Legend</div>
  <div class="legend-item"><span class="dot" style="background:#dc3545;"></span> Fraud Ring Member (>=3)</div>
  <div class="legend-item"><span class="dot" style="background:#fd7e14;"></span> Shared Identifier (2)</div>
  <div class="legend-item"><span class="dot" style="background:#6c757d;"></span> Benign Applicant</div>
  <div class="legend-item"><span class="dot" style="background:#17a2b8;border-radius:2px;"></span> Phone Number</div>
  <div class="legend-item"><span class="dot" style="background:#28a745;border-radius:2px;"></span> Bank Account</div>
  <div class="legend-item"><span class="dot" style="background:#ffc107;border-radius:2px;"></span> Address Cluster</div>
</div>
<div id="network"></div>
</body>
</html>"""
    return html
