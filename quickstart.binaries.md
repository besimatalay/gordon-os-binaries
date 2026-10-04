# Quick Start

**Which image?** Two ship, and they are alternatives: `REU.bin` pairs with VICE at
`-speed 200`, and `REU-C64U.bin` with a C64 Ultimate (or any real machine), which needs no
speed setting at all. Each declares its machine's speed in its own `boot.bat` — see the note
on `speed` below. They differ in that one line and nothing else.

> **VICE on Linux:** Debian/Ubuntu's package ships no C64 ROMs, so `x64sc` exits at once
> unless VICE is told where they are. See *Running VICE on Linux* in [README.md](README.md).

After boot you land in the shell (a blinking block cursor). The shell is
itself a dynamic task (`shell.tsk`) loaded from the REU filesystem by the
boot task.

BASIC's program RAM is a persistent 64 KB REU working file (`basicwrk`) —
open it with `run basic` (reused if present, created if absent, deleted on
`exit`).

The `.tsk` tasks `gfxdemo`, `fpdemo`, `spirog`, `sprdemo`, `maze`, `clock`, `grview` and
`granim` are
**re-runnable**: `run` them multiple times for a fresh copy each time. `sprdemo` is
unconditional about it — a task owns all eight sprite slots while its surface is
displayed, and the kernel hands its sprite state over with the display, so any number of
sprite tasks may run at once: the kernel keeps the sprite state of the task that owns the display and hands it over with the display, so the sprites follow whoever is on screen.
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

`grpaint` (the 1351 paint program) is **not re-runnable** either — one canvas and one
pointer, and its live footprint is 71 of the pool's 109 pages, so two copies plus the shell
are the whole pool: a second `run grpaint` gets `? already running` instead of evicting the
copy that already holds the display.

`run granim llama` plays the bundled **animation**: 360 multicolour frames at 24 fps, 15
seconds, held in the REU filesystem as 60 chunks of six frames. It is
**re-runnable**, SPACE pauses it, `+`/`-` change the rate and `q` exits. It is a greyscale
conversion of *Caminandes 1: "Llama Drama"* — see `NOTICE` for the credit.

