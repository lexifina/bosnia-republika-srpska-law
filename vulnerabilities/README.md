# Vulnerabilities in Republika Srpska law

**This is a placeholder.** The checks have not been run over this repository yet.

The vulnerability detectors in [lexifina/global-law](https://github.com/lexifina/global-law/tree/main/vulnerabilities) look for mechanical mistakes in legislation: a rule still applied "until" a date that has passed, a provision repealed before its replacement took effect, two amendments to one provision on one day, a rule in force before it was published, a reference to an article that no longer exists.

When they are run over this repository, this folder will hold, as [serbia-law's](https://github.com/lexifina/serbia-law/tree/main/vulnerabilities) does: every flag (`data/flags.csv`, one row per provision and problem), the strongest flags reviewed by a language model with the case for and against (`data/reviewed.csv`), the counts by category (`data/by_category.csv`), the scripts used (`tools/`), and every flag that survives review checked by hand in this repository's history and texts.

A flag is a prompt to look, not legal advice, and none of it will have been tested in court.
