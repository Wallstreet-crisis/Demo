from pathlib import Path


def load_init_cypher() -> str:
    here = Path(__file__).resolve()
    cypher_path = here.parents[3] / "scripts" / "neo4j" / "init.cypher"
    return cypher_path.read_text(encoding="utf-8")
