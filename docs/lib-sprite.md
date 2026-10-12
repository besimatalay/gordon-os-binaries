# `sprite.lib` — Library Reference

![sprdemo: eight sprite balls, with real per-pixel collision](img/sprdemo.png)

All **eight** VIC-II sprites, driven by whichever task **owns the display**. A
task names a sprite by its hardware number (`0`–`7`), writes its shadow through
these calls, and the kernel's raster service publishes it once per frame in the
vertical blank. The art lives in the REU FS as 64-byte frames and is DMA'd into
the fixed hardware slots on demand.

There is **no allocation and no handle**: a task owns all eight slots while its
surface is displayed, and the kernel keeps exactly one task's sprite state live
at a time — the display owner's. Everything a task has to say about its sprites
is saved per task slot in the REU and handed over with the display, so two
sprite tasks coexist without any of them knowing about the others.

| | |
|---|---|
| Lib ID | 7 (`LIB_SPRITE`) |
| Entries | 4 (`kSpriteSheet`, `kSpriteFrame`, `kSpritePos`, `kSpriteReg`) |
| Load policy | **eager** — loaded at spawn; declare `libMask` bit 7 (`$0080`) |
| Call indices | 37–40 (`libJumpLo/Hi` + `libInitLo/Hi`) |
| Kernel entry points | `kSpriteSheet` (`$CDDE`), `kSpriteFrame` (`$CDE1`), `kSpritePos` (`$CDE4`), `kSpriteReg` (`$CDEA`) |
| Resident companion | `kSpriteCollide` (`$CDE7`) — **kernel** code, not part of the library |
| Source | `src/libs/sprite.asm` |
| Pool footprint | **1 page** (203 bytes of code, 6 fixups) |
| Caller ZP | **none** — no zero page is needed or claimed |
| Clobbers | A, X, Y and `kArg..kArg+7`; `kPtr` too, **except** `kSpriteSheet`, which preserves it |

> The four call entries are **not** in the `$E000` jump table — that table is
> full. They are four of the five 3-byte stubs in `src/kernel/sprite.inc`'s
> `$CDDE` block, and they are ordinary library entries: `libLoad` rewrites each
> in place to `jmp <the library's entry>` and `libFree` restores `jmp libTrap`.
> The fifth stub, `kSpriteCollide`, is a plain `jmp` to a resident routine,
> because it reads the collision latches — kernel state.

## Before you call

- **Declare `libMask` bit 7** (`$0080`) so the library is refcounted to your
  task: loaded at spawn, freed when the last declared task exits. Like every
  eager library it can be released with `kLibHold` — but **keep bit 7 in the
  mask**: the per-frame setters are the library's entries, and a library the task
  gave back stops serving it, so the sprites freeze on the last state published.
  The publish path is kernel-only; see *Losing the library* below.
- **You drive sprites only while your surface is displayed.** Every call opens
  with the same guard (`curTask == kbFocus`) and returns `C=1` having written
  **nothing** when you are not the display owner. Call `kSwitchView` first.
- **The guard and the store are one step, and the setter clears interrupts with
  `cli`.** Each setter raises `SEI` before the guard and clears it with its last
  store, so a display change cannot land between the two and put the write into
  another task's live state; `kSpriteSheet` holds the same window across the FS
  find and the record copy, which share `reuFsPtr`. `cli` rather than a saved
  status is deliberate — a setter parks its arguments on the caller's stack, so a
  status byte pushed on top of them comes back as an argument. **So
  these calls return with interrupts enabled**, which is what a task runs with
  anyway; a task calling one from inside its own `SEI` window must re-`SEI`.
- **Nothing needs to be claimed, and nothing needs to be cleaned up.** A new
  task starts with an all-zero sprite block, so it inherits no enable, no
  expansions, no priority, no MC mode and no sheet from the task that wore its
  slot before. There is therefore no `sprShadowInit`-style macro and no
  `? sprites busy` refusal: the second sprite task simply works.
