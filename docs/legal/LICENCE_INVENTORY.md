# Third-party licence inventory (Phase 0)

See `release/licences.lock.yaml` for machine-readable decisions.

## Redistribution blockers to clear before commercial V1

1. Confirm Redis tag licence (RSALv2/SSPL vs BSD) at lock-refresh.
2. Revisit Oracle MySQL redistribution for commercial OEM images; consider MariaDB if needed.
3. Per-channel Kolibri content licence audit before bundling education packs.
4. Wikipedia ZIM: ship only as signed packs with CC-BY-SA / GFDL attribution UI.
5. Map packs: OSM ODbL attribution in Command Centre and pack manifests.
6. Product name / trademark clearance (branding-config only until cleared).

## Alpha stance

Alpha ISOs may include components marked `approved_for_alpha_*` while commercial
redistribution decisions remain open, provided `licences.lock.yaml` records the status.
