# Quick Start

**Which image?** Two ship, and they are alternatives: `REU.bin` pairs with VICE at
`-speed 200`, and `REU-C64U.bin` with a C64 Ultimate (or any real machine), which needs no
speed setting at all. Each declares its machine's speed in its own `boot.bat` — see the note
on `speed` below. They differ in that one line and nothing else.

After boot you land in the shell (a blinking block cursor). The shell is
itself a dynamic task (`shell.tsk`) loaded from the REU filesystem by the
boot task.

BASIC's program RAM is a persistent 64 KB REU working file (`basicwrk`) —
open it with `run basic` (reused if present, created if absent, deleted on
`exit`).

The `.tsk` tasks `gfxdemo`, `fpdemo`, `spirog`, `sprdemo`, `maze` and `clock` are
**re-runnable**: `run` them multiple times for a fresh copy each time. `sprdemo` is
unconditional about it — a task owns all eight sprite slots while its surface is
displayed, and the kernel hands its sprite state over with the display, so any number of
sprite tasks may run at once (see [lib-sprite.md](../docs/lib-sprite.md)).
`godzi` is deliberately **not** re-runnable — it holds the **SID** for its whole session,
so a second `run godzi` gets `? already running` rather than two copies fighting over the
chip. (Its sprites need no guard: two sprite tasks coexist, each with its own state.)
`gortris` (Tetris) is **not re-runnable** either — it owns the display for its whole
life, holds the board in its own image and plays its own music, so a second
`run gortris` gets `? already running`. It is **pinned** in the pool as well
(`KF_NOT_EVICTABLE`): swapping it out mid-game would have to restart the game cold.
`grknoid` (Gorkanoid, an Arkanoid game) is the same: **not re-runnable** and
**pinned**, because it owns the display for its whole life and holds the wall and the
score table

