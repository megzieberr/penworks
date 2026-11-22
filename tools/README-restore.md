# PenWorks restore

Brings ONE note back from the nightly backup (`penworks\backup\`) as a NEW note called
"<its name> (restored)". It never changes or deletes anything that is already in PenWorks, and it
only reads the backup.

## Find the note
From the `penworks` folder: `python -E -P tools\restore.py --list "words from the name"`
It works offline and shows each matching note: name, folder, live / in the Bin / gone, the newest
backup, and every saved version (a stamp like `20261121T180012Z`) with its page and stroke counts.

## Look first (a dry run)
`python -E -P tools\restore.py "words from the name"` (or the note id from `--list`)
It signs in, then says what it would make: the folder, the name, the pages, the strokes and the
files it would upload. Nothing changes.

## Make it
Add `--go` to the same line. Then it reads the new note back and says Done, or says what did not match.

## Options
- `--stamp <stamp>` an older version (default: the newest).
- `--folder "Grade 9/Term 1"` where it goes when its own folder is gone or in the Bin. Use `--folder Loose`
  for Loose. If its own folder is still there, it always goes back there.
- `--with-bin` also bring back the pages and stickies that were in the note's own Bin.
- `--env <file>` another login file (default `.env`, PW_USER and PW_PASS).

## What comes back
Every page in order, with its paper, orientation, bookmark and PDF page; every stroke and picture;
every sticky on its own page. PDFs and pictures still in PenWorks are used as they are; ones that are
gone go up again from `backup\files\imports`. Page pictures (snapshots) are not copied: PenWorks
makes new ones when the note is opened.

Exit 0 = done (or a dry run), 1 = could not sign in or reach PenWorks (if that happens part way, it
names the half-made new note: put that one in the Bin and run it again), 2 = refused (nothing written),
3 = a check failed.
