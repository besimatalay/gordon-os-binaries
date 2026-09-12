# Quick Start

After boot you land in the shell (a blinking block cursor). The shell is
itself a dynamic task (`shell.tsk`) loaded from the REU filesystem by the
boot task.

BASIC's program RAM is a persistent 64 KB REU working file (`basicwrk`) —
open it with `run basic` (reused if present, created if absent, deleted on
`exit`).

The `.tsk` tasks `gfxdemo`, `fpdemo`, `sprdemo`, `border`, `maze` and `threads` are
**re-runnable**: `run` them multiple times for a fresh copy each time. `sprdemo` is
guarded rather than unconditional — a second instance is allowed only while the task
holding the sprites is another `sprdemo` (identical definitions: one sheet, loaded once
and never swapped), and it prints `? sprites busy` and exits for any other owner.
`godzi` is deliberately **not** re-runnable — it starts and owns a `sidplay` while it
runs, so a second `run godzi` gets `? already running` rather than two copies fighting
over the SID; it also refuses with `? sprites busy` if another task is driving sprites,
since its two switchable looks could not share them.

> ⚠️ **Only one task may drive the sprites at a time.** The register set is global (eight
> art slots, one pointer table, per-slot bitmask bytes), so two concurrent sprite tasks
> would overwrite each other's art and modes. The demos check this at startup and tell you
> instead of corrupting each other — see `docs/bugs.md` #90.

## Shell built-ins

| Command | What it does |
|---|---|
| `help` | List commands |
| `clear` | Clear the shell's screen |
| `view <id>` | Switch the display to a task's screen |
| `exit` | Exit the shell |
| `run <file> [args]` | Load + run a `.tsk` task from the REU FS (foreground) |
| `pool` | Print the task-pool map (pages, owners, sizes) |
| `runbatch <file>` | Run a `.bat` batch script from the REU FS |
| `print <text>` | Print text |
| `fsinfo` | Show FS status (active, banks, size) |
| `save <name> <start> <end>` | Save a memory block to the REU FS |
| `load <name> <addr>` | Load a file from the REU FS into memory |
| `wait` | Print "press any key to continue..." and wait for a keypress |

## `.com` command tasks

Each command runs on the shell's shared screen and exits when done.
All 18 are bundled in the REU image:

| File | Usage | What it does |
|---|---|---|
| `ps.com` | `ps` | List tasks: `id pri addr size name` per ALIVE task |
| `dir.com` | `dir [/w\|/p] [pattern]` | List REU FS files: name + size, footer `N file(s) $xxxx free`. `/w` = two columns per line, `/p` = pause every 24 lines, `pattern` = wildcard filter (`*` any run, `?` any single character) — e.g. `dir *.com` or `dir /w *.tsk` |
| `time.com` | `time [hhmmss [am\|pm]]` | Show the clock, or set it |
| `kill.com` | `kill <id>` | Kill a task |
| `pause.com` | `pause <id>` | Pause a task |
| `resume.com` | `resume <id>` | Resume a paused task |
| `prio.com` | `prio <id> <0-5>` | Set a task's priority (0 = pause) |
| `format.com` | `format` | Interactive `format? y/n` — formats the REU FS |
| `type.com` | `type <file>` | Dump a file's raw bytes to the shell screen (e.g. `type boot.bat`) |
| `setfont.com` | `setfont <name>` | Load `<name>.fnt` from the REU FS into `FONT_BASE` (switches the system font; base name ≤ 7 chars) |
| `rename.com` | `rename <old> <new>` | Rename an REU FS file |
| `copy.com` | `copy <src> <dst>` | Copy an REU FS file under a new name (streams through a 4-page C64 scratch buffer; destination must not already exist) |
| `del.com` | `del <pattern>` | Delete every REU FS file matching a wildcard pattern (`*` any run, `?` any single char); a plain name deletes exactly that file |
| `compact.com` | `compact` | Reclaim REU FS space. `del` only tombstones a file — its bytes and its directory slot leak permanently — so `compact` packs the live files down to the front, frees the tombstone slots and resets the allocator so the free-space figure `dir` shows is accurate. Refuses to run while any other task is alive: it prints `? busy - N task(s) must be killed` and lists them (kill them first — a task saving mid-compaction would be overwritten). Can take a few seconds; nothing is erased |
| `banner.com` | `banner <file> <row> <col>` | Draw a `.bnr` custom-glyph banner at (row, col) on the shell's screen (base name ≤ 7 chars) |
| `sidrst.com` | `sidrst` | Reset the SID chip (zeroes `$D400`–`$D418`) — silences a stuck note left by a killed `sidplay` |
| `blink.com` | `blink <n>` | Set the cursor blink interval to `n` ticks (default 30, ~60 Hz) |
| `keyrpt.com` | `keyrpt <delay> <repeat>` | Set keyboard repeat timing: `delay` ticks before the first repeat (default 30), then `repeat` ticks between repeats (default 6) |

