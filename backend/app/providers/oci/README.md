# OCI extension points

These adapters deliberately raise `NotImplementedError`. No OCI credentials or SDK are needed for AWS.
Select concrete OCI services during migration, implement the existing signatures, then wire them in
`providers/factory.py`. Follow `docs/oci-migration.md`; run the same API/workflow tests with OCI contract fixtures.