> **Run VICE at `-speed 200`, which is what `REU.bin` is built for.** The whole emulated
> machine runs faster, so anything measured against the host's clock moves: the cursor
> blink and the keyboard repeat, a game's perceived pace, the `clock` task's seconds, and
> **the SID's pitch** — the pitch is tied to the CPU clock, so at 200% every note would be
> an octave higher. **One setting absorbs the system's share of all of it: `speed
> <percent>`**, declared by a line in the image's `boot.bat`. It scales the kernel's
> blink/repeat ticks and sid.lib's pitch and tempo compensation, so the keyboard and the
> music are right whatever the machine runs at. Change it live from the shell with `speed`;
> the [quick-start guide](quickstart.binaries.md) has the values.
>
> **On a C64 Ultimate, use `REU-C64U.bin`** — the same image built with `speed 100`. Its
> turbo raises the CPU speed without moving the SID's clock or the video timing, so a real
> machine must not be told 200%. **The video standard needs no setting on either machine**:
> the clock a standard fixes also scales every note, so `sidlib` measures the standard from
> the VIC once per load and reads its own copy of the note table — a PAL Ultimate is in tune
> with nothing declared, and only the top octave's B note is 45.5 cents flat.
>
> **Running VICE faster than `-speed 200` is not recommended — and that limit is the
> emulator's, not the machine's.** A C64 Ultimate needs no speed setting at all:
> `REU-C64U.bin` declares 100, which is the machine's own speed, and that is the whole story.
> The caveat applies only to the emulator's fast-forward. The music is the limit: `sidlib`
> answers a faster machine by dropping the tune whole octaves, and one octave is all
> `-speed 200` needs. At `-speed 400` or `-speed 800` the tune would need two or three, which
> takes its notes below the SID's usable range — the pitch would come out wrong — and the
> games' frame counts are at their byte limit there too.

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
| `kill.com` | `kill <id>` | Kill a task (cascades to its thread-spawned children). If the task — or the task that spawned it — declared **`sid.lib`**, the SID is silenced afterwards: a killed player never runs its own hush, so the chip would otherwise hold its last note |
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
| `sidrst.com` | `sidrst` | Reset the SID chip (zeroes `$D400`–`$D418`). The manual fallback for a stuck note: `kill` already clears the chip when the victim (or its spawner) declared `sid.lib`, so this is for a task that died another way, or for a SID left sounding by something that declared nothing |
| `blink.com` | `blink <n>` | Set the cursor blink interval to `n` ticks (default 30, ~60 Hz) |
| `keyrpt.com` | `keyrpt <delay> <repeat>` | Set keyboard repeat timing: `delay` ticks before the first repeat (default 30), then `repeat` ticks between repeats (default 6) |
| `speed.com` | `speed <percent>` | Declare the machine's speed relative to real time (`100` = real time, `200` = what `REU.bin` is built for, powers of two only). Scales the kernel's blink/repeat ticks and sid.lib's music compensation, so the keyboard and the music suit the machine. The image's `boot.bat` sets it at boot; use `REU-C64U.bin` (which declares 100) on a C64 Ultimate |

## `.tsk` task files

All 13 are bundled in the REU image. `run <name>` loads `<name>.tsk`:

| File | Run with | What it does |
|---|---|---|
| `shell.tsk` | `run shell` | The interactive shell itself. This is a re-entrant task that is started automatically when the system boots, but you can also run multiple copies of it if you wish |
| `basic.tsk` | `run basic` | Gordon BASIC interpreter (EhBASIC) + line editor + bitmap-graphics commands (`mode`/`pen0`–`pen3`/`plot`/`circle`/…); opens the persistent REU working file `basicwrk` (reused if present, created if absent, deleted on `exit`). See the [Gordon Basic language reference](docs/gordonbasic.md) |
| `edit.tsk` | `run edit <file>` | Full-screen 25×40 editor: opens the file or starts blank; the document grows on the fly (24-line chunks are kMalloc'd/freed as you type, up to 192 lines), two-way scrolling, insert/overwrite modes, saves back to the same file. `STOP+M` marks a selection (cursor keys extend it, highlighted in reverse video); `STOP+Y` copies it, `STOP+K` cuts it, `STOP+P` pastes the clipboard at the cursor |
| `maze.tsk` | `run maze` | Animated 10 PRINT maze renderer. `q` exits (or `kill` it from the shell) |
| `clock.tsk` | `run clock` | Clock at (0,0) on the shared screen. It only *displays* the CIA #1 TOD, so set it first with `time hh:mm[:ss] [am|pm]`; accurate only at 100% emulation speed, and it loses time under REU load — see [docs/lib-time.md](docs/lib-time.md) |
| `gfxdemo.tsk` | `run gfxdemo [step]` | Spider-web line weave — four symmetric corner fans of lines; `step` = line interval 1–25 (default 5, smaller = tighter weave). `q` exits, while drawing or once idle |
| `spirog.tsk` | `run spirog [R r d col \| 1-9]` | Integer spirograph — a hypotrochoid traced as a `kLine` polyline from a 256-entry sine table (no floating point), so the curve closes exactly. `R` ring radius, `r` rolling radius (`R` must exceed `r`), `d` pen offset, `col` 1–15; values above 127 are clamped and the figure is scaled to fit. No arguments = an 80/35/45 rosette in colour 1, and a single `1`–`9` picks a preset shape sized to use the full screen height, while `10` uses multicolour mode to draw 25 random presets at random sizes and positions, each in one of three colours picked at random for the whole screen. `q` exits, while drawing or once idle |
| `fpdemo.tsk` | `run fpdemo` | Floating-point showcase: a sine wave drawn edge to edge with a cosine wave superimposed, computed pixel by pixel; peaks and troughs touch the top and bottom of the screen. Slow by design, then idles with the finished bitmap on screen; `q` exits from either state |
| `sidplay.tsk` | `run sidplay <name> [delay] [repeats] [transpose]` | Plays a COMPUTE!'s Enhanced Sidplayer `.mus` song (`commodo`, `fsonata`, `tetris` bundled) through **`sid.lib`** — single-instance, no screen. `delay` = ticks per jiffy (default 1, raise to slow down), `repeats` = `0` forever / `1` once (default) / N plays. A failure prints `? tune <name>` / `? load <name>` / `? no memory` / `? no player` on a temporary screen and waits for a key |
| `sprdemo.tsk` | `run sprdemo` | The sprite subsystem's demo: eight coloured balls bouncing off the walls and off each other, driven through the sprite library with one update per displayed frame. `q` exits (or `kill` it from the shell). Its only asset is `ball.spr`. **Re-runnable, with no guard**: a task owns all eight slots while its surface is displayed and the kernel swaps the whole sprite state with the display, so it runs happily beside `godzi` |
| `godzi.tsk` | `run godzi [1\|2]` | **Pinned (`KF_NOT_EVICTABLE`)** — pool eviction never swaps it out; a mid-show cold restart (and its music thread) is not acceptable. A port of the stand-alone demo in `reference/godzi.asm`/`reference/main.asm`: a boat-shaped walker crosses the screen (its 9-bit x walks through x=256) while a "Godzilla" flaps between two poses. Four sprite slots — the reference's own layout: the walker's two overlapping layers (black rigging over a light-blue hull, an X-expanded pair) plus the two Godzilla poses — art in `boat.spr`/`godzi.spr`, one update per displayed frame. Live keys: `1`/`2` switch between the two reference looks, `q` exits (or `kill` it from the shell). The music is its own: it declares **`sid.lib`** and calls `kSidPlay` directly from a thread child — no `sidplay`, no `sidrst` — and it loads *both* tunes at startup (`commodo` for mode 1, `fsonata` for mode 2), so switching the look switches the song by re-pointing the child, with no re-load and no gap; `q` sets the child's quit flag, hushes the SID, reaps the child and frees both buffers. (`kill`ing the demo from the shell skips that path, but `kill` silences the chip itself when the victim — or its spawner — declared `sid.lib`, so no drone is left behind either way.) It also declares `filesys.lib`, which it keeps for the session (the tunes and the sprite sheets, `kLibHold` being one-way — the same arrangement as `gortris`). Single-instance for the **SID**: a second `run godzi` is refused, so two copies cannot fight over the chip. (The sprite side needs no guard — its state is per task and swapped with the display) |
| `gortris.tsk` | `run gortris` | **Tetris** — the game logic of Wiebo de Wit's `tetris.c64` (`reference/tetris/`, MIT) ported to GordonOS: its piece set and frame rotations, its move/test order and its line sweep, with the art redrawn with the kernel's glyphs (the reference is char-mode; this is all-bitmap). The 10×20 board is in the task image and is the authority, so collision is a board lookup, not a screen read. Five modes: attract (four screens, 1016 frames), level select (levels 0–9 on the reference's grid — `j`/`k` or a digit to choose, ENTER to start, hi-score table shown), play, and the reference's game-over animation (the well fills a row a frame, is held full ~3 s, empties, then `game over` / `press key` print inside it). Keys: `j` `k` move, `a` `s` turn, ENTER soft drop, `p` pause — plus SPACE, the hard drop (straight to the floor, 2 a row against the step's 1), and `q` to exit, and `m` to mute the music (from any screen — the panel shows `music off`). The port-2 joystick also works (UP rotate CCW, DOWN soft drop, LEFT/RIGHT move, FIRE rotate CW, and FIRE starts a game). 10 lines per level, delay −4 per level (floored at 4), a line scores × (level+1), and the chosen level is remembered. Three hi scores (7-char names) live in the REU FS as `gortris.hi` and are typed in under the kernel's blinking block cursor. Music: it loads `music/tetris.mus` itself and calls `kSidPlay` from a thread child it spawns — **not** via `sidplay.tsk` — and hushes it while the display is lost. The tune is a single pass (no HED/TAL loop inside the file), so the repetition is the player's — the thread passes `repeats = 0` and the tune restarts each time it ends, while `run sidplay tetris` plays it once and stops. **Not re-runnable** (a second `run gortris` gets `? already running`) and **pinned** in the pool, because it owns the display and holds the board |
| `grknoid.tsk` | `run grknoid` | **Gorkanoid** — an Arkanoid/Breakout game: a paddle sprite (X-expanded 24→48px) under a wall of glyph bricks, with the ball in 8.8 fixed point. The 48-entry wall is in the task image (0 = a gap, 1-3 = the hits to break the brick) and is the authority, so collision is a table lookup, not a screen read. The paddle follows the **held** key (`keybHeld`, a level, not `kReadKey`'s events) one step per displayed frame, with that step **accelerating** from 1 px to 3 px while the same direction is held — a gear every 16 frames, dropped straight back by a release or a reversal: `j` `k` move, SPACE serves, `p` pauses, `q` exits — plus the port-2 joystick, whose path is written but **has not been played-tested** (the dev setup has no stick). The bounce angle is taken from where the ball met the paddle, floored so it can never climb straight up, plus english from the paddle's own movement; five lives, a per-level launch ramp (level 5 launches at twice level 1) and a colour pulse on the ball. Four attract screens (title, controls, credits, high scores), and a game-over screen whose **tune is its clock**: it waits for `firstdt` to play through and then leaves, or leaves at once on a key. Three hi scores (7-char names) live in the REU FS as `grknoid.hi` and are typed in under the kernel's blinking block cursor. Music: three **CGSC** tunes (`katmand`/`immig`/`firstdt`, one per mode) played through `sid.lib` from a thread child it spawns, out of **one buffer for the session** — an 18-page `kMalloc` taken at startup (the largest tune's size) and freed on the way out after the child has been reaped, so a mode change makes no pool request at all; a SID another task holds is retried, while a tune that will not load (missing, or longer than the buffer) falls back to the attract tune. It declares `filesys.lib` and keeps it for the session. **Not re-runnable** (a second `run grknoid` gets `? already running`) and **pinned** in the pool, because it owns the display and holds the wall and the score table |

## `.lib` shared libraries

These seven library files are bundled in the REU image and are loaded
automatically when a task needs them (each task declares its own `libMask` bits
in its header — see `docs/dynamic-libraries.md`):

| File | Used by | Provides |
|---|---|---|
| `time.lib` | `clock`, `time` | Clock reading and printing |
| `filesys.lib` | shell, `basic`, `format`, `rename`, `copy`, `godzi`, `gortris`, `grknoid` | Filesystem format/save/delete/rename + in-place create/open/readAt/writeAt |
| `gfx.lib` | `gfxdemo`, `fpdemo`, `spirog`, `basic` | Bitmap drawing + pixel-positioned text + matrix fill (hires + multicolor) |
| `fp.lib` | `basic`, `fpdemo` | Floating-point math |
| `string.lib` | shell, `dir`, `ps`, `time.lib`, `filesys.lib` | String ops + hex formatting (`kStrlen`/`kStrcpy`/`kStrcmp`/`kSkipSpaces`/`kByteToHex`/`kHexDigit`/`kNibbleToHex`) |
| `sid.lib` | `sidplay`, `gortris`, `godzi`, `grknoid` | COMPUTE!'s Enhanced Sidplayer: `kSidPlay` (play a `.mus` image from RAM — blocking) and `kSidHush` (silence, and stop a running player). ⚠️ The **caller** owns the tune buffer and must declare ZP `$02-$0A`, the player's scratch |
| `ipc.lib` | `ipctest` | Four lock-free single-producer/single-consumer **byte channels** between tasks, each with a 128-byte ring in the library's own data: `kIpcPost` (blocks by yielding while that ring is full) and `kIpcPick` (never blocks; `C=1` when the channel is empty). No kernel buffer, no syscall, no caller ZP |
| `sprite.lib` | `sprdemo`, `godzi`, `grknoid` | All eight VIC sprites: `kSpriteSheet`/`kSpriteFrame`/`kSpritePos`/`kSpriteReg` (plus the resident `kSpriteCollide`). The shadow lives in the kernel and belongs to whichever task owns the display; each task's shadow, sheet records and frame indices are saved per slot in the REU and handed over with the display, so two sprite tasks coexist — see [lib-sprite.md](../docs/lib-sprite.md) |

## Fonts, banners, sprites, music and batch files

| File | Used by |
|---|---|
| `gordon.fnt` | The OS font, loaded by boot |
| `c64uppr.fnt` | Stock C64 uppercase/graphics set (`setfont c64uppr`) |
| `c64low.fnt` | Stock C64 lowercase/uppercase set (`setfont c64low`) |
| `boot.bat` | Batch script run automatically at boot |
| `*.mus` | COMPUTE!'s Enhanced Sidplayer tunes, played by `sidplay` (`run sidplay tetris`) or through `sid.lib` directly: `commodo.mus`, `fsonata.mus` and `tetris.mus` — the last is this repository's own three-voice arrangement of Korobeiniki (see `NOTICE`). Base names ≤ 7 characters |
| `*.bnr` | Custom-glyph banners drawn with `banner <name> <row> <col>` — every bundled `.bnr` is listed by `dir` |
| `ball.spr` | The sprite sheet `sprdemo` loads (`kSpriteSheet`/`kSpriteFrame`): 64-byte frames, frame *N* at file offset *N*×64. Authored as `assets/sprites/ball.txt`, converted by `tools/gen-sprites.py`, seeded by the `$assets` array in `tools/build-reu.ps1` — a new `.spr` must be added to that array |
| `boat.spr` | Two hires frames — the walker of `godzi` (`run godzi`), as the reference's own two co-located sprites: frame 0 = its sprite 0 (the rigging/detail, in FRONT, slot 0, black), frame 1 = its sprite 1 (the filled hull, BEHIND, slot 1, light blue). Where the layers share a pixel the front sprite wins. Same format and pipeline as `ball.spr` |
| `godzi.spr` | Two hires frames — the two poses `godzi` alternates through its enable mask (`kSpriteFrame` loads both once, at entry, and never again). Same format and pipeline as `ball.spr` |

Screen switching: F1/F3/F5/F7 and Shift+F1/F3/F5/F7 cycle the 8 virtual
screens. Files in the REU filesystem persist across reboots.
