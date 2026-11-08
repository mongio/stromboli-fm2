# reference/

Put here the **official Korg volca fm2 System Updater 1.12**, unchanged:

    reference/volca_fm2_updater_0112.zip

Download it from Korg: <https://www.korg.com/us/support/download/software/0/892/4964/>
(file `volca_fm2_updater_0112.zip`, 2023-07-10). The build checks its SHA-256 and stops if
it is a different file.

Nothing from Korg is stored in this repository, and nothing built from it may be committed
(`.gitignore` keeps `*.zip`, `*.bin`, `*.wav` out).

Optional: images of earlier betas (`installed_beta_1_13_logical.bin` … `_1_18_`), if you
have them, enable the upgrade tests from those versions in `verify_release.py`.
