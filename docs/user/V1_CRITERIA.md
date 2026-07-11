# Atlas OS 1.0 release criteria checklist

Track against product §45. Mark when automated or manual verification lands.

| # | Criterion | Status |
|---|-----------|--------|
| 1 | ISO installs without internet | scaffolding (needs Debian live-build host) |
| 2 | Unique secrets on install | implemented (atlas-firstboot) |
| 3 | Core services autostart | systemd units present |
| 4 | Command Centre requires auth | implemented (API Bearer) |
| 5 | No unintended public listeners | default bind 127.0.0.1 + ufw modes |
| 6 | Two local AI profiles on certified HW | profiles + recommender; HW cert pending |
| 7 | Agents bounded by tool policies | Policy Gateway + tests |
| 8 | Document RAG with openable sources | KnowledgeService search returns paths |
| 9 | Content packs verify signatures | Content Manager (alpha unsigned flag) |
| 10 | Model/content licences present | licences.lock.yaml |
| 11 | Update rollback automated tests | updater dry-run + unit coverage TBD |
| 12 | Backup restore on clean hardware | backup_service + integration pending |
| 13 | Recovery media repairs/reinstalls | recovery profile in catalog |
| 14 | OEM image first-run | build-oem-image.sh |
| 15 | Accessibility primary flows | pending UX audit |
| 16 | Source/binary manifest archived | SBOM script |
| 17 | Support redacted diagnostics | logs.bundle.create RPC stub |
| 18 | Legal branding/redistribution review | docs/legal inventory |

Alpha MVTR (§44) is the current engineering target; commercial V1 requires docker.sock removal verification, update signing, and recovery path proof on real hardware.
