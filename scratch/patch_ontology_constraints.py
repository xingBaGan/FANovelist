file_path = "/Users/jzj/multica_workspaces/d7baa1d4-c920-4520-b7ae-df5083f1f2cc/1ee06d45/workdir/FANovelist/src/openharness/graphiti/ontology.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace Event-to-Character mapping
old_c_to_ev = """# Character to Event relations
for _c in _CHAR_LABELS:
    for _ev in _EVENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _ev)] = [
            "PARTICIPATED_IN", "INVOLVED_IN", "WITNESSED", "KILLED", "SAVED", "DEFEATED", "LOVES", "HATES"
        ]"""

new_c_to_ev = """# Character to Event relations (restricted to semantically valid options)
for _c in _CHAR_LABELS:
    for _ev in _EVENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_c, _ev)] = [
            "PARTICIPATED_IN", "INVOLVED_IN", "WITNESSED", "LOVES", "HATES", "FEARS"
        ]"""

if old_c_to_ev in content:
    content = content.replace(old_c_to_ev, new_c_to_ev)
else:
    print("Warning: old_c_to_ev not found exactly.")

# Replace Event-to-Location mapping
old_ev_to_loc = """# Event to Location relations
for _ev in _EVENT_LABELS:
    for _loc in _LOC_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _loc)] = [
            "LOCATED_AT", "LOCATED_IN", "HAPPENED_AT", "INSIDE"
        ]"""

new_ev_to_loc = """# Event to Location relations (restricted to semantically valid options)
for _ev in _EVENT_LABELS:
    for _loc in _LOC_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _loc)] = [
            "HAPPENED_AT", "LOCATED_IN"
        ]"""

if old_ev_to_loc in content:
    content = content.replace(old_ev_to_loc, new_ev_to_loc)
else:
    print("Warning: old_ev_to_loc not found exactly.")

# Replace Event-to-NarrativeElement mapping
old_ev_to_elem = """# Event to NarrativeElement relations
for _ev in _EVENT_LABELS:
    for _elem in _ELEMENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _elem)] = [
            "HAS_ITEM", "OWNS", "INVOLVED_IN", "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN"
        ]"""

new_ev_to_elem = """# Event to NarrativeElement relations (restricted to semantically valid options)
for _ev in _EVENT_LABELS:
    for _elem in _ELEMENT_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _elem)] = [
            "INVOLVED_IN", "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN"
        ]"""

if old_ev_to_elem in content:
    content = content.replace(old_ev_to_elem, new_ev_to_elem)
else:
    print("Warning: old_ev_to_elem not found exactly.")

# Replace Event-to-ChekhovsGun mapping
old_ev_to_gun = """# Event to ChekhovsGun relations
for _ev in _EVENT_LABELS:
    for _gun in _GUN_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _gun)] = [
            "HAS_ITEM", "OWNS", "INVOLVED_IN", "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN", "ALTERS"
        ]"""

new_ev_to_gun = """# Event to ChekhovsGun relations (restricted to semantically valid options)
for _ev in _EVENT_LABELS:
    for _gun in _GUN_LABELS:
        NOVEL_EDGE_TYPE_MAP[(_ev, _gun)] = [
            "INVOLVED_IN", "CAUSED", "TRIGGERS", "LEADS_TO", "RESULTED_IN", "ALTERS"
        ]"""

if old_ev_to_gun in content:
    content = content.replace(old_ev_to_gun, new_ev_to_gun)
else:
    print("Warning: old_ev_to_gun not found exactly.")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Ontology relationship constraints updated successfully.")
