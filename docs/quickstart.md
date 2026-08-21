# Quick Start

After boot you land in the shell (a blinking block cursor). The shell is
itself a dynamic task (`shell.tsk`) loaded from the REU filesystem by the
boot task.

## Shell built-ins

| Command | What it does |
|---|---|
| `help` | List commands |
| `clear` | Clear the shell's screen |
| `view <id>` | Switch the display to a task's screen |
| `exit` | Exit the shell |
| `run <file>` | Load + run a `.tsk` task from the REU FS (foreground) |
| `runbatch <file>` | Run a `.bat` batch script from the REU FS |
| `print <text>` | Print text |
| `fsinfo` | Show FS status (active, banks, size) |
| `save <name> <start> <end>` | Save a memory block to the REU FS |
| `load <name> <addr>` | Load a file from the REU FS into memory |
| `del <name>` | Delete an REU FS file |

## `.com` command tasks

Each command is a separate relocatable task that runs on the shell's
shared screen and exits when done. All 11 are bundled in the REU image:

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

## `.tsk` task files

All 8 are bundled in the REU image. `run <name>` loads `<name>.tsk`:

| File | Run with | What it does |
|---|---|---|
| `shell.tsk` | (boot) | The interactive shell itself |
| `basic.tsk` | `run basic` | [Gordon BASIC](gordonbasic.md) interpreter (EhBASIC) + line editor |
| `edit.tsk` | `run edit <file>` | Full-screen 25×40 editor; opens the file or starts blank (terminate with `kill edit`) |
| `border.tsk` | `run border` | Border color flash demo |
| `maze.tsk` | `run maze` | Animated 10 PRINT maze renderer |
| `clock.tsk` | `run clock` | Real-time clock at (0,0) on the shared screen |
| `threads.tsk` | `run threads` | Thread demo — spawns two child threads (border inc/dec) |
| `gfxdemo.tsk` | `run gfxdemo` | Bitmap graphics demo — star (`kLine`), boxes (`kBox`/`kFillBox`), diagonals (`kPlot`) |

## Fonts and batch files

| File | Used by |
|---|---|
| `gordon.fnt` | The OS font, loaded by boot |
| `c64uppr.fnt` | Stock C64 uppercase/graphics set (`setfont c64uppr`) |
| `c64low.fnt` | Stock C64 lowercase/uppercase set (`setfont c64low`) |
| `boot.bat` | Batch script run automatically at boot |

Screen switching: F1/F3/F5/F7 and Shift+F1/F3/F5/F7 cycle the 8 virtual
screens. Files in the REU filesystem persist across reboots.