- **`kArg..kArg+7` is clobbered by every call**, including `kSpriteSheet`'s
  directory scan and the frame DMA. It is per-task (the scheduler saves and
  restores its REU shadow on every switch) and documented as scratch — never
  keep a value in it across a sprite call.
- **The library keeps no per-task state of its own.** Its data is shared by
  every declaring task, so a call may be preempted inside; anything that must
  survive is either in `kArg` (per task) or in the kernel's per-task block.
- **Two tasks may drive sprites at once — that is the point.** They are never
  *live* at the same time: when the display changes hands, the outgoing owner's
  sheet records, shadow and frame indices are saved into its REU block and the
  incoming owner's are installed, art included. Nothing is shared, so nothing
  is corrupted, and nothing has to be re-asserted on the way back.
- ⚠️ **The MC colours (`$D025`/`$D026`) are global hardware** with no per-slot
  form — but they are published from the *shadow*, like every other setting, so
  they are per-task in effect: whichever task is displayed owns the palette.

## The model, in one paragraph

Sprites are **not** per task in hardware. The VIC has one register set, eight
fixed 64-byte art slots, and five control bytes that are each a bitmask over all
eight sprites. GordonOS therefore runs the register set as a *swapped* resource:
the kernel holds one task's sprite state **live** in its own data block, and
`src/kernel/sprite.inc`'s `sprInstall` moves state in and out when the display
changes hands. Tasks see a plain API; the swap is invisible except that the
frame after regaining the display shows exactly what you left.

## `kSpriteSheet` — bind an FS file to a sprite as its animation sheet

- **Input:** A = sprite (`0`–`7`; `8+` rejected), `kPtr`/`kPtr+1` = filename
  (screen codes, e.g. `.text "ball.spr"`).
- **Output:** `C=0` resolved. `C=1` rejected: sprite ≥ 8, file not found, file
  shorter than one 64-byte frame, or you are not the display owner.
- **Writes:** the sheet record for that sprite — the file's 24-bit FS data-area
  offset, so frame *N* is `record + N*64`.
- **Clobbers:** A, X, Y, `kArg..kArg+7`, `reuFsPtr`, `reuFsRemain`, `srcPtr`.
  **Preserves `kPtr`**, so one filename pointer can resolve several sprites in a
  row — reload A and call again.
- ⚠️ **It costs ~1,000–3,000 cycles and runs SEI'd** (the FS offset is left in
  the shared `reuFsPtr` by the find, so the find and the copy must be atomic).
  **Resolve once at startup, never in the frame loop.**
- **A sheet is a flat file of consecutive 64-byte frames**, the same shape as
  the REU font: frame *N* lives at offset *N*×64. There is no frame count in the
  file and no cache — the only size test is the ≥ 64-byte one above.
- A *failed* re-resolve leaves the previous record intact, so a task that
  re-resolves and fails keeps showing the old sheet.

## `kSpriteFrame` — load frame X of a sprite's sheet into its slot

- **Input:** A = sprite (`0`–`7`), X = frame (`0`–`255`).
- **Output:** `C=0` loaded. `C=1` rejected: sprite ≥ 8, no sheet resolved for
  that sprite, or you are not the display owner.
- **Clobbers:** A, X, Y, `kPtr`, `kArg..kArg+7`, `reuFsPtr`, and the slot's
  pixels.
- **The frame index is recorded**, which is what lets the kernel re-DMA your art
  when your surface takes the display back. You do not have to reload frames
  after a focus change.
- ⚠️ **A slot is written wherever the beam is**, so rewriting a slot while its
  sprite is on screen can split it into two frames for that one line of the
  frame. Load a frame once and animate by **position**; a frame-per-frame load
  is possible but is the one thing here that can visibly tear.
- **The record is per sprite, not per file**: two sprites showing different
  frames of the same sheet each need their own `kSpriteSheet` call.

## `kSpritePos` — place a sprite

- **Input:** X = sprite (`0`–`7`), A = **x low byte**, Y = y, **C = x high bit**
  (`1` when x ≥ 256).
