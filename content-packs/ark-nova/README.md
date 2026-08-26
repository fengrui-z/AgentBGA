# Ark Nova semantic content packs

The high-fidelity engine loads mechanics-only data from a directory containing
`manifest.json` and the seven JSON collection files declared by that manifest.
See `schemas/ark-nova-content-manifest-v1.schema.json` and
`schemas/ark-nova-card-v1.schema.json`.

Full packs must contain exactly the official base-game counts and pass
`agentbga.ark_nova_official.load_content_pack`.  Locally reviewed packs that
cannot be redistributed belong under `local/`, which is ignored by Git.

This directory must not contain publisher scans, illustrations, card frames, or
substantial verbatim rule/card prose.

## Current M4 draft

`base-en-draft/` is a repository-safe authoring pack, not a released rules pack.
It reserves all 254 board/content component slots. The structured reference import
adds factual records for all 235 animal, sponsor, project, and final-scoring cards,
plus auxiliary indexes for five Action-card faces, 47 ability keywords, and the
255-card physical expansion. Imported effect records remain non-executable until
they are compiled to the closed semantic vocabulary and independently reviewed.

The browser projection is generated from the same validated data:

```sh
PYTHONPATH=src python3 -m agentbga.ark_nova_official.catalog \
  content-packs/ark-nova/base-en-draft web/public/ark-nova-content.json
```

Neither the roster nor the exported browser catalog makes the semantic rules
version runnable. Registration happens only after reviewed scenario coverage
meets the release gate.
