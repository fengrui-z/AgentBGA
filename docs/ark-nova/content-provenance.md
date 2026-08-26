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

An entry may be released only after an independent second review.  Reviewers
compare a renderer-generated summary and the structured facts against the source;
they must not validate an entry merely by comparing it with another transcription.

## Completeness targets

| Content type | Required count |
| --- | ---: |
| Animal cards | 128 |
| Sponsor cards | 64 |
| Conservation Project cards | 20 |
| Base Conservation Projects | 12 |
| Final Scoring cards | 11 |
| Bonus tiles | 9 |
| Beginner maps | 2 |
| Advanced maps | 8 |

The content validation report must also show that every reference resolves, every
custom handler is registered, and every released entry has scenario coverage.

