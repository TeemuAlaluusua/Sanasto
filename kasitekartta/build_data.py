import yaml, glob, json, re, os
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONCEPTS_DIR = os.path.join(SCRIPT_DIR, "..", "concepts")
TEMPLATE_HTML = os.path.join(SCRIPT_DIR, "template.html")
# Published output lives under docs/, since GitHub Pages serves this repo
# from the docs/ folder (see docs/index.html, the main glossary site).
# This lets docs/index.html link to ./kasitekartta/index.html directly.
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "docs", "kasitekartta")
OUTPUT_HTML = os.path.join(OUTPUT_DIR, "index.html")
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "graph_data.json")

def load_concepts():
    files = sorted(glob.glob(f"{CONCEPTS_DIR}/*.yml"))
    data = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            d = yaml.safe_load(fh)
        data[d["id"]] = d
    return data

def pref_label(d, lang):
    for t in d.get("terms") or []:
        if t.get("lang") == lang and t.get("type") == "Suositettava termi":
            return t["label"]
    for t in d.get("terms") or []:
        if t.get("lang") == lang:
            return t["label"]
    return None

def all_labels(d, lang):
    return [t["label"] for t in (d.get("terms") or []) if t.get("lang") == lang]

def definition(d, lang):
    for item in d.get("definitions") or []:
        if item.get("lang") == lang:
            return item.get("text", "").strip()
    return ""

def notes(d, lang):
    out = []
    for item in d.get("notes") or []:
        if item.get("lang") == lang:
            out.append(item.get("text", "").strip())
    return " ".join(out)

