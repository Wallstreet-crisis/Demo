from neo4j import Driver, GraphDatabase

from ifrontier.core.settings import settings


def create_driver() -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_pool_size=50,
        connection_timeout=10,
    )
