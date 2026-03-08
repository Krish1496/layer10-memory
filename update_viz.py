"""
update_viz.py — Embeds outputs/graph.json into viz/index.html
Just run:  python update_viz.py
"""

import json
import re
import os

GRAPH_JSON = os.path.join("outputs", "graph.json")
VIZ_HTML   = os.path.join("viz", "index.html")

# Load the graph data
with open(GRAPH_JSON, "r", encoding="utf-8") as f:
    graph_data = json.load(f)

# Load the HTML
with open(VIZ_HTML, "r", encoding="utf-8") as f:
    html = f.read()

# Replace the embedded data with the new graph
new_data    = json.dumps(graph_data)
replacement = f"const EMBEDDED_DEMO_DATA = {new_data};"

html = re.sub(
    r"const EMBEDDED_DEMO_DATA = .*?;",
    lambda m: replacement,
    html,
    flags=re.DOTALL
)

with open(VIZ_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✓ Done! viz/index.html updated with:")
print(f"  {len(graph_data['entities'])} entities")
print(f"  {len(graph_data['claims'])} claims")
print(f"  {len(graph_data['evidence'])} evidence items")
print(f"  {len(graph_data['merges'])} merges")
print(f"\nNow open viz/index.html in your browser.")