- **Output:** `C=0` applied. `C=1` rejected (not the display owner, or sprite ≥ 8).
- **Clobbers:** A, X, Y. All three are inputs, so there is nothing to preserve.
- **Writes only the shadow.** The raster commit publishes it in the vertical
  blank, so there is no wrong moment to call this and the effect appears at the
  next frame boundary (up to one frame of latency). No `$D012` polling, no
  waiting.
- **Coordinates are display-window coordinates**: the 40-column window's left
  edge is sprite x = **24** and its right edge is **344**, so a 24-pixel sprite
  belongs in x = 24…320. Vertical needs no offset — a sprite at y = 50 is
  displayed from the window's first line.

## `kSpriteReg` — any single-byte shadow field

- **Input:** A = value, X = shadow offset (`0`–`SPR_SHD_SIZE-1` = `0`–`38`).
- **Output:** `C=0` applied. `C=1` rejected: offset out of range (checked
  **first**, so an unchecked X can never walk out of the block), or you are not
  the display owner.
- **Clobbers:** Y. A and X are the inputs, so they answer nothing.
- **This is the apply path for the values with no call of their own:** the five
  per-sprite control bitmasks — enable (`$D015`), y-expand (`$D017`), priority
  (`$D01B`), MC mode (`$D01C`), x-expand (`$D01D`) — at offsets 32–36, and the
  two MC colours (`$D025`/`$D026`) at 37–38.
- **No masking is needed**: a control byte covers all eight slots, and the byte
  that is live is yours alone, because the shadow belongs to the one task whose
  surface is displayed.
- `src/tasks/sprite-shadow.inc` wraps every one of these in a macro
  (`sprOn`, `sprColour`, `sprPriority`, `sprMode`, `sprXExpand`, `sprYExpand`,
  `sprMcColour`) and publishes the offsets as `SPR_SHD_*`. **Use the macros**;
  the raw offsets are an ABI, not a user interface.

## `kSpriteCollide` — the frame-latched collision masks

- **Input:** none. **Output:** `C=0`, A = sprite-sprite mask (`$D01E`),
  X = sprite-background mask (`$D01F`) — **both then cleared**, so a collision
  is reported to exactly one caller. `C=1` = you are not the display owner and
  the masks are left untouched.
- **Kernel-resident and the only reader of `$D01E`/`$D01F`.** Those registers
  are cleared *by reading*, so the latch is OR-accumulated between polls: a task
  that polls every Nth frame still sees every collision.
- **It is a per-pixel test, not a bounding box.** Bit *i* means "sprite *i*
  touched someone", so a shaped sprite collides where it is *drawn* (a ball's
  empty corners do not collide). What the register cannot give is **the pair**
  (with more than two sprites enabled, `maskA & maskB` is a heuristic) and any
  geometry — that is why a task that needs the pair tests its own in software.
- **The latches are dropped on a hand-over**, so a new display owner's first call
  can never report the previous owner's collisions.

## Two tasks at once

Two tasks can drive sprites at the same time: each drives its own sprites, both
keep working, and whichever surface is displayed shows its own art and its own
settings. The rules that make that work are the ones a caller has to know:

1. **A task's state is saved and restored, never shared.** Sheet records, the
   39-byte shadow and the frame indices are 71 bytes per task slot
   (`REU_SPR_BASE + slot × 128`), and the live copy is one contiguous run in
   kernel data.
2. **Only the display owner's state is installed**, so two tasks can both use
   slot 2 without ever colliding — they are not live at the same time.
3. **A task that never calls a setter costs nothing.** Its block stays zero and
   `sprInstall` skips the frame re-DMA (a zero sheet record means "unresolved").

## When the display changes hands

`sprInstall` runs from two places, and both are needed:

