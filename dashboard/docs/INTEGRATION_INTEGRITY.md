# INTEGRATION: Integrity / Chain-of-Custody — T10/T11

## Purpose
Centralize integrity evaluation rules so UI never “guesses” integrity status ad-hoc.

## Inputs (master variables)
- `hash`
- `signature`
- `device_cert_id`
- (optional) `integrity_status` as stored/declared field

## Current (mock) behavior
We evaluate integrity using placeholder rules:
- If key fields are missing → UNKNOWN
- If a record is explicitly flagged invalid (placeholder) → INVALID
- Otherwise → VALID

## Future (real) behavior
### Hash verification
- Recompute hash from append-only archived file/segment (`source_file_id`)
- Compare recomputed hash to stored `hash`

### Signature verification
- Validate `signature` using device public keys/cert chain
- Certificates likely live in:
  - secure store (Vault / AWS Secrets / etc.)
  - or a controlled registry service
- Verify:
  - signature matches payload digest
  - cert is valid + not revoked

### Where certs live
- `DeviceRegistry` or a separate `CertRegistry` service could map `device_cert_id` to:
  - cert material (public key)
  - metadata (issue date, revocation status)

## “Turn it on” later
1) Implement server-side verification service:
   - Accept measurement payload + metadata
   - Verify hash/signature
   - Persist derived `integrity_status`
2) UI continues using `evaluateIntegrity()` without changes.

## Code location
- Evaluator: `lib/integrity/integrityEvaluator.ts`
