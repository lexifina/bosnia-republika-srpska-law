# Republika Srpska: law history in git

Part of [lexifina/global-law](https://github.com/lexifina/global-law), one git history for every country's law: this is the law of Republika Srpska, Bosnia and Herzegovina, which global-law reads at `bosnia-and-herzegovina/republika-srpska/acts/`.

The law of Republika Srpska, one of the two entities of Bosnia and Herzegovina, as a git history: one file per article, one commit per change, dated the day it took effect. `git log` lists every change to an article; checking out a date gives the text in force that day.

It follows the shared design of [lexifina/global-law](https://github.com/lexifina/global-law), which places it at `ba-srp/`. The state's own law is in [lexifina/bosnia-and-herzegovina-law](https://github.com/lexifina/bosnia-and-herzegovina-law).

The text is in Serbian, in Cyrillic script, exactly as the National Assembly publishes it.

## What this repository holds

| Folder | Act | Versions | History |
| --- | --- | ---: | --- |
| `ustav/` | Устав Републике Српске (Constitution of Republika Srpska) | 1 | current text only: the oldest version available |

## Source

The National Assembly of Republika Srpska (Народна скупштина Републике Српске), <https://www.narodnaskupstinars.net/ci/akti/ustav>: its consolidated text of the Constitution, which incorporates the amendments published in Службени гласник Републике Српске 21/92 (consolidated text), 28/94, 8/96, 13/96, 15/96, 16/96, 21/96, 21/02, 26/02, 30/02, 31/02, 69/02, 31/03, 98/03, 115/05, 117/05 and 48/11.

## Dates

- The Constitution has one version, dated 9 March 2017, the date of the National Assembly's published file. The source gives no date for the consolidation itself, so this is the oldest version available, not the date the text first took effect.
- Each commit is dated at noon, Europe/Sarajevo.

## Files

`ustav/clan-001.md` is Члан 1., `clan-138-a.md` Члан 138а.; `preambula.md` holds the title and preamble. Chapter headings stay in the file of the first article after them. `napomene.md` keeps the footnotes of the consolidated text, which name the amendment behind each provision. Footnote markers are left out of the article text. One paragraph per line.

## How it is checked

- Every version is read back from git on the day it took effect and on the day before (`tools/check_repo.py`); both must match `corpus.json`.
- Every paragraph's letters and digits are found, in order, in the source PDF as read by a second, independent PDF reader; the only differences are footnote markers.
- Health checks: no merge commits, commit dates never go backwards, nothing dated in the future, and every commit's trailers parse.

## Limits

This is not an official publication. The binding text is the one published in Службени гласник Републике Српске. The consolidated text has no official force of its own. The history starts with the oldest version available. Laws are not included yet.
