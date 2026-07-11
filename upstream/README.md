# Upstream Project N.O.M.A.D.

This directory holds the **read-only** pinned upstream source after fetch:

```bash
# On lock-refresh host:
curl -L -o build-cache/source/project-nomad-v1.33.0.tar.gz \
  https://github.com/Crosstalk-Solutions/project-nomad/archive/refs/tags/v1.33.0.tar.gz
tar -xzf build-cache/source/project-nomad-v1.33.0.tar.gz -C upstream/
# Expect upstream/project-nomad-1.33.0 or similar; rename/sync to upstream/project-nomad/
```

Atlas modifications live only in:

- `upstream/patches/`
- `upstream/adapter/`

Do not edit files under `upstream/project-nomad/` except via the rebase process.
