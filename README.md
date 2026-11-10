# Republika Srpska: law history in git

Part of [lexifina/global-law](https://github.com/lexifina/global-law), one git history for every country's law: this is the law of Republika Srpska, Bosnia and Herzegovina, which global-law reads at `bosnia-and-herzegovina/republika-srpska/acts/`.

The law of Republika Srpska, one of the two entities of Bosnia and Herzegovina, as a git history: one file per article, one commit per change, dated the day it took effect. `git log` lists every change to an article; checking out a date gives the text in force that day.

It follows the shared design of [lexifina/global-law](https://github.com/lexifina/global-law), which places it at `ba-srp/`. The state's own law is in [lexifina/bosnia-and-herzegovina-law](https://github.com/lexifina/bosnia-and-herzegovina-law); the Federation's in [lexifina/bosnia-federation-law](https://github.com/lexifina/bosnia-federation-law).

The text is in Serbian, in Cyrillic script, exactly as the National Assembly publishes it.

## What this repository holds

| Folder | Act | Versions | History |
| --- | --- | ---: | --- |
| `ustav/` | Устав Републике Српске (Constitution of Republika Srpska) | 1 | current text only: the oldest version available |
| `zakon/<year>/sg<issue>-<id>/` | Laws of the National Assembly, as adopted and published in Службени гласник Републике Српске, 2004 onwards | 1 each | as enacted |

Every law is listed, with its status, in [registry/ACTS.md](registry/ACTS.md) and [registry/data/acts.json](registry/data/acts.json); [registry/REPRODUCE.md](registry/REPRODUCE.md) says how they were built. Each law is held as enacted: a law amended since is labelled `amended, not consolidated` and names the amending acts (`amended_by` in acts.json), and one the register records as no longer in force, or no longer lists, is labelled `repealed, not consolidated`. Neither has a consolidated text here.

## Freshness

Every version names the official page it was read from (the commit's `Source:` and `Consolidated:` trailers; `portal` in registry/data/acts.json), so every act can be checked against its source.

<!-- freshness-summary -->
Checked against the official sources: 2026-11-10; 100% of acts verified in the last 7 days, 100% in the last 30 ([data/freshness.json](data/freshness.json)).
<!-- /freshness-summary -->

`python tools/freshness.py <act>` gives an act's status, its last check and the official link; `python tools/freshness.py --summary` the overall picture. An act is checked by reading its record in the gazette publisher's Electronic Register of Regulations (eRP, <https://erp.slglasnik.org/>): whether it is still in force and which later acts amend, correct or repeal it. The check runs daily and re-reads every act within 7 days; [data/status.json](data/status.json) says whether updates are running and when each official source last answered. Statuses (`current`, `pending-change`, `stale`, `unverified`, `source-unavailable`) and columns are explained in [data/freshness.json](data/freshness.json); a labelled act is `pending-change`.

Laws of the National Assembly that are not here are listed, each with its reason, in [data/held.json](data/held.json); laws published but not yet in force in [data/pending.json](data/pending.json).

New laws are fetched and appended by the same daily run. The National Assembly's robots.txt asks robots not to fetch `.zip` files (its law texts) and to wait 3 seconds between requests; Lexifina treats it as advisory and reads that site one request every 3 seconds.

## Sources

- The National Assembly of Republika Srpska (Народна скупштина Републике Српске), <https://www.narodnaskupstinars.net/ci/akti/usvojeni-zakoni>: the adopted text of each law (signed by the Assembly's President), and <https://www.narodnaskupstinars.net/ci/akti/ustav>: its consolidated text of the Constitution, which incorporates the amendments published in Службени гласник Републике Српске 21/92 (consolidated text), 28/94, 8/96, 13/96, 15/96, 16/96, 21/96, 21/02, 26/02, 30/02, 31/02, 69/02, 31/03, 98/03, 115/05, 117/05 and 48/11.
- JU Службени гласник Републике Српске: each gazette issue's date and contents (<https://online.slglasnik.org/sr/pregled>) and the Electronic Register of Regulations (<https://erp.slglasnik.org/>).

## Dates

- A law takes effect on the day its own final article names, almost always the eighth day after its publication, counted from the issue date the gazette publisher gives.
- The Constitution has one version, dated 9 March 2017, the date of the National Assembly's published file. The source gives no date for the consolidation itself, so this is the oldest version available, not the date the text first took effect.
- Each commit is dated at noon, Europe/Sarajevo.

## Files

`ustav/clan-001.md` is Члан 1., `clan-138-a.md` Члан 138а.; `preambula.md` holds the title and preamble. Chapter headings stay in the file of the first article after them. `napomene.md` keeps the footnotes of the consolidated text, which name the amendment behind each provision. Footnote markers are left out of the article text. One paragraph per line. A law's folder holds one file per article (`clan-001.md`), its preamble (`uvod.md`) and its headings.

## How it is checked

- Every version is read back from git on the day it took effect and on the day before (`tools/check_repo.py`, `registry/tools/build/check_repo.py`); both must match the corpus.
- Each law's in-force day is read again from its final article and the gazette issue date, and its publication day compared with the gazette publisher's.
- Every paragraph of the Constitution is found, in order, in the source PDF as read by a second, independent PDF reader; the only differences are footnote markers.
- Health checks: no merge commits, commit dates never go backwards, nothing dated in the future, and every commit's trailers parse.

## Limits

This is not an official publication. The binding text is the one published in Службени гласник Републике Српске. The consolidated text of the Constitution has no official force of its own, and its history starts with the oldest version available. Laws are held as enacted; amendments are named, not applied. Laws before the National Assembly's list begins (December 2003) have no free official text and are not here; data/held.json lists them.