def main():
    data = load_concepts()
    ids = sorted(data.keys())
    print(f"Loaded {len(ids)} concepts")

    nodes = []
    texts = []
    for cid in ids:
        d = data[cid]
        fi = pref_label(d, "fi") or pref_label(d, "sv") or pref_label(d, "en") or cid
        sv = pref_label(d, "sv") or ""
        en = pref_label(d, "en") or ""
        def_fi = definition(d, "fi")
        def_sv = definition(d, "sv")
        def_en = definition(d, "en")
        note_fi = notes(d, "fi")
        rel = d.get("relations") or {}
        broader = rel.get("broader") or []
        narrower = rel.get("narrower") or []
        related = rel.get("related") or []
        degree = len(broader) + len(narrower) + len(related)

        nodes.append({
            "id": cid,
            "label": fi,
            "label_sv": sv,
            "label_en": en,
            "synonyms_fi": all_labels(d, "fi"),
            "synonyms_sv": all_labels(d, "sv"),
            "synonyms_en": all_labels(d, "en"),
            "def_fi": def_fi,
            "def_sv": def_sv,
            "def_en": def_en,
            "note_fi": note_fi,
            "broader": broader,
            "narrower": narrower,
            "related": related,
            "degree": degree,
            "sources": [s.get("label","") for s in (d.get("sources") or [])],
        })
        # text used for embedding: prefLabel + definition + notes (richest fi semantic signal)
        text = f"{fi}. {def_fi} {note_fi}".strip()
        if not def_fi:
            text = f"{fi}. {def_sv or def_en}".strip()
        texts.append(text)

    print("Computing lexical embeddings (TF-IDF, word + char n-grams)...")
    # NOTE: this sandbox has no network access to huggingface.co (model hub is not
    # on the allowlist), so a transformer sentence-embedding model cannot be
    # downloaded here. Falling back to a lexical vector-space model in the spirit
    # of the cited paper's own "v_lex" baseline: TF-IDF over word unigrams/bigrams
    # PLUS character 3-5-grams (robust to Finnish inflection, e.g. "tietomalli"
    # vs "tietomallin" vs "tietomallia" share most character n-grams even though
    # they are different word forms).
    from sklearn.feature_extraction.text import TfidfVectorizer
    from scipy.sparse import hstack

    FI_STOPWORDS = set("""
    ja tai sekä joka jotka jonka mikä mitä missä milloin miten kun jos vaan mutta
    on ovat oli olivat ollut olisi olisivat ole eikä ei että jos niin kuin kuten
    myös vain esimerkiksi eli siis myös tämä tässä tähän tästä nämä näissä näihin
    näistä se sen sitä siinä siihen siitä ne niiden niitä niissä niihin niistä
    joka jotka jonka joiden hän hänen häntä he heidän heitä minä sinä me te
    voi voidaan voidaan käyttää käytetään yksi kaksi kolme sekä tulee tulee olla
    """.split())

    word_vec = TfidfVectorizer(
        lowercase=True,
        token_pattern=r"(?u)\b\w\w+\b",
        ngram_range=(1, 2),
        stop_words=list(FI_STOPWORDS),
        min_df=1,
        max_df=0.6,
        sublinear_tf=True,
    )
    char_vec = TfidfVectorizer(
        lowercase=True,
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        max_df=0.6,
        sublinear_tf=True,
    )

    X_word = word_vec.fit_transform(texts)
    X_char = char_vec.fit_transform(texts)

    # weight char n-grams a bit lower than word n-grams, then L2-normalize each
    # block separately before concatenation so neither dominates by raw scale
    from sklearn.preprocessing import normalize
    X_word = normalize(X_word)
    X_char = normalize(X_char) * 0.6

    X = hstack([X_word, X_char]).tocsr()
    X = normalize(X)  # final unit-norm rows -> dot product = cosine similarity
    embeddings = X  # sparse matrix, shape (n_concepts, vocab)
    print("Embeddings shape:", embeddings.shape)

    # Cosine similarity (rows are L2-normalized -> dot product = cosine)
    sim = (embeddings @ embeddings.T).toarray()

    # existing explicit relation pairs (undirected set) to exclude from "candidate" edges
    explicit_pairs = set()
    id_index = {cid: i for i, cid in enumerate(ids)}
    for cid in ids:
        d = data[cid]
        rel = d.get("relations") or {}
        for kind in ("broader", "narrower", "related"):
            for target in rel.get(kind) or []:
                if target in id_index:
                    a, b = sorted([cid, target])
                    explicit_pairs.add((a, b))

    # candidate semantic edges: top-K nearest neighbours per node above threshold,
    # excluding self and already-explicit pairs
    K = 3
    THRESHOLD = 0.35
    candidate_edges = []
    seen = set()
    n = len(ids)
    for i in range(n):
        order = np.argsort(-sim[i])
        added = 0
        for j in order:
            if j == i:
                continue
            if added >= K:
                break
            score = float(sim[i][j])
            if score < THRESHOLD:
                break
            a, b = sorted([ids[i], ids[j]])
            if (a, b) in explicit_pairs:
                continue
            if (a, b) in seen:
                added += 1
                continue
            seen.add((a, b))
            candidate_edges.append({"source": a, "target": b, "score": round(score, 4)})
            added += 1

    candidate_edges.sort(key=lambda e: -e["score"])
    print(f"Candidate semantic edges: {len(candidate_edges)}")

    # 2D semantic layout via UMAP (fallback to PCA if it fails)
    embeddings_dense = embeddings.toarray()
    try:
        import umap
        reducer = umap.UMAP(n_neighbors=12, min_dist=0.3, metric="cosine", random_state=42)
        coords = reducer.fit_transform(embeddings_dense)
        layout_method = "umap"
    except Exception as e:
        print("UMAP failed, falling back to PCA:", e)
        from sklearn.decomposition import TruncatedSVD
        coords = TruncatedSVD(n_components=2, random_state=42).fit_transform(embeddings)
        layout_method = "svd"

    coords = np.asarray(coords)
    # normalize to a reasonable canvas range
    cmin, cmax = coords.min(axis=0), coords.max(axis=0)
    span = np.where((cmax - cmin) == 0, 1, cmax - cmin)
    norm_coords = (coords - cmin) / span  # 0..1

    for i, cid in enumerate(ids):
        nodes[i]["semantic_x"] = float(norm_coords[i][0])
        nodes[i]["semantic_y"] = float(norm_coords[i][1])

    # explicit edges list (directed for broader/narrower stored once, related undirected once)
    explicit_edges = []
    added_related = set()
    for cid in ids:
        d = data[cid]
        rel = d.get("relations") or {}
        for target in rel.get("broader") or []:
            if target in id_index:
                explicit_edges.append({"source": cid, "target": target, "kind": "broader"})
        for target in rel.get("related") or []:
            if target in id_index:
                a, b = sorted([cid, target])
                if (a, b) not in added_related:
                    added_related.add((a, b))
                    explicit_edges.append({"source": a, "target": b, "kind": "related"})

    out = {
        "meta": {
            "concept_count": len(ids),
            "embedding_model": "tfidf-word12+char_wb35 (lexical, offline fallback)",
            "layout_method": layout_method,
            "candidate_threshold": THRESHOLD,
            "candidate_topk": K,
        },
        "nodes": nodes,
        "explicit_edges": explicit_edges,
        "candidate_edges": candidate_edges,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Wrote {OUTPUT_JSON}")
    print("Explicit edges:", len(explicit_edges))
    print("Nodes:", len(nodes))

    # ---- inject data into template.html -> index.html ----
    embed_json = json.dumps(out, ensure_ascii=False).replace("</", "<\\/")
    with open(TEMPLATE_HTML, encoding="utf-8") as f:
        html = f.read()
    if "__GRAPH_DATA__" not in html:
        raise RuntimeError(f"{TEMPLATE_HTML} does not contain the __GRAPH_DATA__ placeholder")
    html = html.replace("__GRAPH_DATA__", embed_json)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUTPUT_HTML} ({len(html)} chars)")

if __name__ == "__main__":
    main()
