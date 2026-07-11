# Atlas OS Threat Model (Phase 0)

Status: foundation document  
Aligned with product §24.1  
Date: 2026-07-11

## Assets

- User documents, notes, conversations, agent memory
- Encryption keys, backup keys, device identity
- Local model weights and embeddings
- Offline knowledge packs (ZIM, PMTiles, Kolibri)
- Host integrity (root FS, Docker, System Daemon)
- Signing keys for OS / packs / updates

## Adversaries and scenarios

| Scenario | Impact | Mitigations |
|----------|--------|-------------|
| Device theft | Data disclosure | LUKS2, screen lock, encrypted backups |
| Malicious public Wi-Fi | Remote compromise / data leak | Default-deny firewall, loopback-only services, no SSH by default |
| Untrusted LAN client | Unauth access to Command Centre | Local auth required; Trusted LAN mode explicit |
| Malicious documents | Prompt injection / exfil | Trust levels, retrieval isolation, Policy Gateway |
| Tool poisoning | Privilege escalation | Signed tool registry, capability tokens, no raw shell |
| Compromised container images | Host takeover | Digest pins, SBOM, vulnerability scan, read-only FS |
| Supply-chain attack | Malicious release | Separate lock-refresh, signed metadata, fail-closed ISO |
| Agent privilege escalation | Destructive host actions | Policy Gateway, approval L3/L4, System Daemon typed RPCs |
| Cross-user leakage | Privacy breach | Per-user paths, DB scoping, RAG isolation tests |
| Failed updates | Bricked system | Btrfs snapshots, auto-rollback, recovery ISO |
| Malicious USB packs | Code/content injection | Signature verify, licence display, atomic install |
| Browser attacks on localhost | Privilege via UI | Auth sessions, CSP, no docker.sock to browser |

## Trust boundaries

1. **Untrusted content** — documents, ZIM text, web (if enabled) never become instructions for privileged tools.
2. **Model boundary** — model output is untrusted; only Policy Gateway grants capabilities.
3. **Container boundary** — apps run without host Docker socket after Phase 3 migration.
4. **Host privileged boundary** — System Daemon only; Unix socket + capability tokens.
5. **Network boundary** — private device mode by default.

## Out of scope for V1

- Nation-state physical implants
- Side-channel attacks on local inference
- Formal verification of agent planners

## Acceptance

Security tests in `tests/security/` must cover: unauthenticated LAN denial, docker.sock absence from UI containers, capability escalation failure, pack signature rejection, firewall mode matrix.
