# Atlas OS

Offline-first AI agent operating environment and knowledge appliance.

Built on Debian 13 Stable (x86-64). Product specification: see `product.md` (Atlas OS product v0.2).

## Quick start

```bash
# On a Debian 13 build host (or compatible container):
make deps          # install live-build, calamares tooling helpers
make catalog       # validate sources.catalog.yaml
make lock-refresh  # internet-connected: resolve digests into sources.lock.yaml
make iso           # offline ISO build from verified cache
make test-install  # QEMU UEFI boot + install smoke test
```

## Principles

- Offline is the default state after provisioning.
- Agents never call Docker socket, host shell, or privileged APIs directly.
- All release inputs are pinned in `release/sources.lock.yaml`.
- ISO builds fail closed if any required asset is missing or unverified.

## Phases

| Phase | Focus |
|-------|--------|
| 0 | Legal, catalog, threat model, signing plan |
| 1 | Bootable branded ISO + Calamares |
| 2 | Offline container payload + Ollama |
| 3 | Identity, firewall, System Daemon |
| 4 | Agent runtime, Policy Gateway, Model Router |
| 5 | Knowledge / RAG |
| 6 | Content packs |
| 7 | Updates, backup, recovery |
| 8 | OEM and commercial release |

## Licence

Atlas OS packaging and original code: see `docs/legal/`. Upstream Project N.O.M.A.D. is Apache-2.0; attribution is required.
