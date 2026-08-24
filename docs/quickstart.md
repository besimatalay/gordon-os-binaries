# Quick Start

After boot you land in the shell (a blinking block cursor). The shell is
itself a dynamic task (`shell.tsk`) loaded from the REU filesystem by the
boot task.

The kernel includes a generic page-granular heap (`kMalloc`/`kFree`):
task-owned blocks allocated from the task pool, preserved across pool
eviction, and freed on exit. BASIC's program RAM is a `kMalloc` block sized
with `run basic <N>`.

Cold kernel code ships as **shared dynamic libraries** — `time.lib`,
`fswrite.lib`, `gfx.lib` — loaded into the pool on demand and freed when their
last consumer exits (see [docs/dynamic-libraries.md](docs/dynamic-libraries.md)).
The `.tsk` tasks `gfxdemo`, `border`, `maze` and `threads` are **re-runnable**:
`run` them multiple times for a fresh copy each time.

## Shell built-ins

| Command | What it does |
|---|---|
| `help` | List commands |
| `clear` | Clear the shell's screen |
| `view <id>` | Switch the display to a task's screen |
| `exit` | Exit the shell |
| `run <file> [pages]` | Load + run a `.tsk` task from the REU FS (foreground) |
| `pool` | Print the task-pool map (pages, owners, sizes) |
| `runbatch <file>` | Run a `.bat` batch script from the REU FS |
| `print <text>` | Print text |
| `fsinfo` | Show FS status (active, banks, size) |
| `save <name> <start> <end>` | Save a memory block to the REU FS |
| `load <name> <addr>` | Load a file from the REU FS into memory |
| `del <name>` | Delete an REU FS file |

## `.com` command tasks

Each command is a separate relocatable task that runs on the shell's
shared screen and exits when done. All 12 are bundled in the REU image:

| File | Usage | What it does |
|---|---|---|
| `ps.com` | `ps` | List tasks: `id pri addr size name` per ALIVE task |
| `dir.com` | `dir` | List REU FS files: name + size, footer `N file(s) $xxxx free` |
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

All 8 are bundled in the REU image. `run <name>` loads `<name>.tsk`:

| File | Run with | What it does |
|---|---|---|
| `shell.tsk` | `run shell` | The interactive shell itself. This is a re-entrant task that is started automatically when the system boots, but you can also run multiple copies of it if you wish |
| `basic.tsk` | `run basic <N>` | [Gordon BASIC](gordonbasic.md) interpreter (EhBASIC) + line editor; N = program-RAM pages (256B each) |
| `edit.tsk` | `run edit <file>` | Full-screen 25×40 editor; opens the file or starts blank (terminate with `kill edit`) |
| `border.tsk` | `run border` | Border color flash demo |
| `maze.tsk` | `run maze` | Animated 10 PRINT maze renderer |
| `clock.tsk` | `run clock` | Real-time clock at (0,0) on the shared screen |
| `threads.tsk` | `run threads` | Thread demo — spawns two child threads (border inc/dec) |
| `gfxdemo.tsk` | `run gfxdemo [step]` | Spider-web line weave — four symmetric corner fans of `kLine` strokes; `step` = line interval 1–25 (default 5, smaller = tighter weave) |

## `.lib` shared libraries

Loaded into the pool on demand by the kernel and freed at refcount 0 — see
[docs/dynamic-libraries.md](docs/dynamic-libraries.md):

| File | Used by | Holds |
|---|---|---|
| `time.lib` | `clock`, `time` | getTime / setTime / printTime |
| `fswrite.lib` | shell, `basic`, `format`, `rename` | format / save / delete / rename |
| `gfx.lib` | `gfxdemo` | plot / line / box / fillBox / clearBitmap + 5 stubs |

## Fonts, banners and batch files

| File | Used by |
|---|---|
| `gordon.fnt` | The OS font, loaded by boot |
| `c64uppr.fnt` | Stock C64 uppercase/graphics set (`setfont c64uppr`) |
| `c64low.fnt` | Stock C64 lowercase/uppercase set (`setfont c64low`) |
| `boot.bat` | Batch script run automatically at boot |
| `*.bnr` | Custom-glyph banners drawn with `banner <name> <row> <col>` — every `.bnr` from `src/banners/` is bundled |

Screen switching: F1/F3/F5/F7 and Shift+F1/F3/F5/F7 cycle the 8 virtual
screens. Files in the REU filesystem persist across reboots.
