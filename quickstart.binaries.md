# Quick Start

After boot you land in the shell (a blinking block cursor). The shell is
itself a dynamic task (`shell.tsk`) loaded from the REU filesystem by the
boot task.

BASIC's program RAM is a persistent 64 KB REU working file (`basicwrk`) —
open it with `run basic` (reused if present, created if absent, deleted on
`exit`).

The `.tsk` tasks `gfxdemo`, `fpdemo`, `border`, `maze` and `threads` are **re-runnable**:
`run` them multiple times for a fresh copy each time.

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
| `del <name>` | Delete an REU FS file |
| `wait` | Print "press any key to continue..." and wait for a keypress |

## `.com` command tasks

Each command runs on the shell's shared screen and exits when done.
All 12 are bundled in the REU image:

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
| `banner.com` | `banner <file> <row> <col>` | Draw a `.bnr` custom-glyph banner at (row, col) on the shell's screen (base name ≤ 7 chars) |

## `.tsk` task files

All 9 are bundled in the REU image. `run <name>` loads `<name>.tsk`:

| File | Run with | What it does |
|---|---|---|
| `shell.tsk` | `run shell` | The interactive shell itself. This is a re-entrant task that is started automatically when the system boots, but you can also run multiple copies of it if you wish |
| `basic.tsk` | `run basic` | Gordon BASIC interpreter (EhBASIC) + line editor + bitmap-graphics commands (`mode`/`pen0`–`pen3`/`plot`/`circle`/…); opens the persistent REU working file `basicwrk` (reused if present, created if absent, deleted on `exit`). See the [Gordon Basic language reference](docs/gordonbasic.md) |
| `edit.tsk` | `run edit <file>` | Full-screen 25×40 editor; opens the file or starts blank (terminate with `kill edit`) |
| `border.tsk` | `run border` | Border color flash demo |
| `maze.tsk` | `run maze` | Animated 10 PRINT maze renderer |
| `clock.tsk` | `run clock` | Real-time clock at (0,0) on the shared screen |
| `threads.tsk` | `run threads` | Thread demo — spawns two child threads (border inc/dec) |
| `gfxdemo.tsk` | `run gfxdemo [step]` | Spider-web line weave — four symmetric corner fans of lines; `step` = line interval 1–25 (default 5, smaller = tighter weave) |
| `fpdemo.tsk` | `run fpdemo` | Floating-point showcase: a sine wave drawn edge to edge with a cosine wave superimposed, computed pixel by pixel; peaks and troughs touch the top and bottom of the screen. Slow by design, then idles with the finished bitmap on screen |
## `.lib` shared libraries

These five library files are bundled in the REU image and are loaded
automatically when a task needs them:

| File | Used by | Provides |
|---|---|---|
| `time.lib` | `clock`, `time` | Clock reading and printing |
| `filesys.lib` | shell, `basic`, `format`, `rename` | Filesystem format/save/delete/rename + in-place create/open/readAt/writeAt |
| `gfx.lib` | `gfxdemo`, `fpdemo`, `basic` | Bitmap drawing + pixel-positioned text + matrix fill (hires + multicolor) |
| `fp.lib` | `basic`, `fpdemo` | Floating-point math |
| `string.lib` | shell, `dir`, `ps`, `time.lib`, `filesys.lib` | String ops + hex formatting (`kStrlen`/`kStrcpy`/`kStrcmp`/`kSkipSpaces`/`kByteToHex`/`kHexDigit`/`kNibbleToHex`) |

## Fonts, banners and batch files

| File | Used by |
|---|---|
| `gordon.fnt` | The OS font, loaded by boot |
| `c64uppr.fnt` | Stock C64 uppercase/graphics set (`setfont c64uppr`) |
| `c64low.fnt` | Stock C64 lowercase/uppercase set (`setfont c64low`) |
| `boot.bat` | Batch script run automatically at boot |
| `*.bnr` | Custom-glyph banners drawn with `banner <name> <row> <col>` — every bundled `.bnr` is listed by `dir` |

Screen switching: F1/F3/F5/F7 and Shift+F1/F3/F5/F7 cycle the 8 virtual
screens. Files in the REU filesystem persist across reboots.
