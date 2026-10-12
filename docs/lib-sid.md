# `sid.lib` — Library Reference

The COMPUTE!'s Enhanced Sidplayer as a shared library: play a `.mus` tune
already in RAM, and silence the SID. It is the player body that `sidplay.tsk`
wraps, so any task can play music without carrying a copy of the player —
`sidplay.tsk` itself is **508 bytes / 49 fixups**.

| | |
|---|---|
| Lib ID | 5 |
| Entries | 2 (`kSidPlay`, `kSidHush`) |
| Load policy | **lazy** — the first call cold-loads it; declare `libMask` bit 5 (`$0020`) |
| Call indices | 33–34 (jump entries patched via `libJumpLo/Hi` + `libInitLo/Hi`) |
| Kernel entry points | `kSidPlay` (`$FF7E`), `kSidHush` (`$FF81`) |
| Source | `src/libs/sid.asm` (player body: `src/libs/sidplay.inc`) |
| Pool footprint | 13 pages (3,318 bytes of code, 483 fixups) |

> The two entry points are **not** in the `$E000` jump table — that table is
> full (its only free byte is `$E119`). They are ordinary 3-byte stubs in the
> free block at `$FF7E`, exactly like the five `kSprite*` stubs in the `$CDDE`
> pocket, and they are the *last thing assembled* in the kernel.

## Before you call

- **Declare ZP `$02-$0A`** (base 2, length 9) in your task header. This is not
  optional and it cannot be delegated: the player's scratch is remapped into
  that range, and **a library cannot declare ZP** — only a task header has
  `zp_base`/`zp_len`. The play loop yields with `sysSleep`, so the scheduler
  swaps ZP on every jiffy; with any other region the song's state is swapped out
  from under a running tune.
- **Own your tune buffer.** `kSidPlay` never allocates and never touches the
  REU filesystem. A library's `libMask` is structurally `0`, so a library that
  called `kReuFindFile`/`kReuLoad` would hold no filesys reference and
  `filesys.lib` could be freed under a running player. The task loads the tune
  (`kReuFindFile` → `kMalloc` → `kReuLoad`) and passes the buffer.
- **Declare `libMask` bit 5** (`$0020`) so the library is refcounted to your
  task: loaded on demand, freed when the last declared task exits.
- **If you also needed `filesys.lib` to read the tune, give it back before you
  play** with `kLibHold(1 << 5)` (`src/libs/sid.asm`'s reference consumer,
  `sidplay.tsk`, does exactly this). A declared library stays resident until the
  task *exits*, so holding filesys across a song costs ~11 pool pages for
  nothing — enough, on a loaded system, to make the loader evict and restore
  other tasks around the player, which is audible as gaps in the music. Note it
  is **one-way**: see [`dynamic-libraries.md`](dynamic-libraries.md) § *Giving a
  library back early*.
- **Pass the image as stored**: a `.mus` file is PRG-like and opens with a
  2-byte load address, so the tune proper starts at image + 2. The library skips
  those two bytes for you — do not pre-adjust the pointer.
- **One player at a time.** The SID is a single chip and the player's state
  lives in one copy of the library's data, so the second caller is refused.

## `kSidPlay` — play a tune at a given speed

- **Input:** `kPtr`/`kPtr+1` = the `.mus` image in RAM; `kArg` = delay, the
  scheduler ticks slept per jiffy **on a machine at 100%** (`0` is forced to `1`,
  because a delay of 0 would be a tight loop — the library scales it by the machine's
  speed); `kArg+1` = repeats, `0` = repeat forever, `1` = play
  once, `2`–`255` = that many plays; `kArg+2` = transpose in **octaves** and
  `kArg+3` = transpose in **semitones**, both signed (`0` = none) and both **on top of
  the machine's own compensation** (see *Tuning* below). The two have
  **opposite sign conventions**, because each is added where the player already had a
  field: `kArg+2` is added to the **halving count**, so `+1` is one octave **down**
  (`$FF` is one octave up); `kArg+3` is added to the note's half-step total, so `-12` is
  an octave down. **Keep `kArg+3` within one octave either way**: the note path carries a
  half-step total into an octave exactly once, so a total that would need a second carry
  leaves the half-step outside the 12-entry frequency table and the note comes out at the
  wrong pitch.
  **Set both on every call** — they are read at the call, and an unset
  byte is whatever the last task left in the `kArg` block.
- **Output:** `C=0` — the tune played and the SID was hushed. `C=1` — refused,
  another task is already playing.
