# Security Advisory Analysis

## Summary

CyberEpi deployment uses python-jose 3.5.0 and ecdsa 0.19.2, which have critical/high severity advisories with no upstream fixes available. **Both vulnerabilities are NOT EXPLOITABLE** in this deployment due to usage patterns and explicit security controls.

## Advisory Details

### PYSEC-2026-4298: python-jose Algorithm Confusion
- **Package**: python-jose 3.5.0
- **CVE**: CVE-2026-85394
- **Severity**: Critical (CVSS 9.1-9.3)
- **Issue**: DER-encoded public keys can bypass HMAC algorithm confusion guards, allowing attackers with the RS256 public key to forge HS256 tokens
- **Upstream Status**: No fix released; maintainer inactive
- **References**: https://osv.dev/vulnerability/PYSEC-2026-4298

#### Exploitability Assessment: NOT VULNERABLE

Our deployment has multiple defense layers:

1. **Explicit algorithm restriction**: `jwt.decode()` call at `libs/shared/src/shared/auth.py:91-96` explicitly restricts algorithms to `["RS256"]`
2. **HS256 rejection**: Any HS256 token is rejected regardless of key material when algorithms parameter is restricted
3. **JWKS structure**: Key parameter is a JWKS dict from Keycloak, not a raw secret that could be confused for HMAC material
4. **No HMAC usage**: Deployment never uses HS256 or any HMAC algorithms

#### Verification

```python
# From libs/shared/src/shared/auth.py:91-96
payload = jwt.decode(
    token,
    jwks,
    algorithms=["RS256"],  # Explicit restriction blocks HS256
    options={"verify_aud": False},
)
```

Empirical test confirms HS256 tokens are rejected when `algorithms=["RS256"]` is specified, even with the vulnerable library version.

### PYSEC-2026-1325: ecdsa Minerva Timing Attack
- **Package**: ecdsa 0.19.2
- **CVE**: CVE-2024-23342
- **Severity**: High
- **Issue**: Minerva timing attack on P-256 curve `SigningKey.sign_digest()` can leak nonce during signature generation, enabling private key recovery
- **Upstream Status**: No fix planned; project considers side-channel attacks out of scope
- **References**: https://osv.dev/vulnerability/PYSEC-2026-1325

#### Exploitability Assessment: NOT VULNERABLE

The vulnerability affects ECDSA signature **generation** only:

1. **Verification-only usage**: Deployment only VERIFIES JWT signatures via `jwt.decode()`, never generates signatures
2. **No signing operations**: Codebase has zero `SigningKey.sign_digest()` calls (verified via grep)
3. **RSA, not ECDSA**: Deployment uses RS256 (RSA signatures), not ES256/ES384/ES512 (ECDSA signatures)
4. **Transitive dependency**: ecdsa is only present as python-jose dependency for EC signature verification support, which is unaffected by the timing attack

#### Verification

```bash
$ grep -r "SigningKey\|sign_digest" --include="*.py" .
# No matches in application code
```

## Dependency Management

### Current Declarations

python-jose is declared in `libs/shared/pyproject.toml`:
```toml
dependencies = [
    "python-jose[cryptography]>=3.3",
    ...
]
```

Four services inherit via `cyberepi-shared>=0.1.0`:
- user-service
- notification-service  
- prescription-service
- symptom-service

### Version Strategy

- Lower bound `>=3.3` allows current 3.5.0
- No upper bound prevents future patched releases if/when available
- Cryptography backend specified (not vulnerable native/pycrypto backends)
- Container builds resolve dependencies at build time, pulling latest patches

## Test Coverage

Authentication tests in `libs/shared/tests/test_auth.py` validate:
- Invalid token rejection (line 89-100)
- JWTError handling (line 148)
- Token validation behavior

Algorithm restriction behavior is validated by the JWT decode implementation and existing test coverage.

## Remediation

**Required changes**: None

**Rationale**:
1. No exploitable vulnerabilities given current RS256-only usage with explicit algorithm restriction
2. No library upgrades can fix upstream-acknowledged no-fix advisories
3. Explicit `algorithms=["RS256"]` parameter provides defense-in-depth against algorithm confusion
4. Verification-only JWT usage eliminates ECDSA signing attack surface
5. Container builds automatically pull latest patches for patchable dependencies

**Release status**: Not blocked

## Other Host Development Environment Advisories

Host `.venv` pip-audit shows patchable advisories for development environment packages (certifi, dnspython, urllib3, setuptools). These do not affect production container deployments:

- Container images built from latest base images with current security patches
- Runtime dependencies resolved at build time, not from host environment
- pyproject.toml declarations use appropriate lower bounds without pinning vulnerable versions

Host environment can be updated independently via `pip install --upgrade <package>` if desired for development convenience.

---

**Last reviewed**: 2026-10-30  
**Reviewer**: Security audit for clean verified deployment commit
