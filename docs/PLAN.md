# Atlas OS — phased plan (working summary)

Canonical backlog checkboxes: [`docs/BACKLOG.md`](BACKLOG.md).

## Decision: Command Centre on `:8787`

**Ship direct Command Centre on `http://127.0.0.1:8787/`.**  
`atlas-proxy` (nginx on loopback `:80` → `:8787`) is **optional compatibility** only.

| Surface | Canonical | Notes |
|---------|-----------|--------|
| Desktop launchers / `atlas-open-command-centre` | `:8787` | Never default to portless `:80` |
| `atlas-launcher` status UI link | `:8787` via `ATLAS_COMMAND_CENTRE_URL` | `/etc/atlas/atlas.conf` |
| Firewall (`network_modes.py`) | opens **8787** in trusted LAN | Not port 80 |
| `atlas-proxy` | optional | Present for older bookmarks / evidence scripts |

## Milestones

### Milestone 1 — Ship polish (updates + branding path) — **done in-tree**

1. `:8787` canonical — documented; launchers/docs/firewall aligned; proxy marked optional.
2. Wallpaper path — SDDM `theme.conf.user`, stronger `set-wallpaper.sh` (wait/retry), autostart phase; verify checklist in BACKLOG (ISO boot still required to confirm visually).
3. Stable refuses unsigned — `atlas-updater` rejects `DEV-UNSIGNED-PLACEHOLDER` / missing sig on stable/release unless `ATLAS_ALLOW_UNSIGNED=1`; keys dir + SIGNING_PLAN install path; `atlas-apply-update.py` no longer forces unsigned.
4. CC update UX — channel, from→to version, clearer apply/rollback/signature errors.
5. Unit tests — `tests/unit/test_updater_signing.py` (+ existing updater tests).
6. Docs — this plan + BACKLOG M1 status.

### Milestone 2+ (out of M1)

- Kolibri / Khan catalogue channels  
- ZIM HTML → agent RAG  
- Map zoom > 11 / denser extracts  
- Plymouth / deeper theme polish  
- Signed APT / appliance update channel beyond GitHub Releases MVP  
- Final ISO cut (`scripts/phase7-iso.sh`) with full boot checklist  

## Related product phases

Product build order remains in `product.md` (§ Phase 7 updates/backup, Phase 8 OEM). M1 is the near-term engineering slice for signed updates + `:8787` + wallpaper wiring before the final ISO.
