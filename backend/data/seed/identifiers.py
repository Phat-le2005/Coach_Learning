from uuid import UUID, uuid5

SEED_NAMESPACE = UUID("7f5454c6-6e68-4b59-89af-67f3b74ccf65")


def stable_id(entity: str, code: str) -> UUID:
    """Return the same UUID for a versioned entity/code pair on every machine."""
    return uuid5(SEED_NAMESPACE, f"edums:{entity}:{code.strip().upper()}")
