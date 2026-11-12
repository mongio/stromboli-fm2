# Licensing

STROMBOLI, the volca fm2 beta patch, and its tools are free software under the GNU General Public License, version 3 only
(`GPL-3.0-only`, full text in `LICENSE`). You may use, study, change and share them. If you give someone a firmware
built from them, give them the complete source under the same licence too.

## Who made what

| | |
| --- | --- |
| Everything in this repository: patch sources `src/`, build and test tools (`build_patch.py`, `build_release.py`, `verify_*.py`, `baseline/`, `probability_format.py`, `edit_probability.py`), `release/` scripts, documentation `docs/`, `README.md`, `LEGGIMI.md` | Copyright (C) 2026 Mario Texture, written with the help of Claude (Anthropic) |

## Korg material

No Korg firmware, updater or document is in the source code of this repository. The build reads the official
`volca_fm2_updater_0112.zip`, which you download from Korg, and checks its SHA-256. The tools contain only addresses,
a few bytes of the original code at each patched location (to check that the right firmware is being patched) and
hashes.

For convenience, the GitHub release has the ready-made update WAVs, as other community volca firmware projects do.
Those WAVs contain Korg's firmware 1.12 with the STROMBOLI patch applied: the Korg part is not covered by the GPL and
remains Korg's, under Korg's licence agreement. The WAVs are offered free of charge, for owners of a volca fm2, for
personal use; they will be removed if Korg asks. If you prefer, build the WAVs yourself from the official updater
(see README) and do not use the release WAVs.

## Trademarks

"Korg" and "volca" are trademarks of Korg Inc. STROMBOLI is not made or endorsed by Korg.
