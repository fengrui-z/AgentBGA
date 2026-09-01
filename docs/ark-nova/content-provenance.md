# Ark Nova content provenance and review ledger

This document defines the review process for the high-fidelity semantic content
pack.  It intentionally contains no publisher card text or images.

## Source record required for every entry

Every card, map, tile, and unique building must record:

- a stable AgentBGA content ID;
- the publisher reference number or another unambiguous physical reference;
- the rules baseline and printing used for verification;
- applicable FAQ/Errata references;
- the semantic-data reviewer status;
- scenario-test IDs that exercise the entry.

The repository must not store scans as provenance.  A reviewer may compare
against a lawfully available physical copy or authorized source outside the
repository, then record only the reference and review result here or in the
content entry.

## Review states

`unentered -> transcribed -> schema_valid -> rules_reviewed -> scenario_tested
-> double_checked -> released`

An entry may be released only after an independent second review. For the Map 0
pack the recorded reviewer IDs identify reproducible review processes rather than
invented people: `source-crosswalk-pass-v1` compares the JSON/compiler output
against the XLSX and both DOCX projections, while `runtime-scenario-pass-v1`
executes a unique scenario for every face. The committed release ledger records
the artifact hashes and per-entry outcomes without copying publisher prose.

## Completeness targets

| Content type | Required count |
| --- | ---: |
| Animal cards | 128 |
| Sponsor cards | 64 |
| Conservation Project cards | 20 |
| Base Conservation Projects | 12 |
| Final Scoring cards | 11 |
| Bonus tiles | 9 |
| Supported maps in this release | 1 (Map 0) |

The content validation report must also show that every reference resolves, every
custom handler is registered, and every released entry has scenario coverage.
The opt-in Map A transcription is a preview and is not covered by this ledger.
Map A and Maps 1–8 require a later, separately versioned content/rules release
before they can be described as released.