> **Run VICE at `-speed 200`, which is what `REU.bin` is built for.** The whole emulated
> machine runs faster, so anything measured against the host's clock moves: the cursor
> blink and the keyboard repeat, a game's perceived pace, the `clock` task's seconds, and
> **the SID's pitch** — the pitch is tied to the CPU clock, so at 200% every note would be
> an octave higher. **One setting absorbs the system's share of all of it: `speed
> <percent>`**, declared by a line in the image's `boot.bat`. It scales the kernel's
> blink/repeat ticks and sid.lib's pitch and tempo compensation, so the keyboard and the
> music are right whatever the machine runs at. Change it live from the shell with `speed`;
> the `speed.com` row below has the values.
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
All 23 are bundled in the REU image:

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
| `fstest.com` | `fstest` | Kept runtime self-test for the FS bank boundary: the chunked DMA paths and the 24-bit offset arithmetic, checked against `fscross.bin`. Re-run it after a change to `filesys.lib`. Run it **before** your first `compact`: that is what closes the alignment gap the check depends on, and the test reports `skipped` afterwards |
| `ipctest.com` | `ipctest` | Kept runtime self-test for `ipc.lib`: two thread producers on two channels, both consumed interleaved, so the backpressure wait and the channel recovery after a sleep are exercised. Expect `ipc PASS` |
| `mtest.com` | `mtest` | The **1351 mouse readout**: the raw POT byte, the position mod 64, the delta since the last sample, the running total and the six button lines of `$DC00`, refreshed while it runs. `p` switches port, `h` cycles the hold, `l` switches between reading the hardware directly and reading it through `mouse.lib`, and any other key exits. It ignores `mouseKind`, so a machine the OS believes has no mouse can still be diagnosed |
| `mouse.com` | `mouse [1351\|off]` | Declare the pointer device this machine has — writes the kernel's `mouseKind` byte (`0` = off, `1` = 1351), the machine-wide setting a program reads at start-up. Bare `mouse` prints the current setting; an unrecognised argument prints the accepted words and changes nothing. Silent on success, like `speed`/`blink`. The kernel default is off; the image's `boot.bat` carries `mouse 1351` at boot, exactly as it carries `speed`. Policy only — the device is `mouse.lib` (the `mtest` readout above) |

## `.tsk` task files

All 15 are bundled in the REU image. `run <name>` loads `<name>.tsk`:

| File | Run with | What it does |
|---|---|---|
| `shell.tsk` | `run shell` | The interactive shell itself. This is a re-entrant task that is started automatically when the system boots, but you can also run multiple copies of it if you wish |
| `basic.tsk` | `run basic` | Gordon BASIC interpreter (EhBASIC) + line editor + bitmap-graphics commands (`mode`/`pen0`–`pen3`/`plot`/`circle`/…); opens the persistent REU working file `basicwrk` (reused if present, created if absent, deleted on `exit`). See the [Gordon Basic language reference](docs/gordonbasic.md) |
| `edit.tsk` | `run edit <file>` | Full-screen 25×40 editor: opens the file or starts blank; the document grows on the fly (24-line chunks are kMalloc'd/freed as you type, up to 192 lines), two-way scrolling, insert/overwrite modes, saves back to the same file. `STOP+M` marks a selection (cursor keys extend it, highlighted in reverse video); `STOP+Y` copies it, `STOP+K` cuts it, `STOP+P` pastes the clipboard at the cursor |
| `maze.tsk` | `run maze` | Animated 10 PRINT maze renderer. `q` exits (or `kill` it from the shell) |
| `clock.tsk` | `run clock` | Clock at (0,0) on the shared screen. It only *displays* the CIA #1 TOD, so set it first with `time hh:mm[:ss] [am|pm]`; accurate only at 100% emulation speed, and it loses time under REU load |
| `gfxdemo.tsk` | `run gfxdemo [step]` | Spider-web line weave — four symmetric corner fans of lines; `step` = line interval 1–25 (default 5, smaller = tighter weave). `q` exits, while drawing or once idle |
| `spirog.tsk` | `run spirog [R r d col \| 1-9]` | Integer spirograph — a hypotrochoid traced as a `kLine` polyline from a 256-entry sine table (no floating point), so the curve closes exactly. `R` ring radius, `r` rolling radius (`R` must exceed `r`), `d` pen offset, `col` 1–15; values above 127 are clamped and the figure is scaled to fit. No arguments = an 80/35/45 rosette in colour 1, and a single `1`–`9` picks a preset shape sized to use the full screen height, while `10` uses multicolour mode to draw 25 random presets at random sizes and positions, each in one of three colours picked at random for the whole screen. `q` exits, while drawing or once idle |
| `fpdemo.tsk` | `run fpdemo` | Floating-point showcase: a sine wave drawn edge to edge with a cosine wave superimposed, computed pixel by pixel; peaks and troughs touch the top and bottom of the screen. Slow by design, then idles with the finished bitmap on screen; `q` exits from either state |
| `sidplay.tsk` | `run sidplay <name> [delay] [repeats] [transpose]` | Plays a COMPUTE!'s Enhanced Sidplayer `.mus` song (`commodo`, `fsonata`, `tetris` bundled) through **`sid.lib`** — single-instance, no screen. `delay` = ticks per jiffy (default 1, raise to slow down), `repeats` = `0` forever / `1` once (default) / N plays. A failure prints `? tune <name>` / `? load <name>` / `? no memory` / `? no player` on a temporary screen and waits for a key |
| `sprdemo.tsk` | `run sprdemo` | The sprite subsystem's demo: eight coloured balls bouncing off the walls and off each other, driven through the sprite library with one update per displayed frame. `q` exits (or `kill` it from the shell). Its only asset is `ball.spr`. **Re-runnable, with no guard**: a task owns all eight slots while its surface is displayed and the kernel swaps the whole sprite state with the display, so it runs happily beside `godzi` |
| `grview.tsk` | `run grview <name>` | Picture viewer for the `.pic` format (`run grview hires` opens `hires.pic` — the suffix is appended, as `sidplay` appends `.mus`, so the base name is ≤ 7 chars): allocates a bitmap surface, takes the display, and DMAs the file's three regions straight to `$2000` / `$0400` / `$D800` — the mode and all four VIC colours come from the file's own header, never the shell's. `m` reinterprets the same bytes in the other mode (nothing is converted), any other key exits. The header's label is metadata and is not printed — a 1-bit glyph blit is unreadable on a multicolour surface. A name that is not there, or a `<name>.pic` that is not a picture, takes a screen of its own, prints `? not found <name>.pic` / `? not a picture <name>.pic` and waits for a key — the `sidplay` pattern, so the shell's screen is never left holding a message. `hires.pic`, `mc.pic`, `alf.pic` and `alfgs.pic` (one photograph in colour and in the three greys) are bundled as samples; the `alf` pair are images of ALF, included non-commercially and claimed as fair use — see `NOTICE` |
| `grpaint.tsk` | `run grpaint <name>` | The **1351 paint program**. The name is the picture: `run grpaint shot` opens `shot.pic` — the suffix is appended, so the base name is at most **7 characters** — and a picture that is there is loaded, while one that is not is the blank canvas the allocator just handed over. **The colours a NEW picture starts in are the rest of the command line**, and their COUNT is the mode: `run grpaint shot 1 1 0` is hires — border 1, paper 1, ink 0 — and `run grpaint shot 1 1 2 7 15` is MC, with 1 the border and the background and red/yellow/light grey as c1/c2/c3. No values at all keeps the black-and-white defaults, and any other count (1, 2, 4, 6 or more) is refused on a screen of its own, like a bad name. A picture that **exists** is a load: the file's own mode and colours win, so a colour argument is refused rather than dropped. It gates on `mouseKind` first — with the setting off it takes a screen of its own, prints `? mouse off - run 'mouse 1351'` and **waits for a key**, the `sidplay` pattern every failure here uses (a task with no screen cannot report anything, so it never just returns to the prompt); then it takes a **bitmap canvas in the mode and palette the run resolved** — the arguments' for a new picture, the loaded file's for one that exists, both settled *before* the allocation so the surface is never re-coloured afterwards (`kAllocScreen` hands the slot back already cleared, so a blank canvas needs no clear pass) and shows it through the `kBlinkReset` SEI window, because the blink block is drawn into framebuffer pixels and would otherwise be baked into the shell's saved surface. The pointer is **two sprites stamping one arrow**: `pointer.spr` holds two hires frames of the classic pointer silhouette, one the 1px ring (the ink) and one the interior (the canvas background), each bound with its own `kSpriteSheet` because a sheet record is per sprite. It is positioned **once per displayed frame** off `frameCount` at sprite (canvas x + 24, canvas y + 50) — the window's left edge and its first raster line — moved by `mouse.lib`'s signed deltas, clamped to the canvas. A single pot sample can read one count high, so the frame is followed as offsets from its first sample and moved by the change in their **minimum**, the reading with no noise on it. The **left button paints**: the segment from where the last frame's stroke ended to where this one moved the pointer, one `kPlot` per pixel, which sets the pixel *and* its cell's colour — so in hires the stroke shows the ink. In MC the plotted value alone would show whichever colour the cell already carried, so every mark then **claims** its cell (`gpClaim`): the cell's colour for the pen's value becomes the pen's colour — high nibble for value 1, low for 2, the colour RAM for 3, and nothing for 0, which is `$D021` — while the cell's *other* colour is kept, exactly as the hires mark keeps the paper. A stroke across a loaded picture therefore comes out in the pen's colour wherever it lands, and the cells it does not touch keep the picture's own per-cell colours. The walk is the task's own Bresenham with the error held below the major span, so a steep drag comes out as a run of pixels, and a press is an event, so a click marks exactly one pixel. `q` clears the sprite enable and exits, which frees the slot and returns the shell's screen **and its cursor**. A shape is previewed live by a **kernel-drawn XOR band** and committed through `kPlot`/`kLine`/`kBox`/`kCircle`, each of which colours its cells in the ink, so what lands is visible the moment it lands. The **UI band is a toggle, and it is already up when the program starts**: a right press closes it and opens it again, a left press takes an entry and leaves the band **up** for the next pick, and a left press off the entries dismisses it and lands on the canvas — so setting a colour, setting a tool and then drawing is one gesture, with no second click. **Undo and redo are five steps each way**: `u` and `r`, or the band's two stacked arrows — the **top** cell row steps back and the **bottom** one forward — and an arrow is **white while it has a step to take**, grey when it does not. One press is one step: a stroke, a shape's commit, a fill, a text entry put away, CLEAR, a palette press and a MODE switch are each one. The line's first click only **anchors** and is *not* a step, so one `u` takes the anchor's dot off without touching the history. **The palette's first swatch is the eraser** in hires — the drawing calls read colour 0 as *clear*, so it takes a pixel off to the cell's own paper without re-colouring the cell — and in multicolour chip 0, the background, does the same. The band is the canvas's **bottom two cell rows**: sixteen palette swatches then **thirteen tiles** — pencil, line, box, filled box, circle, flood fill, three brush blobs, text, clear, save and the MODE tile — read out of `gpui.bin` (`gpui_mc.bin` in multicolour: the MODE tile's face names the mode a press goes to, and only that file carries the four palette-slot chips) (resolved by name once, at start-up, for both modes) into those rows on every open, and saved into the REU while it is up so the close can put the canvas's own rows back. The tool in use is marked in **colour** in its own tile, and the pointer's interior previews the swatch under it. The **text** tile takes the keyboard: pick it, click the canvas, and every printable key plots a glyph one glyph on (eight pixels, the font's pitch; RETURN starts a line, DEL takes the last one back). The pen is a **pixel position**, so text starts wherever you clicked, and the glyph's own cells are written to the **chosen ink** first, so the text comes out in that colour wherever it lands. The glyphs are written **XORed** — the same pixel op the shape previews use — so they invert whatever they cross and stay legible over existing work, and DEL is exact because the same glyph written twice restores the pixels. A block cursor (the inverted cell under the pen) marks where the next key lands, and it goes with the pen: opening the band or clicking elsewhere to type puts it away first, so it never leaves a block behind. Opening the band puts the pen away, which is also when `q` quits again. **`q` asks before it loses work**: with the canvas as the file holds it, `q` leaves at once — but with something drawn since the last save the band comes up if it was down and the SAVE tile **flashes** (about a second on, a second off) until the user either presses it (which saves and stays) or presses `q` again *while the band is up* (which leaves with the canvas as it is). Dismissing the band hides the warning, so the next `q` brings it back rather than leaving. **CLEAR is a command, not a tool**: the press that picks it blanks the canvas and puts the cells back to the palette the picture was created with, leaving the tool and the ink as they were. **SAVE writes `<name>.pic`**, and the tile is drawn only while the canvas has changed since the last save — a press on an unmarked one does nothing at all, which is the whole of the feedback, since there is no message on success. The file is the 10,032-byte picture format `grview` reads and `grpaint` writes, and `kReuOpen` runs before `kReuCreate` so that saving over an existing picture **writes it in place** — a delete would tombstone both the directory slot and the 10,032 bytes. A loaded picture brings its palette and its label through to the next save. A `<name>.pic` that is there but is not ours — the magic, the version, the flags and the 40x25 cell grid are compared, in a fixed 10,032-byte layout — is refused on a screen of its own, and so is a name with a dot in it or one over 7 characters. The **mode** is the file's own and either loads: a `3` boots the canvas multicolour and a `2` hires, and the task adopts the tag, its palette and its band face. **The pointer is a Commodore 1351 in control port 2, and it has to be there before the program starts** — under VICE start it with `-controlport2device 1351` *and* `-mouse` (the device alone leaves the POT bytes frozen, so the buttons read released and the pointer never moves), and attach it before the machine starts, because attaching a mouse afterwards needs a reset; on a C64 Ultimate a real 1351 in control port 2 is all it takes, since the board handles the POT lines itself (a joystick-port device needs nothing enabled, and an Ultimate 64 Elite can swap the two ports from its menu with `C= + J` if the mouse is in port 1) — or a **USB mouse**, which the machine presents to the C64 as a 1351 (its mouse options include Cursor, Mouse, Mouse+Cursor and Mouse+Wheel modes, and firmware 3.15 reads each mouse by its HID report descriptor, so most USB mice work). Either way declare it with `mouse 1351` — the image's `boot.bat` does that at boot, so a fresh start is ready. **Not re-runnable** (a second `run grpaint` gets `? already running`); declares `sprite.lib` + `mouse.lib` + `gfx.lib` + **`filesys.lib`** |
| `godzi.tsk` | `run godzi [1\|2]` | **Pinned (`KF_NOT_EVICTABLE`)** — pool eviction never swaps it out; a mid-show cold restart (and its music thread) is not acceptable. A port of a stand-alone demo: a boat-shaped walker crosses the screen (its 9-bit x walks through x=256) while a "Godzilla" flaps between two poses. Four sprite slots — the reference's own layout: the walker's two overlapping layers (black rigging over a light-blue hull, an X-expanded pair) plus the two Godzilla poses — art in `boat.spr`/`godzi.spr`, one update per displayed frame. Live keys: `1`/`2` switch between the two reference looks, `q` exits (or `kill` it from the shell). The music is its own: it declares **`sid.lib`** and calls `kSidPlay` directly from a thread child — no `sidplay`, no `sidrst` — and it loads *both* tunes at startup (`commodo` for mode 1, `fsonata` for mode 2), so switching the look switches the song by re-pointing the child, with no re-load and no gap; `q` sets the child's quit flag, hushes the SID, reaps the child and frees both buffers. (`kill`ing the demo from the shell skips that path, but `kill` silences the chip itself when the victim — or its spawner — declared `sid.lib`, so no drone is left behind either way.) It also declares `filesys.lib`, which it keeps for the session (the tunes and the sprite sheets, `kLibHold` being one-way — the same arrangement as `gortris`). Single-instance for the **SID**: a second `run godzi` is refused, so two copies cannot fight over the chip. (The sprite side needs no guard — its state is per task and swapped with the display) |
| `gortris.tsk` | `run gortris` | **Tetris** — the game logic of Wiebo de Wit's `tetris.c64` (MIT) ported to GordonOS: its piece set and frame rotations, its move/test order and its line sweep, with the art redrawn with the kernel's glyphs (the reference is char-mode; this is all-bitmap). The 10×20 board is in the task image and is the authority, so collision is a board lookup, not a screen read. Five modes: attract (four screens, 1016 frames), level select (levels 0–9 on the reference's grid — `j`/`k` or a digit to choose, ENTER to start, hi-score table shown), play, and the reference's game-over animation (the well fills a row a frame, is held full ~3 s, empties, then `game over` / `press key` print inside it). Keys: `j` `k` move, `a` `s` turn, ENTER soft drop, `p` pause — plus SPACE, the hard drop (straight to the floor, 2 a row against the step's 1), and `q` to exit, and `m` to mute the music (from any screen — the panel shows `music off`). The port-2 joystick also works (UP rotate CCW, DOWN soft drop, LEFT/RIGHT move, FIRE rotate CW, and FIRE starts a game). 10 lines per level, delay −4 per level (floored at 4), a line scores × (level+1), and the chosen level is remembered. Three hi scores (7-char names) live in the REU FS as `gortris.hi` and are typed in under the kernel's blinking block cursor. Music: it loads `music/tetris.mus` itself and calls `kSidPlay` from a thread child it spawns — **not** via `sidplay.tsk` — and hushes it while the display is lost. The tune is a single pass (no HED/TAL loop inside the file), so the repetition is the player's — the thread passes `repeats = 0` and the tune restarts each time it ends, while `run sidplay tetris` plays it once and stops. **Not re-runnable** (a second `run gortris` gets `? already running`) and **pinned** in the pool, because it owns the display and holds the board |
| `grknoid.tsk` | `run grknoid` | **Gorkanoid** — an Arkanoid/Breakout game: a paddle sprite (X-expanded 24→48px) under a wall of glyph bricks, with the ball in 8.8 fixed point. The 48-entry wall is in the task image (0 = a gap, 1-3 = the hits to break the brick) and is the authority, so collision is a table lookup, not a screen read. The paddle follows the **held** key (`keybHeld`, a level, not `kReadKey`'s events) one step per displayed frame, with that step **accelerating** from 1 px to 3 px while the same direction is held — a gear every 16 frames, dropped straight back by a release or a reversal: `j` `k` move, SPACE serves, `p` pauses, `q` exits — plus the port-2 joystick, whose path is written but **has not been played-tested** (the dev setup has no stick). The bounce angle is taken from where the ball met the paddle, floored so it can never climb straight up, plus english from the paddle's own movement; five lives, a per-level launch ramp (level 5 launches at twice level 1) and a colour pulse on the ball. Four attract screens (title, controls, credits, high scores), and a game-over screen whose **tune is its clock**: it waits for `firstdt` to play through and then leaves, or leaves at once on a key. Three hi scores (7-char names) live in the REU FS as `grknoid.hi` and are typed in under the kernel's blinking block cursor. Music: three **CGSC** tunes (`katmand`/`immig`/`firstdt`, one per mode) played through `sid.lib` from a thread child it spawns, out of **one buffer for the session** — an 18-page `kMalloc` taken at startup (the largest tune's size) and freed on the way out after the child has been reaped, so a mode change makes no pool request at all; a SID another task holds is retried, while a tune that will not load (missing, or longer than the buffer) falls back to the attract tune. It declares `filesys.lib` and keeps it for the session. **Not re-runnable** (a second `run grknoid` gets `? already running`) and **pinned** in the pool, because it owns the display and holds the wall and the score table |
| `granim.tsk` | `run granim <film>` | **GordonAnim** — a full-screen animation player for the REU filesystem's `.anm` chunks. `run granim llama` plays the bundled film: 360 multicolour frames at 24 fps, 15 seconds, held as 60 chunks of six frames plus a manifest. A frame is six reads, so no window holds interrupts off for long; the film clock steps on the machine's declared **speed**, so the film is the same length in real time on a 200% emulator as on a real C64, and the display is checked before every update, so an F-key switch pauses the film instead of drawing into the new owner's screen. `+`/`-` change the rate, SPACE pauses, `q` exits. The bundled film is a greyscale conversion of *Caminandes 1: "Llama Drama"* — see `NOTICE` for the credit |

## `.lib` shared libraries

These nine library files are bundled in the REU image and are loaded
automatically when a task needs them (each task declares its own `libMask` bits
in its header):

| File | Used by | Provides |
|---|---|---|
| `time.lib` | `clock`, `time` | Clock reading and printing |
| `filesys.lib` | shell, `basic`, `format`, `rename`, `copy`, `godzi`, `gortris`, `grknoid` | Filesystem format/save/delete/rename + in-place create/open/readAt/writeAt |
| `gfx.lib` | `gfxdemo`, `fpdemo`, `spirog`, `basic` | Bitmap drawing + pixel-positioned text + matrix fill (hires + multicolor) |
| `fp.lib` | `basic`, `fpdemo` | Floating-point math |
| `string.lib` | shell, `dir`, `ps`, `time.lib`, `filesys.lib` | String ops + hex formatting (`kStrlen`/`kStrcpy`/`kStrcmp`/`kSkipSpaces`/`kByteToHex`/`kHexDigit`/`kNibbleToHex`) |
| `sid.lib` | `sidplay`, `gortris`, `godzi`, `grknoid` | COMPUTE!'s Enhanced Sidplayer: `kSidPlay` (play a `.mus` image from RAM — blocking) and `kSidHush` (silence, and stop a running player). ⚠️ The **caller** owns the tune buffer and must declare ZP `$02-$0A`, the player's scratch |
| `ipc.lib` | `ipctest` | Four lock-free single-producer/single-consumer **byte channels** between tasks, each with a 128-byte ring in the library's own data: `kIpcPost` (blocks by yielding while that ring is full) and `kIpcPick` (never blocks; `C=1` when the channel is empty). No kernel buffer, no syscall, no caller ZP |
| `sprite.lib` | `godzi`, `grknoid`, `grpaint`, `sprdemo` | All eight VIC sprites: `kSpriteSheet`/`kSpriteFrame`/`kSpritePos`/`kSpriteReg` (plus the resident `kSpriteCollide`). The shadow lives in the kernel and belongs to whichever task owns the display; each task's shadow, sheet records and frame indices are saved per slot in the REU and handed over with the display, so two sprite tasks coexist |
| `mouse.lib` | `grpaint`, `mtest` | The Commodore **1351** on control port 2: `MOUSE_READ` (raw x/y, signed deltas, the button lines), `MOUSE_ENABLE`, `MOUSE_DISABLE`, behind one dispatching call entry. Which pointer this machine has is the kernel's `mouseKind` byte, set by `mouse 1351` — the library reads the hardware and never consults it |

## Fonts, banners, sprites, music and batch files

| File | Used by |
|---|---|
| `gordon.fnt` | The OS font, loaded by boot |
| `c64uppr.fnt` | Stock C64 uppercase/graphics set (`setfont c64uppr`) |
| `c64low.fnt` | Stock C64 lowercase/uppercase set (`setfont c64low`) |
| `boot.bat` | Batch script run automatically at boot |
| `buildid` | The build stamp: the date and time the image was written, printed by `type buildid`. Digits and punctuation only, because `type` writes a file's bytes as they are |
| `*.mus` | COMPUTE!'s Enhanced Sidplayer tunes, played by `sidplay` (`run sidplay tetris`) or through `sid.lib` directly: `commodo.mus`, `fsonata.mus` and `tetris.mus` — the last is this repository's own three-voice arrangement of Korobeiniki (see `NOTICE`). Base names ≤ 7 characters |
| `*.bnr` | Custom-glyph banners drawn with `banner <name> <row> <col>` — every bundled `.bnr` is listed by `dir`. The bundled `logo320`, drawn at boot, is an image of ALF — see `NOTICE` |
| `ball.spr` | The sprite sheet `sprdemo` loads (`kSpriteSheet`/`kSpriteFrame`): 64-byte frames, frame *N* at file offset *N*×64 |
| `boat.spr` | Two hires frames — the walker of `godzi` (`run godzi`), as the reference's own two co-located sprites: frame 0 = its sprite 0 (the rigging/detail, in FRONT, slot 0, black), frame 1 = its sprite 1 (the filled hull, BEHIND, slot 1, light blue). Where the layers share a pixel the front sprite wins. Same format as `ball.spr` |
| `godzi.spr` | Two hires frames — the two poses `godzi` alternates through its enable mask (`kSpriteFrame` loads both once, at entry, and never again). Same format as `ball.spr` |

Screen switching: F1/F3/F5/F7 and Shift+F1/F3/F5/F7 cycle the 8 virtual
screens. Files in the REU filesystem persist across reboots.
