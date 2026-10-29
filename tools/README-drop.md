# Drop a PDF into PenWorks (for a Claude session on this laptop)

- Command: `python tools/drop_pdf.py "C:\path\to\Some sheet.pdf"` (run from the penworks folder; any path with spaces or Afrikaans letters works).
- It makes a NEW note in **Loose** unless you add `--folder "Grade 12"` (a top folder) or `--folder "Grade 9/Term 1"` (a sub-folder). Case does not matter. An unknown folder lists the folders and writes nothing.
- `--name "Michaela G1 to G8"` names the note; without it the note is named after the file, without `.pdf` (at most 120 letters).
- `--test` uses the throwaway login `droptest` instead of Megan's. Every test uses `--test`; only a real drop she asked for goes without it.
- The login lives in `penworks\.env` (PW_USER / PW_PASS, PW_TEST_USER / PW_TEST_PASS). It is gitignored: never commit it, never print it.
- Limit: 50 MB per PDF (the storage bucket's limit). A bigger file, a broken one or one with a password is refused before anything is written.
- It prints one line: `Dropped "Some sheet" (12 pages) into Loose as note <id>`. Her tablet and phone show it within seconds.
- Exit codes: 0 done, 1 sign-in or internet trouble, 2 bad arguments (no file, not a PDF, too big, unknown folder).
- Checks: `python tests/test_drop.py` (no internet needed) and `python tests/test_drop.py --live` (droptest only, cleans up after itself).
