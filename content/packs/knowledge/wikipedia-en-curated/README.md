# Wikipedia (English) — curated offline pack

This pack gives Atlas agents a **curated, offline Wikipedia-style knowledge set** for RAG,
plus an optional Kiwix ZIM download on install.

## Catalogue SKUs

| Catalogue id | What you get | Approx size |
|--------------|--------------|-------------|
| `atlas.knowledge.wikipedia-en` | Curated Markdown + top-100 nopic ZIM (starter) | ~13 MB ZIM |
| `atlas.knowledge.wikipedia-en-mini` | Full English mini ZIM | ~12 GB |
| `atlas.knowledge.wikipedia-en-nopic` | Full English nopic ZIM | ~49 GB |
| `atlas.knowledge.wikipedia-en-maxi` | Full English maxi (with media) | ~115 GB |

Install from Command Centre → **Content** → **Knowledge for agents**. Large SKUs
require a confirm dialog (`confirm_large`) before download.

## What starter install does
1. Indexes Markdown under `articles/` into the shared knowledge base (`knowledge.search`).
2. Downloads the default English top-100 ZIM (~13 MB, no pictures) into the pack target and
   registers it with Kiwix Serve — same async pattern as map tile fetch.
3. Override with `ATLAS_ZIM_URL` / `ATLAS_ZIM_NAME`, or set catalogue `zim_fetch.url`.

## Locked ZIM URLs (`release/sources.catalog.yaml`)
- Starter: `wikipedia_en_100_nopic_2026-04.zim`
- Mini: `wikipedia_en_all_mini_2026-06.zim`
- Nopic: `wikipedia_en_all_nopic_2026-06.zim`
- Maxi: `wikipedia_en_all_maxi_2026-02.zim`

Do **not** commit multi-GB ZIMs to git. Use Content Install, USB, or
`scripts/fetch-wikipedia-zim.sh mini|nopic|maxi` into `/srv/atlas` / pack staging.

Licence: article text derived from Wikipedia is CC BY-SA 4.0 / GFDL — see licences/.
