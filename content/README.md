# Atlas content packs

Offline maps, knowledge, and education packs use the `.atlas-pack` format
(`content/schemas/atlas.pack.v1.json`).

## Build

```bash
./scripts/build-content-packs.sh              # default countries + kids + Wikipedia
./scripts/build-content-packs.sh --all-maps   # every country in maps/countries.json
./scripts/fetch-wikipedia-zim.sh starter|mini|nopic|maxi  # optional ZIM fetch help
./scripts/fetch-country-pmtiles.sh uk         # optional: download country PMTiles, then rebuild
```

Outputs land in `dist/packs/` and are staged under:

- `packages/atlas-content-manager/usr/share/atlas/packs/`
- `config/includes.chroot/usr/share/atlas/packs/` (when writable)

Catalogue copies:

- `content/catalogues/catalogue.json`
- `packages/atlas-content-manager/usr/share/atlas/catalogue.json`

## Pack families

| Category | Examples | Install workflow |
|----------|----------|------------------|
| Maps | `atlas.maps.uk`, `atlas.maps.us`, … | `maps.reindex` → `/srv/atlas/maps/<cc>/` + online PMTiles fetch |
| Education | `atlas.education.kids-home` | `knowledge.index` → RAG ingest (rich offline starter); optional `ATLAS_KIDS_EXPAND_URL` |
| Knowledge | `atlas.knowledge.wikipedia-en` (starter) | `knowledge.index` → RAG + async top-100 ZIM (~13 MB) |
| Knowledge | `atlas.knowledge.wikipedia-en-mini` | stub + async full mini ZIM (~12 GB, `confirm_large`) |
| Knowledge | `atlas.knowledge.wikipedia-en-nopic` | stub + async full nopic ZIM (~49 GB, `confirm_large`) |
| Knowledge | `atlas.knowledge.wikipedia-en-maxi` | stub + async full maxi ZIM (~115 GB, `confirm_large`) |

**Starter** (`atlas.knowledge.wikipedia-en`): curated Markdown is indexed for agents; install
also downloads English top-100 nopic ZIM into `/srv/atlas/knowledge/packs/wikipedia-en`.

**Large SKUs** (mini / nopic / maxi): Content UI lists them under Knowledge; install requires
`confirm_large` (same pattern as large map packs), then async-downloads the locked Kiwix URL
from `release/sources.catalog.yaml` into `/srv/atlas/knowledge/packs/wikipedia-en-{mini,nopic,maxi}`.

Skip with `ATLAS_ZIM_SKIP_FETCH=1`. Operator CLI:
`./scripts/fetch-wikipedia-zim.sh starter|mini|nopic|maxi` then
`./scripts/build-content-packs.sh --knowledge-only` for the starter pack only
(large ZIMs are never embedded in git packs).

### Offline maps (PMTiles)

Country stubs ship without multi-GB tile archives. On **Install** in Command
Centre (or `install_pack`), Atlas downloads a **Protomaps** basemap extract for
the country bounding box (ODbL — © OpenStreetMap contributors) into
`/srv/atlas/maps/<cc>/<cc>.pmtiles`, then reindexes. After that, tiles work
fully offline.

- Default max zoom: **11** (`ATLAS_PMTILES_MAXZOOM` to override; each level ~2× size)
- Planet source: daily builds at `https://build.protomaps.com/YYYYMMDD.pmtiles`
  (override with `ATLAS_PMTILES_PLANET_URL`, or set `ATLAS_PMTILES_URL` for a
  finished country file)
- Skip network fetch: `ATLAS_MAPS_SKIP_FETCH=1`
- Large countries (us, ca, br, in, au, …) may be multi-GB — the UI asks for confirm
- Operator pre-fetch (like Wikipedia ZIM):

```bash
./scripts/fetch-country-pmtiles.sh ie
# writes content/packs/maps/ie/ie.pmtiles — rebuild embeds it in the pack
./scripts/build-content-packs.sh --maps-only
```