- **The scheduler's restore path** (`switchTask`/`reschedule` — the timer tick,
  and every yield/sleep/exit/kill) covers a task that never calls a setter: an
  F-key screen switch, or the display owner dying. It is also what unpublishes a
  stale state when there is no display owner at all (`kbFocus = $FF`). The call
  sits between the scheduler's save and its reload of the kernel ZP, which is
  what makes the routine's `kPtr`/`kArg` clobber harmless. After that reload the
  resumed task would keep the install's leftovers as its own DMA parameters —
  `kPtr` = `sprLiveState` and `kArg` = a sprite block address, which a caller
  that reuses `kArg` as a length reads as ~50KB — so the call belongs *before*
  the reload, never after it; on a tick that does
  not switch tasks it is skipped, so a hand-over takes effect at the next switch
  (one quantum — one tick at the default priority 1).
- **The top of every library setter** — immediate, so a write can never land in
  the *previous* owner's live state. A task that drives sprites every frame
  therefore registers its first setter call as the hand-over.

Both are cheap when nothing has changed: it compares `kbFocus` with the installed
slot and returns at once.

The swap itself is: save the live state into the old owner's block (one DMA),
load the new owner's block (one DMA), re-DMA every frame its sheet records name
(up to eight 64-byte DMAs), republish, and drop the collision latches. A task
that regains the display therefore comes back to **the art it left**, at the
positions it left, with its own control bytes — nothing to re-assert.

## Losing the library

The publish path is **kernel-only by construction**: the raster commit reads the
kernel's own state and never calls into the library, so a task whose `sprite.lib`
has been released (`kLibHold`) or evicted keeps its sprites displayed perfectly —
frozen on the last state that was published. Every setter then calls `libTrap`
(`sec`/`rts`) and returns `C=1`, which is why the failure is a `C=1` you can ignore
rather than a crash.

**It does not come back on its own.** `sprite.lib` is an **eager** library, so its
entry stubs hold the fail-safe `jmp libTrap` — there is no cold stub, and unlike a
lazy library (`sid.lib`, `filesys.lib`, `time.lib` — all of which reload on the
next call) nothing can reload it. A task that hands it back therefore loses its
per-frame setters for good: the calls go silent and stay silent, until some other
task that still declares the library loads it — then `libLoad` re-patches the four
**shared** entries for everyone. That is why bit 7 belongs in the `kLibHold` keep
mask (see
*Before you call*), and why `kLibHold` takes a **mask** at all: a task needs
`sid.lib` **and** `sprite.lib` at the same time, and the old keep-one-id form could
only hold one of them.

## Endnotes

- **The art lives in the REU FS**, so a sprite task ships its `.spr` files with
  the image (`tools/build-reu.ps1`'s asset array) and declares `filesys.lib` if
  it wants to read them itself. `kSpriteSheet` uses the resident `kReuFindFile`
  and needs no `filesys.lib` of its own — a library cannot declare one.
- **The eight slots are fixed hardware addresses** (`$02C0`, `$0300`, `$0340`,
  `$0380`, `$03C0`, `$0F00`, `$0F40`, `$0F80`) and the commit re-applies
  `$07F8-$07FF` every frame, because that page travels with the surface. A task
  that wants art no file can describe may write slot pixels directly.
- **The commit has a deadline.** Past raster line 30 it publishes nothing for
  that frame rather than split a sprite; that is a one-frame hold, not a lost
  update.
- **Animate on `frameCount`, not on the scheduler tick** (`$CFFF`, one increment
  per displayed frame). The tick runs at 59.2 Hz and the display samples at
  50.1 Hz, so a per-tick animation is sampled unevenly and stutters.

## See also

- [`kernel.md`](kernel.md) → *Sprites* — the kernel side: the shadow layout, the
  raster commit, `sprInstall`, the per-task REU block and the warm-boot reset.
- [`programmers-guide.md`](programmers-guide.md) → *Sprites* — how to drive
  sprites from a task, with the focus, frame and collision rules.
- [`kernel-call-inventory.md`](kernel-call-inventory.md) — the full call table.
- [`dynamic-libraries.md`](dynamic-libraries.md) — how libraries are loaded,
  refcounted and released.
- [`lib-gfx.md`](lib-gfx.md), [`lib-fp.md`](lib-fp.md),
  [`lib-string.md`](lib-string.md), [`lib-sid.md`](lib-sid.md),
  [`lib-ipc.md`](lib-ipc.md) — the other libraries.
