import os


def pytest_sessionstart(session):
    os.environ.setdefault("IF_NEO4J_DISABLED", "true")