- **Clobbers:** A, X, Y, `kArg`+0/+1 (the sleep uses `kArg+1`).
- **Blocks** (politely): the task sleeps `delay` ticks per jiffy, so it yields
  the CPU and the 60 Hz scheduler tick is the player's jiffy clock. The call
  returns when the repeats are done — or earlier if `kSidHush` asks it to stop.
- **Returns with the SID silent** and the owner released.

```asm
        lda #<song              // the kMalloc'd buffer
        sta kPtr
        lda #>song
        sta kPtr+1
        lda #1                  // 1 tick per jiffy AT 100%: the tune's own tempo
        sta kArg
        lda #0                  // 0 = repeat forever
        sta kArg+1
        lda #0                  // no transpose: the library answers the machine
        sta kArg+2              //   (+1 in this field is one octave DOWN)
        lda #0                  // no semitone offset
        sta kArg+3
        jsr kSidPlay
        bcs refused             // someone else owns the SID
```

`delay` is **the tune's tempo on a real machine**: one jiffy of music per `delay`
emulated jiffies, so `1` plays the file as written and `2` plays it at half speed. The
library multiplies it by the machine's speed (`sysSpeedShift`), because a faster machine's
jiffies are shorter and it has to sleep more of them per note — so `sidplay commodo 2` is
half the file's tempo *on any machine*, and no caller compensates the emulator.
`gortris`, `godzi` and `grknoid` all pass 1 (`GT_MUSIC_DELAY`/`GZ_MUSIC_DELAY`/
`GK_MUS_DELAY`).

The **pitch** is compensated in the same place and the same way: `-speed 200` runs the
whole emulated machine at twice the rate — the SID's clock included — so every frequency
doubles and a tune would come out **an octave high**. The library adds the machine's own
shift in octaves down (that is why `+1` in the `kArg+2` field is one octave down), so
callers pass 0 and a tune sounds at its written pitch on any machine. A caller's own
offset is added *after* the tune's `TPS` and *after* the compensation, so a tune that
transposes keeps it; both are latched once per call, so the `sidInitSong` work-memory
clear cannot wipe them.

## Tuning

**The machine's speed is declared once, not compensated per call.** `speed <percent>`
sets `sysSpeedShift` — the speed the whole machine runs at relative to real time, as a
signed power of two — and this library applies it to every tune: the pitch moves one
**octave** per step and the `delay` scales by the same step. Both are no-ops on a machine
at 100%, and both are exact, because only powers of two are accepted (25 50 100 200 400
800): the pitch lever is a whole octave, so a speed between them could not be compensated
at all. The pairs above 200% are accepted and not recommended: they mean an emulator running
faster than real time, which no real machine declares. One octave down is what 200% needs,
and two or three take the tune below the SID's usable range, so the pitch comes out wrong
rather than merely fast.

**Why any of this moves the pitch: a SID voice's output frequency is the register value
scaled by the clock feeding the chip** — its 24-bit accumulator is advanced by that clock —
so this is arithmetic, not an emulator quirk, and nothing on the chip can compensate for it.
Speeding up the *CPU* alone does not move it: a **C64 Ultimate** runs its turbo as a CPU
speed setting (up to 48x, 64x on an Elite-II) that grants the CPU more of the fast system
clock's time slots while the VIC keeps priority and the bus, SID sockets included, stays at
1 MHz — so the SID is clocked as it is at 1x, **there is no pitch shift**, and `speed 100`
(what `REU-C64U.bin` declares) is all that machine needs. A *master-clock* change — an
emulator's `-speed`, a bus overclock — is the case that does move it.

**PAL and NTSC differ by the same physics in a smaller amount.** The system clock follows
the video standard (985248 Hz PAL, 1022727 Hz NTSC), so one register value sounds 3.8% —
0.646 semitones — higher on NTSC, and the archive's note table is the NTSC one: `$861E` is
C7 on a 1022727 Hz clock to the last bit.

**The library carries both tables and picks one, so a tune is in tune on either machine.**
`sidDetectVideo` runs once per library load — the first `kSidPlay` of the session — and its
answer (`DataVideoStd`) is read by the note path on every note: `0` selects the archive's own
table, `1` selects `DataNoteFreqLoPal`/`DataNoteFreqHiPal`, the same twelve notes scaled by
NTSC/PAL — stored deliberately **one octave down**, because the scaled B7 needs `$106D0` and
no 16-bit register holds it. An octave down every entry fits, and the note path puts the
octave back — a PAL note is halved **one time fewer** than its octave field says, and an
octave-7 note is **doubled** instead. The tuning is therefore exact on all twelve notes
except **B at octave 7**, where that doubling meets the clamp at `$FFFF`: 45.5 cents flat on
the highest note alone, against 64.7 cents flat on all twelve with no compensation at all.
⚠️ **Clamping in the table instead is the trap this design avoids**: the octave halving
divides whatever is in the table, so a clamped entry comes out 45-52 cents flat in *every*
*octave*, and one sour pitch class is far more audible than a tune that is uniformly flat by
a little. Nothing else about a tune changes: the tempo, the jiffy and the `kArg+2`/`kArg+3`
transposes are the same on both standards.

