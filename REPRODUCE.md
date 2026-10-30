# How this repository was made (Republika Srpska)

This file is written by the build on 2026-10-30, the day the source data was retrieved.

## Sources

| Source | Address | Retrieved | Licence |
| --- | --- | --- | --- |
| Narodna skupština Republike Srpske: Устав Републике Српске (consolidated text, PDF) | <https://www.narodnaskupstinars.net/sites/default/files/upload/dokumeti/kodeks/ustav_republike_srpske.pdf> | 2026-10-30 | Official text, not protected: Zakon o autorskom i srodnim pravima BiH (Sl. glasnik BiH 63/10), čl. 8(1)(b) |

Every word of law in this repository comes from these sources. Lexifina reads them and records each act's dated versions, and the laws that made each change, in one corpus file. This repository is built from that file.

## What is in it

| Act | Title | Versions | Span |
| --- | --- | ---: | --- |
| `ustav` | Устав Републике Српске | 1 | 2017-03-09 to 2017-03-09 |

The build made 1 commits:

| Commits | Kind |
| ---: | --- |
| 1 | first version of an act |
| 0 | one law on its in-force day |
| 0 | changes no amendment note explains, credited to the publisher |

Other counts:
- 0 commits on the branch `buducnost`: laws not yet in force on 2026-10-30.
- 0 commits dated 1 January 1970: in force before 1970, with the real day in their `In-force` trailer.
- 17 laws in the record.
- 1 tags.

## Dates

Each commit is dated at noon (Europe/Sarajevo) on the day the change took effect. The other dates, enacted and published, are trailers.

When a law gives no date of its own, the default rule applies: An act takes effect on the day it names, most often the eighth day after its publication in Službeni glasnik Republike Srpske. https://www.narodnaskupstinars.net/ci/akti/ustav

## How the history is built

`tools/build.py` turns the corpus into this history in one pass: one commit per law, on the day it took effect. The same corpus always gives the same commit hashes. `tools/check_repo.py` reads every version back from git and compares it with the corpus. `tools/on.py` shows the law as it stood on any date. The corpus format is described in `tools/SCHEMA.md`.

- Corpus: sha256 `3cb21c8a0a1ebae645bacae6571a988092c6b2a14609fef256d2810790a9e73e` (138914 bytes).
- Builder blob hashes (`git hash-object`): `build.py` `a97ff7ea62c3c7595c5668a297d533da0b74373c`, `check.py` `3e59cb6f05eccb94a9ec14431a7f6781221e83ef`, `on.py` `644a6c0857fbcc72562032b58d57aa113fee0641`.
- Python 3.12.10; git version 2.46.0.windows.1.

## Checks

1 versions of 1 acts read back from git on the day each took effect and on the day before: 0 mismatches. Trailers: 0 commits whose trailers git cannot parse. Health: 0 merge commits on main, 0 commit dates that go backwards, 0 commits dated after the build.

No second build of this corpus has been compared yet.

## Decisions made by hand

- Republika Srpska Constitution: one version, the National Assembly's consolidated text (amendments to Službeni glasnik RS 48/11), dated 2017-03-09, the creation date of the published file, as the oldest version available; the source gives no date for the consolidation itself.
- The text is kept in Cyrillic, as the National Assembly publishes it.
- Footnote markers are dropped from the article text; the footnotes themselves (which name the amendment behind each provision) are kept, in order, in ustav/napomene.md.
- Chapter headings stay in the file of the first article after them; running headers and page numbers are dropped.

## What AI did and did not do

The scripts that read the sources and build this repository were written by Claude Code running Claude Opus 5.5 (`claude-opus-5-5`) under Lexifina's direction.

No model wrote, translated or corrected legal text. No model runs at build time. Every word of law in this repository comes from the official sources above.

The commit messages are written by `build.py` from the source data.

Model use at data-build time:
- none: the text is read from the PDF text layer by a deterministic parser; no model output is legal text.
