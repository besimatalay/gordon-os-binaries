# Upstream: `wiebow/tetris.c64`

"Tetris for the CBM64 in 6502 Assembly" by Wiebo de Wit. This is a **verbatim
clone**, kept as the porting reference for GordonOS's own port, **`gortris`**
(task `gortris.tsk`, source `src/tasks/dynamic/gortris.asm` + `gortris.inc` —
the name is the GordonOS pun on "Gort", not a typo for `tetris`).
**Nothing in this folder is built, imported or linked** — it is reference
material, exactly like `reference/ehbasic-original.asm` and `filesys.asm`.

| | |
|---|---|
| Repository | https://github.com/wiebow/tetris.c64 |
| Commit | `d15f86f62060d09323a7c30c20a422d58f6ed3a4` |
| Commit date | 2017-01-29 |
| Commit subject | cleanups and added load/save |
| Licence | **MIT** — Copyright (c) 2015 Wiebo de Wit (full text in `README.md`) |
| Toolchain | KickAssembler + CharPad |

The nested `.git` was removed on 2026-09-13 so these files are ordinary tracked
files of this repository — a nested repo is invisible to the outer one, which is
the opposite of keeping track of anything. The commit above is the exact
revision being ported; re-cloning the URL restores the history if ever needed.

## What we port

The **game logic only**, re-expressed for GordonOS's bitmap display, its
REU-backed per-task surfaces and its 60 Hz scheduler:

| File | Role |
|---|---|
| `blocks.asm` | the seven tetrominoes and their rotated forms |
| `play.asm` | the play-mode state machine, and its level rule (10 lines a level, `delayChange` = 4 off the drop delay, a line score × (level+1)) |
| `lines.asm` | full-row detection and clearing |
| `gameover.asm` | the game-over animation: fill the well with a block, one row per update (`drawCharacter` = 105, `linesLeft` = 19), clear it the same way with a space, then print the text. Ported whole, in the same bottom-up order and at the same 20 frames a pass — ours differs only in the glyph (one 8-byte block instead of a charset tile), the colour, and the text: the reference draws a 10×20 `WELL_GAMEOVER` map **inside the well**, which is artwork, so the port draws the words with the kernel's font in the same place instead (rows 12 and 14, at the well's own left column) |
| `attract.asm`, `levelselect.asm`, `main.asm` | the mode machine: the attract loop (3 screens + the select screen on `ATTRACT_DELAY` = 254 frames), the level grid (its `levelX`/`levelY` — five columns at 16,18,20,22,24 on rows 7 and 9) with the `FLASH_DELAY` = 18 digit flash, then play and game over |
| `scores.asm`, `random.asm` | scoring, and the piece selector's randomness |
| `hi-scores.asm`, `entername.asm`, `controlled_input.asm`, `file_load.asm` / `file_save.asm` | the hi-score table: three entries of `TABLE_NAMELENGTH` (7) name cells and three BCD score bytes, most significant first (its `TABLE_ENTRIES`/`ENTRY_LENGTH` layout kept byte for byte), seeded with three house scores rather than its own `$01` fill: that fill reads as a score of BCD 010101 named "AAAAAAA", which looks like corrupted memory AND needs ~250 cleared lines at level 0 to beat, so a first session could never take a row, checked at game over and shown on the select screen. What changed is the storage and the editor: the table is saved to the REU FS (`gortris.hi`, 30 bytes) instead of KERNAL `LOAD`/`SAVE`, and the name is typed by the port's own yielding editor because the kernel's `kReadString` spins without yielding: it types straight into the 7-cell field (placeholders are dots, and DEL puts the dot back, as its `CONTROLLED_INPUT` does), and the cursor is the KERNEL's blinking block (`kEnableCursor`) rather than its static reverse-video underscore — the blink follows the live cursor, so an editor that yields gets it for free. One trap worth repeating: a key from `kReadKey` is a SCREEN CODE, so the letters are `$01-$1A` and a "printable = `>= $20`" test throws every one of them away (it made the port's first editor untypable). The table sits at rows 19-21 rather than its 14-16 — the port's select screen has its key list where the reference has room — but the columns are its own (table column 14, name column 21). Saving is find → delete → save, because `kReuSave` refuses a duplicate name and the FS's delete is a tombstone |
| `screens.asm`, `input.asm` | redrawn: kernel font/glyphs, `kReadKey`/`kScanKeyboard`. Its **joystick** path (`GetJoyInput`, port 2) is ported whole — same mapping (UP = rotate CCW, DOWN = drop, LEFT/RIGHT = move, FIRE = rotate CW and confirm) and same "keyboard first, stick only if the keyboard had nothing" order — though it is untested here (no stick in the development setup). Its **repeat tuning** is ported too: `INPUTDELAY` (10 frames before a held key or direction repeats) with the shorter delay for DOWN, halved from the one number the player sets on the select screen with `-`/`+` |
| — | **three additions, ours:** SPACE is a **hard drop** — down to the floor, settle at once, 2 points a row (the reference has no such move: its `DOWN`, on ENTER, is one row at a time and 1 point); `q` leaves the task, which the reference's world has no equivalent of and a task on a multitasking OS needs; and `m` mutes the music from any screen (ours too — the reference hands the chip to a one-shot SID player it cannot stop, while this port owns the player it starts). The port's attract screens also show for 4× its `ATTRACT_DELAY`, because its screens are art to glance at and ours are text to read. |