The machine's video standard is **measured from the VIC, never read from the KERNAL**: the
documented `$02A6` is that ROM's *RS232 baud-table selector*, filled in when RS232 is used,
so on a machine that never opened RS232 the byte holds whatever RAM held at reset — `0`, the
"NTSC" answer, on an emulator that never opened it. PAL wraps at 312 raster lines and NTSC at
263, and lines 263-311 are visible only through `$d011`'s ninth bit, so the detection polls for
that window: it reads the register for a PAL frame's worth of iterations and a machine that
never shows a line past 262 answers NTSC. It costs ~20 ms, once. `DataVideoStd` sits outside
the work window `sidInitSong` clears (asserted in the source), so a song restart does not
re-measure, and the flag is a plain byte rather than a work variable for that reason.

The **filter cutoff** tables are in cutoff-register units and the **vibrato and portamento**
rates are absolute register-unit deltas; both are used exactly as the archive wrote them.

**The jiffy is a CIA timer, not a display frame.** The tick runs at ~60 Hz on both
standards, so a tune's tempo, the blink and the key repeat take the same real time on either
machine. Anything gated on `frameCount` follows the *display* frame instead: 50.1 a second
on PAL against 59.8 on NTSC, so a game that paces itself in frames runs ~19% faster on NTSC.
That difference is accepted — a game's pace is its own business, and no game scales its frame
counts for the video standard.

## `kSidHush` — silence the SID

- **Input:** none. **Output:** none. **Clobbers:** A, X, Y.
- **With no player running** it is a plain silence — the same 25 writeable
  registers (`$D400-$D418`) that `sidrst.com` zeroes directly.
- **With a player running** it also raises the stop flag: the player hushes and
  releases the chip as it leaves its loop, **whatever its repeat value was**.
- ⚠️ **It does not clear the owner.** Clearing it here would let a third task
  claim the player while the current one is still inside its loop. The owner is
  released by the player itself, or reclaimed by liveness (below).
- ⚠️ `sidrst.com` deliberately keeps its own direct register pokes: loading a
  13-page library to zero 25 registers would be absurd, and the "stop a running
  player" half is only wanted while a player is alive. `kill.com` pokes the very
  same 25 registers for the same reason — see "Cleaning up after a kill".

## Ownership, and why a stale owner heals

`sidOwner` holds the slot of the playing task (`$FF` = free) and `sidStop` is
the stop request. The claim is a **check-and-set with interrupts off** — no
syscall may run inside that window, because the syscall dispatcher switches
tasks with `I` set. A recorded owner whose slot is not ALIVE is taken
over, because a **killed** player never runs its hush: without that test a
plain flag would lock the SID for the rest of the session after one `kill`.
(That is why `sidrst.com` exists at all — a `kill` leaves the chip holding
the note the player last wrote, and only a register poke silences it. `gortris`
and `godzi` avoid the problem by owning the player: they call `kSidHush` on the
way out, so nothing is left playing.)

## Cleaning up after a kill

A killed player never runs its own hush, so `kill.com` clears the chip itself
when the task it is killing — **or the task that spawned it** — declared
`sid.lib`. It asks `dynTaskLibMaskLo` (bit 5) **before** the kill, because
`sysKill` frees the victim's dyn entry, then zeroes `$D400-$D418` with the same
write set as `sidrst` (no library call, so no 13 pages are loaded to do it).

Why the declaration and not the owner: `sidOwner` lives in this library's own
data — relocated into pool pages — so no task can address it, and the library
offers no query entry. The declaration is the right question anyway, because
both music demos play through a **thread child**: the child is the SID owner but
has no dyn entry at all (the declaration is on the parent), so the parent is
asked too — which is what makes `kill <demo.0>` work as well as `kill <demo>`.

