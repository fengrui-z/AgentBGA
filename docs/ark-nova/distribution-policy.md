# Ark Nova semantic-content distribution policy

AgentBGA code is MIT-licensed.  That license covers project-authored code and
data only; it does not grant rights to third-party art, scans, graphic design, or
publisher prose.

## Repository-safe content

The public implementation may contain:

- rules mechanics expressed as code;
- stable internal IDs and publisher reference numbers;
- factual numeric values and icon relationships after distribution review;
- typed conditions and effects;
- project-authored concise summaries generated from those semantics;
- original CSS/SVG presentation and appropriately licensed icons.

It must not contain:

- scanned cards, boards, maps, or rulebook pages;
- copied card frames or publisher illustrations;
- substantial verbatim card, glossary, or rulebook prose;
- third-party fonts or icons without a compatible license and notice.

## Content-pack boundary

The engine must support separately installed content packs.  Until distribution
rights for a complete high-fidelity pack have been reviewed, the public repository
continues to ship the research pack while an official semantic pack may be loaded
locally and excluded from Git.  Optional local art packs are never required for
rules execution and are never distributed by default.

Every content-pack manifest declares its license/provenance status and a content
hash.  Hosted deployments must not expose a pack whose manifest disallows public
distribution.