## `.tsk` task files

All 11 are bundled in the REU image. `run <name>` loads `<name>.tsk`:

| File | Run with | What it does |
|---|---|---|
| `shell.tsk` | `run shell` | The interactive shell itself. This is a re-entrant task that is started automatically when the system boots, but you can also run multiple copies of it if you wish |
| `basic.tsk` | `run basic` | Gordon BASIC interpreter (EhBASIC) + line editor + bitmap-graphics commands (`mode`/`pen0`–`pen3`/`plot`/`circle`/…); opens the persistent REU working file `basicwrk` (reused if present, created if absent, deleted on `exit`). See the [Gordon Basic language reference](docs/gordonbasic.md) |
| `edit.tsk` | `run edit <file>` | Full-screen 25×40 editor: opens the file or starts blank; the document grows on the fly (24-line chunks are kMalloc'd/freed as you type, up to 192 lines), two-way scrolling, insert/overwrite modes, saves back to the same file. `STOP+M` marks a selection (cursor keys extend it, highlighted in reverse video); `STOP+Y` copies it, `STOP+K` cuts it, `STOP+P` pastes the clipboard at the cursor |
| `border.tsk` | `run border` | Border color flash demo |
| `maze.tsk` | `run maze` | Animated 10 PRINT maze renderer. `q` exits (or `kill` it from the shell) |
| `clock.tsk` | `run clock` | Real-time clock at (0,0) on the shared screen |
| `threads.tsk` | `run threads` | Thread demo — spawns two child threads (border inc/dec) |
| `gfxdemo.tsk` | `run gfxdemo [step]` | Spider-web line weave — four symmetric corner fans of lines; `step` = line interval 1–25 (default 5, smaller = tighter weave). `q` exits, while drawing or once idle |
| `fpdemo.tsk` | `run fpdemo` | Floating-point showcase: a sine wave drawn edge to edge with a cosine wave superimposed, computed pixel by pixel; peaks and troughs touch the top and bottom of the screen. Slow by design, then idles with the finished bitmap on screen; `q` exits from either state |
| `sidplay.tsk` | `run sidplay <name> [delay] [repeats]` | Plays a COMPUTE!'s Enhanced Sidplayer `.mus` song (`commodo`, `fsonata` bundled) through **`sid.lib`** — single-instance, no screen. `delay` = ticks per jiffy (default 1, raise to slow down), `repeats` = `0` forever / `1` once (default) / N plays. A failure prints `? tune <name>` / `? load <name>` / `? no memory` / `? no player` on a temporary screen and waits for a key. Also spawned by `godzi` (`sidplay commodo 2`), which restarts it when the song ends |
| `sprdemo.tsk` | `run sprdemo` | The sprite subsystem's demo: eight coloured balls bouncing off the walls and off each other, driven through the shadow API with one update per displayed frame. `q` exits (or `kill` it from the shell). No libraries; its only asset is `ball.spr`. **Re-runnable and guarded**: a second `sprdemo` is allowed because it shares the same sheet, but any other task holding the sprites makes it print `? sprites busy` and exit |
| `godzi.tsk` | `run godzi [1\|2]` | A port of the stand-alone demo in `reference/godzi.asm`/`reference/main.asm`: a boat-shaped walker crosses the screen (its 9-bit x walks through x=256) while a "Godzilla" flaps between two poses. Four sprite slots — the reference's own layout: the walker's two overlapping layers (black rigging over a light-blue hull, an X-expanded pair) plus the two Godzilla poses — art in `boat.spr`/`godzi.spr`, no libraries, one update per displayed frame. Live keys: `1`/`2` switch between the two reference looks, `q` exits (or `kill` it from the shell). It has no sound of its own, so it spawns `sidplay` with the arguments a command line would use — `commodo 2` in mode 1, `fsonata 2` in mode 2 — and restarts it whenever the song ends; switching modes live switches the song, and `q` kills that instance and then spawns `sidrst`, because killing a SID player leaves the chip holding its last note. (Killing the demo from the shell skips both — run `sidrst` yourself if you get a drone.) Single-instance: a second `run godzi` is refused, so two copies cannot fight over the SID, and it refuses with `? sprites busy` when another task already owns the sprites (its two looks are different art, so unlike `sprdemo` it cannot share them) |
## `.lib` shared libraries

These five library files are bundled in the REU image and are loaded
automatically when a task needs them:

| File | Used by | Provides |
|---|---|---|
| `time.lib` | `clock`, `time` | Clock reading and printing |
| `filesys.lib` | shell, `basic`, `format`, `rename`, `copy` | Filesystem format/save/delete/rename + in-place create/open/readAt/writeAt |
| `gfx.lib` | `gfxdemo`, `fpdemo`, `basic` | Bitmap drawing + pixel-positioned text + matrix fill (hires + multicolor) |
| `fp.lib` | `basic`, `fpdemo` | Floating-point math |
| `string.lib` | shell, `dir`, `ps`, `time.lib`, `filesys.lib` | String ops + hex formatting (`kStrlen`/`kStrcpy`/`kStrcmp`/`kSkipSpaces`/`kByteToHex`/`kHexDigit`/`kNibbleToHex`) |

## Fonts, banners, sprites and batch files

| File | Used by |
|---|---|
| `gordon.fnt` | The OS font, loaded by boot |
| `c64uppr.fnt` | Stock C64 uppercase/graphics set (`setfont c64uppr`) |
| `c64low.fnt` | Stock C64 lowercase/uppercase set (`setfont c64low`) |
| `boot.bat` | Batch script run automatically at boot |
| `*.bnr` | Custom-glyph banners drawn with `banner <name> <row> <col>` — every bundled `.bnr` is listed by `dir` |
| `ball.spr` | The sprite sheet `sprdemo` loads (`kSpriteSheet`/`kSpriteFrame`): 64-byte frames, frame *N* at file offset *N*×64. Authored as `assets/sprites/ball.txt`, converted by `tools/gen-sprites.py`, seeded by the `$assets` array in `tools/build-reu.ps1` — a new `.spr` must be added to that array |
| `boat.spr` | Two hires frames — the walker of `godzi` (`run godzi`), as the reference's own two co-located sprites: frame 0 = its sprite 0 (the rigging/detail, in FRONT, slot 0, black), frame 1 = its sprite 1 (the filled hull, BEHIND, slot 1, light blue). Where the layers share a pixel the front sprite wins. Same format and pipeline as `ball.spr` |
| `godzi.spr` | Two hires frames — the two poses `godzi` alternates through its enable mask (`kSpriteFrame` loads both once, at entry, and never again). Same format and pipeline as `ball.spr` |

Screen switching: F1/F3/F5/F7 and Shift+F1/F3/F5/F7 cycle the 8 virtual
screens. Files in the REU filesystem persist across reboots.