The one case it cannot tell apart: two tasks declaring `sid.lib` where the
killed one is not the player (e.g. `sidplay` playing while a *refused* `gortris`
is killed). The chip is still cleared — a live player simply re-writes its
registers on its next tick, so the cost is a glitched note, not a stopped tune.
Silence-on-doubt is deliberate: the drone is permanent, the glitch is not.

## Who uses it

| Caller | What it does |
|---|---|
| `sidplay.tsk` | The wrapper: `run sidplay <name> [delay] [repeats]` — finds the `.mus` in the REU FS, `kMalloc`s a buffer sized to the file, loads it, calls `kSidPlay`, frees the buffer, exits. On failure it takes a screen, prints `? tune <name>` / `? load <name>` / `? no memory` / `? no player`, waits for a key and hands the display back (a task with no screen cannot report anything) |
| `godzi` | Directly, from a thread child: it loads **both** modes' tunes at startup (`commodo` and `fsonata`, via `kReuFindFile` → `kMalloc` → `kReuLoad`) and the child plays whichever the player selected, looping the tune while the demo owns the display. `1`/`2` switch the tune by pointing the child's `kPtr` at the other buffer — no re-spawn, no gap. `q` sets `gzMusQuit`, tells the child to stop, reaps it and frees both buffers. Same `filesys`-held-for-the-session arrangement as `gortris` |
| `gortris` ([gortris.md](gortris.md)) | Directly, from a thread child: it loads `music/tetris.mus` at startup (`kReuFindFile` → `kMalloc` → `kReuLoad`) and the child calls `kSidPlay` in a loop while the game owns the display. It does **not** give `filesys.lib` back the way the wrapper does — its hi-score table has to be *written*, and `kLibHold` is one-way, so both declared libraries stay held for the session |
| `grknoid` ([grknoid.md](grknoid.md)) | Directly, from a thread child: three **CGSC** archive tunes (`katmand`/`immig`/`firstdt`) one per mode, loaded from **one buffer for the session** — an 18-page `kMalloc` taken by the *task* at startup (`GK_MUS_PAGES`, sized for the largest tune) and freed on the way out, **after** the child has been reaped. The pool therefore sees one request per session instead of three sizes cycling, and a mode change makes no pool request at all: the allocator needs a **contiguous** run, which is what a 18/4/2-page rotation spends. A tune longer than the buffer is **refused** rather than loaded past its end, so a bigger tune means raising the constant. The game-over tune is a one-shot: when it ends the child hands the request back to the attract tune and sets `gkMusDone`, which is the cue the game-over screen waits on — so that tune always plays to its end. Two failures are handled separately: a `C=1` refusal **keeps the tune and retries** (the retry costs no FS read and no allocation), while a tune that will not load falls back to the attract tune and does not retry on a timer. `filesys.lib` stays held for the session for the same reason as `gortris` (the score table is written, and the child reads a tune file on every mode switch) |

## Writing a tune

`.mus` files are authored, not converted. `tools/gen-mus.py` is the generator:

```
python tools/gen-mus.py --from-midi <file> --bars 16   # write the shipped tune
python tools/gen-mus.py --build  music/score.mus      # the hand-written fallback score
python tools/gen-mus.py --decode music/commodo.mus    # list any .mus file
```

It carries the format (a PRG-style header, three per-voice command streams each
ending in HLT, then a NUL-terminated description) and the encoder/decoder for
every command the player implements; the score itself is a readable table at the
bottom of the script. `--decode` is the safety net: it was validated by decoding
`commodo.mus` (a real, working file) with zero unrecognised commands before any
tune was written with it.

Two things to know when picking a tempo. **The player's jiffy is the unit of note
duration**, and `kSidPlay`'s `delay` is how many scheduler ticks are slept per
jiffy — so at the game's `delay 2` a tune plays at **half** the tempo written in
it (`tetris.mus` is written at 150 M.M., so it sounds at 75). Under VICE's `-speed 200`
that written tempo is heard at ~150 M.M. of wall clock, which is deliberately where the
game wants it — see *VICE speed, and the blink / repeat timings* in
[quick-start.md](quick-start.md). And a tempo should
be a multiple of 32 if 16th notes are used, because the player derives every
duration by shifting the tempo byte.

