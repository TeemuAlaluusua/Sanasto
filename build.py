import pathlib
import json
import yaml
import sys
from datetime import datetime

root = pathlib.Path(__file__).parent
concept_dir = root / "concepts"
docs_dir = root / "docs"
scheme_file = root / "schemes.yml"

docs_dir.mkdir(exist_ok=True)


def load_yaml(path: pathlib.Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


scheme_data = load_yaml(scheme_file)["schemes"][0]
base_uri = scheme_data["baseUri"]

concepts = []
ids = set()
schemes_found = set()  # ← kerätään kaikki schemeId:t

# -----------------------------
# CONCEPTS
# -----------------------------
for f in list(concept_dir.glob("*.yml")) + list(concept_dir.glob("*.yaml")):
    if f.name.startswith("_"):
        continue

    c = load_yaml(f)
    if not isinstance(c, dict) or "id" not in c:
        continue

    cid = c["id"]
    if cid in ids:
        print("Duplicate id:", cid)
        sys.exit(1)
    ids.add(cid)

    uri = base_uri + "#/concept/" + cid

    obj = {
        "@id": uri,
        "@type": "skos:Concept"
    }

    # -------------------------
    # SCHEME LINK
    # -------------------------
    scheme_id = c.get("schemeId") or scheme_data["id"]
    schemes_found.add(scheme_id)
    obj["skos:inScheme"] = base_uri + scheme_id

    # -------------------------
    # TERMS
    # -------------------------
    pref = []
    alt = []

    if c.get("terms"):
        for t in c["terms"]:
            lit = {
                "@value": t["label"],
                "@language": t["lang"],
                "termType": t.get("type")
            }

            if t.get("type") == "Suositettava termi":
                pref.append(lit)
            else:
                alt.append(lit)

    if c.get("prefLabel"):
        for lang, text in c["prefLabel"].items():
            pref.append({"@value": text, "@language": lang})

    if c.get("altLabel"):
        for lang, text in c["altLabel"].items():
            alt.append({"@value": text, "@language": lang})

    if pref:
        obj["skos:prefLabel"] = pref
    if alt:
        obj["skos:altLabel"] = alt

    # -------------------------
    # DEFINITIONS
    # -------------------------
    defs = []

    if c.get("definitions"):
        for d in c["definitions"]:
            defs.append({"@value": d["text"], "@language": d.get("lang", "fi")})

    if c.get("definition"):
        for lang, text in c["definition"].items():
            defs.append({"@value": text, "@language": lang})

    if defs:
        obj["skos:definition"] = defs

    # -------------------------
    # NOTES
    # -------------------------
    notes = []

    for n in (c.get("notes") or []):
        notes.append({"@value": n["text"], "@language": n.get("lang", "fi")})

    if c.get("note"):
        for lang, text in c["note"].items():
            notes.append({"@value": text, "@language": lang})

    if notes:
        obj["skos:note"] = notes

    # -------------------------
    # SOURCES  ✅ FIXED
    # -------------------------
    srcs = []

    if c.get("sources"):
        for s in c.get("sources") or []:
            if not isinstance(s, dict):
                continue

            node = {}
            if s.get("label"):
                node["@value"] = s["label"]
            if s.get("lang"):
                node["@language"] = s["lang"]

            # ✅ hyväksy sekä uri että url
            if s.get("uri"):
                node["@id"] = s["uri"]
            elif s.get("url"):
                node["@id"] = s["url"]

            if node:
                srcs.append(node)

    if c.get("source"):
        for lang, text in c["source"].items():
            srcs.append({
                "@value": text,
                "@language": lang
            })

    if srcs:
        obj["dcterms:source"] = srcs

    # -------------------------
    # RELATIONS
    # -------------------------
    rel = c.get("relations", {})
    for key in ["broader", "narrower", "related"]:
        vals = rel.get(key, [])
        if vals:
            obj["skos:" + key] = [base_uri + "#/concept/" + v for v in vals]

    # -------------------------
    # METADATA
    # -------------------------
    meta = c.get("metadata", {})

    if meta.get("created"):
        created = meta["created"]
        if isinstance(created, datetime):
            created = created.isoformat()
        obj["dcterms:created"] = {"@value": created, "@type": "xsd:dateTime"}

    if meta.get("modified"):
        modified = meta["modified"]
        if isinstance(modified, datetime):
            modified = modified.isoformat()
        obj["dcterms:modified"] = {"@value": modified, "@type": "xsd:dateTime"}

    concepts.append(obj)

# -----------------------------
# SCHEMES (moniskeematuki)
# -----------------------------
scheme_objs = []

for sid in sorted(schemes_found):
    scheme_objs.append({
        "@id": base_uri + sid,
        "@type": "skos:ConceptScheme",
        "skos:prefLabel": [
            {"@value": sid, "@language": "fi"}
        ]
    })

# -----------------------------
# OUTPUT
# -----------------------------
out = {
    "@context": {
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "dcterms": "http://purl.org/dc/terms/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
    },
    "@graph": scheme_objs + concepts
}

out_path = docs_dir / "sanasto.jsonld"
out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"OK built {len(concepts)} concepts in {len(scheme_objs)} schemes -> {out_path}")
