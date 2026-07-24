# Third-party licence inventory (Phase 0)

See `release/licences.lock.yaml` for machine-readable decisions.

## Redistribution blockers to clear before commercial V1

1. Confirm Redis tag licence (RSALv2/SSPL vs BSD) at lock-refresh.
2. Revisit Oracle MySQL redistribution for commercial OEM images; consider MariaDB if needed.
3. Per-channel Kolibri content licence audit before bundling education packs.
   - **Alpha (2026-07):** Khan Academy EN US (`c9d7f950ab6b5a1199e3d6c10d7f0103`),
     CK-12 (`1d8f6d84618153c18c695d85074952a7`), and Inclusive Home Learning
     (`378cf4128c854c2795c100b5aca7a3ed`) are **locked as operator-import** catalogue
     SKUs only — channel media is **not** redistributed in git or the core ISO.
     See `content/packs/education/kolibri-channels/CHANNELS.lock.yaml` and
     `release/licences.lock.yaml` entries `kolibri-channel-*`.
4. Wikipedia ZIM: ship only as signed packs with CC-BY-SA / GFDL attribution UI.
5. Map packs: OSM ODbL attribution in Command Centre and pack manifests.
6. Product name / trademark clearance (branding-config only until cleared).

## Alpha stance

Alpha ISOs may include components marked `approved_for_alpha_*` while commercial
redistribution decisions remain open, provided `licences.lock.yaml` records the status.

Kolibri channel packs on alpha are **prepare/import metadata only**
(`operator_may_import_not_bundled`). Do not treat catalogue install as permission
to redistribute Khan/CK-12 media inside Atlas images without a separate commercial
clearance.