A MIDI is a better source of notes than a hand-written table, and the tool reads
one: `--from-midi <file> --bars N` takes the melody from the file's top velocity
class, the bass from the lowest note in each eighth (transposed as a line into the
SID's register), fits a chord to each half bar from the notes actually sounding
(preferring the key over a neat-looking inversion), and voices a harmony under the
melody from those chords.

The shipped tune's MIDI was made from a fan piano sheet — **NinSheetMusic sheet
574**, "Tetris – A Theme (Korobeiniki)", **piano arrangement by Olimar12345**,
credited there to **Hirokazu Tanaka**'s game arrangement, **Nintendo (C) 1989**.
The folk melody itself is public domain; the sheet is not, so only its notes are
used here, and the sheet, its PDF and the MIDI are not redistributed — rebuilding
the tune means supplying the MIDI. The credit is in `NOTICE` and
`reference/tetris/UPSTREAM.md`.

What the MIDI cannot supply is the SID's colour —
waveforms, envelopes, pulse widths — so those stay hand-written in the tool. The
shipped tune uses three different waveforms, one per voice (**sawtooth** lead,
**square** bass — pulse at `$0800` — and a **triangle** harmony), writes the lead and
harmony at the register the MIDI transcribes and the bass an octave below the register
the importer picks for it, and deliberately uses **no pulse-width movement and no
mid-song envelope changes**. The file carries no emulator-speed compensation and needs
none: a tune is written at the pitch it should sound, and the player moves it to the
machine's speed — under `-speed 200` the library's one octave down cancels the doubled
clock, and on a machine at 100% nothing moves at all. Its one piece
of movement is a **slight, quick vibrato on the melody only** (VRT 3 / VDP 12): the
player's vibrato amplitude is `rate * depth` in *frequency-register* units and its
period is `2 * rate` player calls, so 3 x 12 = 36 units is ~16 cents at A3 but only
~8 at A4 (a semitone is ~223 register units at A3, ~445 at A4) at roughly 5 Hz in the
game — which reads as richness on a held note. Much more than that stops sounding
expressive and starts sounding out of tune: rate 40 x depth 6, over a semitone of
wobble, was that mistake. ⚠️ VRT must be sent **before** VDP: VDP only arms the
vibrato, and its first flip reloads the counter from the rate, so a rate still 0 at
that point leaves the counter at 0 — which the ramp then reads as 256 calls of drift
in one direction. The MIDI's own form is A B, so
`--repeat-first` (default 8 bars) plays the opening phrase twice — the theme is
heard as A A B. Volume is set to the chip's maximum once, by voice 1: VOL is the
*global* `$D418` register, and the player ORs the option's high nibble into its
low nibble only, so the filter bits and bit 7 (voice 3 off, which must stay
clear) are left alone.

**The file does not loop.** A Sidplayer tune *can* repeat itself — HED marks the top of
a repeat section, `TAL` jumps back to it, and a count of 0 means forever — and the
shipped tune deliberately sends neither, so it plays once, all three voices halt, and
`kSidPlay`'s own `repeats` argument decides what happens next: `gortris` passes `0` (a
looping soundtrack) while `run sidplay tetris` takes the default `1` and stops after one
pass. A loop in the *file* makes that second case impossible, because `TAL` jumps back
**inside** the stream: the voices never all halt, the player never reaches its end test,
and the repeat count it was given can never be acted on. `tools/gen-mus.py` asserts that
no voice carries HED/TAL, so the split stays put.
`--midi-phrases` labels an arrangement's phrases (A B A B C …) if you need to find
the loop length first.

The file then ships itself: `tools/build-reu.ps1` seeds every `music/*.mus` into
the REU FS (base name ≤ 7 characters so the 11-character name limit holds), so
the same tune the game plays is one `run sidplay <name>` away. For the melody's
provenance — why there is no `sid2mus`, and why a `.sid` cannot be converted at
all — see [`reference/tetris/UPSTREAM.md`](../reference/tetris/UPSTREAM.md).

A direct caller is expected to work like the wrapper: load (or embed) the tune,
set `kPtr`/`kArg`/`kArg+1`, call `kSidPlay`, then free. Note that `kMalloc` and
`kReuLoad` both clobber `kPtr`, which is why the wrapper stashes the buffer
pointer in its instance data before it calls them.

## See also

- [`dynamic-libraries.md`](dynamic-libraries.md) — the library system itself
- [`lib-ipc.md`](lib-ipc.md) — the sibling library, and the opposite extreme:
  one pool page, no ZP contract, and a ring of shared state
- [`lib-filesys.md`](lib-filesys.md) — the calls a wrapper uses to load a tune
- [`lib-sprite.md`](lib-sprite.md) — the sprite API: the one library whose
  per-task state is kept by the *kernel* and swapped with the display
- [`reference/sidplayer-how-it-works.md`](../reference/sidplayer-how-it-works.md)
  — the player's internals (jiffy model, `.mus` format)