## What we do NOT port, and why

- **`file_load.asm`/`file_save.asm`'s KERNAL `LOAD`/`SAVE` path** — the table and
  the name editor ARE ported (see the rows above); what is not is their storage.
  High scores go to the REU FS through `filesys.lib` (`gortris.hi`, 30 bytes)
  rather than to a disk file through the KERNAL wrappers, which is also why the
  port holds `filesys.lib` for the whole session instead of handing it back the
  way `sidplay` does. (The `LOAD`/`SAVE` wrappers are the one thing
  `kernal.asm` existed for.)
- **`kernal.asm`, `file_load.asm`, `file_save.asm`** — KERNAL jump-table
  wrappers (`SETLFS`/`SETNAM`/`OPEN`/`LOAD`/`SAVE`/`PRINT`/`GETIN`/`PLOT`).
  GordonOS runs `$01=$35` with no ROM mapped, so those addresses land in our own
  jump table. High scores go to the REU FS via `filesys.lib` when/if we add them.
- **The `$d012` frame wait** in `main.asm` (`loopstart: lda $d012 / cmp #208 /
  bne loopstart`) — a raster busy-wait that would starve every other task.
  Timing comes from the kernel's `frameCount` plus a `SYS_YIELD` (see
  `.github/copilot-instructions.md`: animate on `frameCount`, never the tick).
