# Licensing

STROMBOLI, the volca fm2 beta patch, and its tools are free software under the GNU General Public License, version 3 only
(`GPL-3.0-only`, full text in `LICENSE`). You may use, study, change and share them. If you give someone a firmware
built from them, give them the complete source under the same licence too.

## Who made what

| | |
| --- | --- |
| Everything in this repository: patch sources `src/`, build and test tools (`build_patch.py`, `build_release.py`, `verify_*.py`, `baseline/`, `probability_format.py`, `edit_probability.py`), `release/` scripts, documentation `docs/`, `README.md`, `LEGGIMI.md` | Copyright (C) 2026 Mario Texture, written with the help of Claude (Anthropic) |

## Korg material

No Korg firmware, updater or document is in this repository. The build reads the official
`volca_fm2_updater_0112.zip`, which you download from Korg, and checks its SHA-256. The tools contain only addresses,
a few bytes of the original code at each patched location (to check that the right firmware is being patched) and
hashes. The firmware, the updater and the WAVs built from them are Korg's and fall under Korg's licence agreement:
do not publish them. Distributing modified firmware may not be allowed by that agreement; each user builds the WAVs
for their own instrument.

## Trademarks

"Korg" and "volca" are trademarks of Korg Inc. STROMBOLI is not made or endorsed by Korg.
