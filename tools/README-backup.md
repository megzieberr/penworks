# PenWorks backup

Every night at 20:00 the laptop copies all of PenWorks into `penworks\backup\`. It only reads from
PenWorks; it never changes anything there. A missed night runs at the next chance.

## What it keeps
- `notes\<note id>\` one file per version of each note: the note, all its pages (Bin pages and stickies
  too) and every stroke. A new version only when the note changed. Notes deleted in PenWorks stay here for ever.
- `tree\` the folder list, notes and pages as they were each night.
- `files\imports\` every PDF and picture she imported. `files\snapshots\` the newest picture of every page.
- Old versions: everything from the last 30 days, then one a month. The newest version of a note is never removed.
- `INDEX.md` every note ever seen: live, in the Bin, or gone from PenWorks.
- `LAST-RUN.txt` one line: OK or FAILED and why. `backup.log` the same line for every night.

## Run it by hand
From the `penworks` folder: `python -E -P tools\backup.py`
Exit 0 = good, 1 = could not sign in or reach PenWorks, 3 = the self-check found a mismatch.
The login comes from `.env` (PW_USER, PW_PASS).

## Check it
`python -E -P tools\backup.py --check` opens every note version and checks every PDF and picture is here.
It works offline.

## Find an old note
`python -E -P tools\backup.py --find "words from the name"` lists matching notes, their folder and state,
and for each page: stroke count, the page picture and the PDF page. Or look the name up in `INDEX.md`.

## Second copy
`--mirror "<folder>"` copies new files into that folder after a good run (never deletes there). Setting
`PW_BACKUP_MIRROR=<folder>` in `.env` does the same every night. It is off for now.

## Scheduled task
`tools\backup_task.ps1` registers the "PenWorks Backup" task (run it once, by hand).

To bring a note back from these files, use `tools\restore.py` (see `README-restore.md`): it makes a new copy, never overwrites.