- **`audio.sid` / `sound.asm`** — a `.sid` is a *program*: 6502 code with its own
  player, its own IRQ and its own private data layout, not a score. It cannot be
  turned into a `.mus`, which is *notation* for one
  interpreter: working out from it which note sounds when, in which voice, with
  which envelope, IS the arrangement, so there is no converter and there cannot
  be one. (There is also no `sid2mus` to look for: the name returns 0 GitHub
  repositories and nothing on the web. `sid2midi` exists, but it stops at MIDI.)
  So the port **wrote** its tune instead: `music/tetris.mus` is this repository's
  own three-voice SID arrangement of **Korobeiniki** — a traditional Russian folk
  song, so the melody itself is in the public domain. The melody and the bass
  line were read from a MIDI
  made from a fan piano sheet, which is credited here as it prints itself:

  > **"Tetris – A Theme (Korobeiniki)"**, NinSheetMusic sheet 574,
  > <https://www.NinSheetMusic.org/> — Traditional Russian Folk Song,
  > *Arrangement by Hirokazu Tanaka*, *Piano Arrangement by Olimar12345*,
  > Nintendo (C) 1989.

  The chords are fitted from the notes sounding under them and everything about
  the SID score is ours: a sawtooth lead, a square-wave bass (a 50% pulse, with a
  soft attack and a long sustain so that straight eighths do not sound plucked)
  and a triangle harmony, the melody and harmony an octave below where the MIDI
  writes them and the bass an octave below that again, the volume at the chip's
  maximum, no pulse-width movement and no mid-song envelope changes (both were
  tried and both read as "detuned" on three voices — the one piece of movement is a
  slight, quick vibrato on the melody alone: ~16 cents at A3, ~5 Hz in the game,
  with the player's `rate * depth` arithmetic worked out in `tools/gen-mus.py`),
  and the form A A B — the theme's opening phrase is heard twice, which the MIDI
  does not write out. It has **no loop of its own** (no HED/TAL): it plays once and
  halts, so `run sidplay tetris` stops after a single pass, and the repetition the
  game wants lives in its `kSidPlay` call (`repeats = 0`). `tools/gen-mus.py` does the
  whole job and plays it through `sid.lib` from a thread of the task itself rather
  than through `sidplay.tsk`. The sheet, its PDF and the MIDI are **not**
  redistributed — none of the three is in this repository.
  (PSID hosting was measured and closed separately: a `.sid` wants `playAddress`,
  ROM banking and its own IRQ, none of which this OS provides.)
  The per-event sounds (`SND_MOVE_BLOCK`,
  `SND_ROTATE_BLOCK`, …) are not ported: the SID is one chip with one player,
  so a short effect would have to interrupt the music that `sid.lib` is playing.
- **The CharPad `.ctm` projects, `tetris_chars2.raw`, and the 441/200-byte
  screen blocks** — they are char-mode artwork (charset at `$3800`, VIC bank 0
  via `$dd00`, `$d018`), and GordonOS is all-bitmap. The screens get redrawn
  with the kernel's own font and glyph support.
  > **Ported, but not as artwork:** the hi-score table's *screen* is the select
  > screen plus the table (see above), and its big block-letter `WELL_GAMEOVER`
  > map is replaced by our font in the well. The `tetris_titlescreen.bin`,
  > `tetris_keys.raw` and `tetris_credits.bin` screens are still unbuilt: the
  > port draws its own text on its own frame for those.
  > **Not ported, but it *is* portable — measured 2026-09-13.** A version of
  > `gortris` that compiled the whole set in was built and then deliberately
  > taken back out (this port wants its own look, and the art is 4.5 KB of a
  > pinned task), so the notes are kept here for whoever revisits it:
  > the art is **hires, 1 bit per pixel** (`$d016` is never written and
  > `SET_CHAR_COLOR` fills all of colour RAM with one `charColor`, so the
  > shading in the tiles is *dithering*, not colour) — which means **every tile
  > is exactly an 8-byte glyph**, and the tile index *is* the glyph offset
  > (`index × 8`), the same arithmetic the VIC does. Screen blocks are 21×21
  > tile maps (441 B) written at column 10, row 4 (`writeScreen = $0410`); the
  > pause and game-over maps are 10×20 (200 B) written inside the well at
  > column 12, row 4 (`PRINT_WELLDATA`). `tetris_chars2.raw` is 232 tiles and
  > the seven maps reference **188** of them (pruning would save 352 B but needs
  > every map remapped by a build step). **Tile 32 (space) is the blank cell** —
  > which is why `cmp #$20` is the occupancy test throughout the original — and
  > the piece frames are tile maps too: `blocks.asm`'s `.text " II "` art names
  > CharPad tiles by letter (tile 73 is the J face; the I-piece bar uses the
  > segmented tiles 89-94). Digits are tiles 48-57.
- **`$d020`/`$d021` colour fiddling** and the `COLOR_CHANGES` keys — char-mode
  specific (colour RAM), no equivalent in the bitmap/surface model.
