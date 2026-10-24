import json
import os


def parse_node(node, depth=0):
    name = (
        node.get("operator_type")
        or node.get("name")
        or node.get("type")
        or "OPERATOR"
    )
    timing = node.get("operator_timing") or node.get("timing") or 0.0

    indent = "  " * depth
    print(f"{indent}▸ {name} (Timing: {timing:.2f}s)")

    # Consolidate operator metadata from both detailed and standard JSON modes
    info_dict = {}
    if isinstance(node.get("operator_info"), dict):
        info_dict.update(node.get("operator_info"))
    if isinstance(node.get("extra_info"), dict):
        info_dict.update(node.get("extra_info"))

    for key, val in info_dict.items():
        key_lower = key.lower()
        if any(
            k in key_lower
            for k in [
                "memory",
                "spill",
                "cardinality",
                "rows",
                "bytes",
                "partition",
            ]
        ):
            val_str = str(val).replace("\n", " ").strip()
            print(f"{indent}   └─ {key}: {val_str}")

    # Process children nodes
    children = node.get("children", [])
    for child in children:
        parse_node(child, depth + 1)


profile_file = "profile_output.json"

if not os.path.exists(profile_file):
    print(f"Error: {profile_file} not found.")
    exit(1)

with open(profile_file) as f:
    data = json.load(f)

print("\n=== DETAILED QUERY EXECUTION PROFILE ===")
query_info = data.get("query") or {}
total_latency = (
    query_info.get("total_time")
    or data.get("latency")
    or data.get("timing")
    or 0.0
)
print(f"Total Query Time: {total_latency:.2f}s\n")

# duckdb 2.0+ nests the plan under "operator" (a list of root nodes);
# older versions exposed it as "tree" or directly at the top level
if isinstance(data.get("operator"), list) and data["operator"]:
    root = data["operator"][0]
else:
    root = data.get("tree") or data
parse_node(root)
