# Kids Home Learning (Atlas)

Offline starter curriculum for home learning. Lessons are ingested into the Atlas
knowledge base on install so local AI tutors can teach without the internet.

## Included (CC BY 4.0 — Atlas-authored)

| Area | Files |
|------|--------|
| Maths | `maths-ages-6-8.md`, `maths-ages-8-10.md` |
| Reading | `reading-ages-6-8.md`, `reading-ages-8-10.md` |
| Science | `science-home.md`, `science-living-things.md` |
| Geography | `geography-world.md`, `geography-weather-climate.md` |
| Habits | `daily-learning-routine.md` |

## Expand bundle (pinned)

After install, Content Manager downloads the expand archive of extra Markdown
lessons and re-indexes them into Knowledge.

| Pin | Value |
|-----|--------|
| On-device (ISO / package) | `file:///usr/share/atlas/content/kids-home-learning-expand.tar.gz` |
| Source tree | `content/packs/education/kids-home-learning-expand.tar.gz` |
| GitHub raw fallback | `https://raw.githubusercontent.com/kaal22/atlas-os/main/content/packs/education/kids-home-learning-expand.tar.gz` |
| Env override | `ATLAS_KIDS_EXPAND_URL` |
| Pack meta | `meta.expand_fetch.url` / `fallback_url` |

Expand lessons live under `kids-home-learning-expand/` (fractions, story structure,
simple machines). Rebuild the tarball with:

```bash
tar -czf content/packs/education/kids-home-learning-expand.tar.gz \
  -C content/packs/education kids-home-learning-expand
./scripts/build-content-packs.sh
```

GitHub Release asset pattern (optional OEM host): publish the same `.tar.gz` as a
release asset and set `ATLAS_KIDS_EXPAND_URL` to that download URL.

Licence: Creative Commons Attribution 4.0.
