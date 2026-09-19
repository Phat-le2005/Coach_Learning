from uuid import UUID

# Compatibility owner for subjects created before curriculum versioning existed.
# Canonical import may adopt a legacy record only when its manifest explicitly
# declares compatible stable identifiers.
LEGACY_CURRICULUM_ID = UUID("c65a10e9-9850-5ad9-afeb-8448634b4a8f")
LEGACY_CURRICULUM_VERSION_ID = UUID("a8ee8b78-f064-54d9-9e2b-586543c9682d")
