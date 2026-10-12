# GordonOS — Memory Map

> Complete memory layout for the Commodore 64 under GordonOS (`$01=$35`).
> Every figure below is checked against the KickAssembler build map by
> `tools/verify-map.ps1`, which rebuilds the kernel, recomputes the free runs
> and their total (**127B across 22 pockets**) and asserts the pinned pockets.
> A green build makes **230 asserts**.
> The FS block must stay above `$0801` — the PRG's first block has to be
> the BASIC stub, or VICE autostart flattens the PRG into one linear
> injection and the system never boots.

---

## Memory Configuration (`$01=$35` = `%00110101`)

GordonOS runs with both the KERNAL ROM and BASIC ROM switched out.

| Bit | Name | Value | Effect |
|---|---|---|---|
| 0 | LORAM | 1 | BASIC ROM and KERNAL ROM require HIRAM=1; LORAM alone has no effect |
| 1 | **HIRAM** | **0** | KERNAL ROM switched out → `$E000-$FFFF` = RAM. BASIC ROM also requires HIRAM=1 → `$A000-$BFFF` = RAM |
| 2 | CHAREN | 1 | I/O at `$D000-$DFFF` (VIC-II, SID, CIA, REU), character ROM at `$D000-$D7FF` |

With HIRAM=0, the entire `$A000-$FFFF` range is RAM. No ROMs are mapped.

---

## Source Import Order

Determines the assembled layout. See `main.asm` for details.

```
main.asm  .pc=$0801  →  BASIC loader
          .pc=$0810  →  kernel.inc (constants; imports task-header.inc + pool.inc)
                        → init.inc
                        → scheduler.inc → irq.inc → syscall.inc → kernel.asm
          kernel.asm → .pc=$E000 jump table group 1 (65 entries)
                       .pc=$E0C3 group 2 (16 entries, $E0C3-$E0F2)
                       $E0F3 kPrintGlyphAt -- $E0F6 kMouseCall
                       .pc=$E0F9 filesys.lib in-place I/O stubs
                       .pc=$E107/$E10A/$E10D/$E110/$E113/$E116 — the six
                         overflow vectors (kStrcmp, kFillMatrix,
                         kSetGfxMode, kFillColorRam, kFpCall, kReuDmaRange)
                       .pc=$E11A imports, in order:
                        kernel-vars → screen-io → keyboard → scroll-region
                        (frag 1) → gfx.inc → text-blit → screen-mgmt →
                        semaphore → screen-lock → task-util → reuCmpName →
                        malloc → poolevict → lib.inc → flood-fill + kEll
                       gfx.lib scratch (ff* + kEll* + kCircle*) → one contiguous block $FC3F-$FF7D (no .pc pin)
          reu.inc / math.inc → .pc=$C800 REU DMA + math routines
          .pc=$CA99  →  dyn task tables (dynTaskOrigin..dynTaskCount,
                        residency records, pool bitmap, malloc table,
                        dynTaskRam*, per-slot name buffers, per-task
                        colors/readString)
          .pc=*      →  boot.inc (boot task — loads shell from the
                        host-built REU FS)
          .pc=*      →  lib descriptors (libNameLo/Hi, libEntryCount, libEager)
                        — sequential after the boot task, i.e. $CD0C
          .pc=*      →  dynTaskLibMask (per-dyn-slot library mask) — $CD4C
          .pc=$CD6D  →  taskScrollTop/Bottom + scrollSeedBuf
          .pc=$4304  →  freeList (orphan free-list)
          dynload.inc → .pc=$4310 (loader + dlCopyArgs + dlEvLibs/dlReLibs)
          .pc=$189F  →  static data (lib runtime + libJump/libInit +
                        gfx LUTs + taskFont + taskShadow)
          .pc=$4000  →  kernel data (kArg, savedSP, per-task arrays, FS state)
          .pc=$13D4  →  reuDirBuf (256B) → reu-fs.inc
          .pc=$186F  →  tasks.inc (taskLo/Hi lookup tables)
          .pc=$C400  →  scratchBuf (1KB scratch text buffer)
          char-shadow.inc → .pc=$CE00
          libstubs.inc → .pc=$1A17 — lazy call stubs
          font-help.inc → .pc=$5340 → pool-top.inc (sequential, $53F2)
          cursor-helpers.inc → .pc=$5457
          scroll-slot.inc → .pc=$54AB (scrollScreenSlot)
          sprite.inc → SIX .pc blocks, one per band it must sit in:
                        .pc=$529E warmSpriteReset (the pocket below
                          dlProbeFit; a warm reboot forgets all sprite state)
                        .pc=$52DC sprInstall + the state mover (loader band)
                        .pc=$1CC0 sprFrameDma (after sysExit, before the
                          data heap)
                        .pc=$567D rasterCommit (above scrollScreenSlot,
                          below the pool)
                        .pc=$CA2F kSpriteCollide + clearSlotSprite
                        .pc=$CD9F sprBlkAddr + sprRestoreFrames + the five
                          entry stubs + sprPtrBytes
                        .pc=$CFA4 the per-task sprite state + the kernel-only
                          bytes (the last pocket before I/O)
```

---

## Full Address Space

| Address | Size | Label | Description |
|---|---|---|---|
| **Zero Page** — `$0000-$00FF` | | | |
| `$0000-$0001` | 2B | — | ⛔ 6510 port registers |
| `$0002-$00EF` | 238B | — | ✓ Task ZP — DMA-preservable per-task via REU |
| `$00F0` | 1B | `blinkRate` | ⛔ Kernel global — cursor blink interval (ticks), set via `blink.com` and re-derived by `speed.com` |
| `$00F1-$00F2` | 2B | `dataPtr` | ⛔ Scheduler saves/restores — task-private data pointer |
| `$00F3-$00F4` | 2B | `taskNamePtr` | ⛔ Task name for spawn (SEI-protected) |
| `$00F5-$00F6` | 2B | `kPtr` | ⛔ Scheduler saves/restores — string/screen pointer |
| `$00F7-$00F8` | 2B | `spawnPtr` | ⛔ Task addr for spawn (SEI-protected) |
| `$00F9-$00FA` | 2B | `srcPtr` | ⛔ Scroll/keyboard scratch (task-owned) |
| `$00FB-$00FC` | 2B | `tmpPtr` | ⛔ Scheduler TCB pointer (IRQ-only) |
| `$00FD` | 1B | `curTask` | ⛔ Current task index (IRQ-only) |
| `$00FE` | 1B | `saveSP` | ⛔ Temp SP during switch (IRQ-only) |
| `$00FF` | 1B | `kbTemp` | ⛔ Keyboard scan temp (IRQ-only) |
| **Low RAM** — `$0100-$1FFF` | | | |
| `$0100-$01FF` | 256B | | ⛔ Stack page — DMA-swapped per task via REU |
| `$0200-$0204` | 5B | | ⛔ EhBASIC page-2 block — `ccflag`/`ccbyte`/`ccnull`/`vec_cc` (`ehbasic.asm`; `basic.asm` writes `$0205`/`$020B` directly) |
| `$0205-$020C` | 8B | | ⛔ EhBASIC I/O vectors `vec_in`/`vec_out`/`vec_ld`/`vec_sv` — installed by `basic.asm` at task start |
| `$020D-$021E` | 18B | | ✓ Free (EhBASIC's reserved irq/nmi gap begins at `$020D`) |
| `$021F-$0220` | 2B | | Boot task `dataPtr` scratch — the name buffer is 12B at `$021F-$022A`; `kDynLoad` writes the binary name here. ⚠️ its tail (`$0221-$022A`) reaches into `ibuffs`, safe only because the boot task has exited before `basic` runs |
| `$0221-$02A0` | 127B | `ibuffs` | ⛔ **EhBASIC input buffer** — `ibuffs = vec_sv+$16 = $0221`, `ibuffe = ibuffs+$7F = $02A0` (`ehbasic.asm`). A **fixed page-2 address**, NOT inside the task's data region |
| `$02A1-$02BF` | 31B | | ✓ Free — the remainder of the only free run in pages 2-3 |
| `$02C0-$03FF` | 320B | sprite slots 0-4 | 5 × 64B VIC sprite data blocks (`$02C0 $0300 $0340 $0380 $03C0`) — the **low band**. All five are ordinary task sprites — fixed, not allocated |
| `$0400-$07FF` | 1KB | | Bitmap video matrix (VIC-II reads this during bitmap mode) |
| `$0801-$080C` | 12B | | BASIC loader `"10 SYS 2064"` |
| `$0810-$0EFF` | ~1.7KB | | **Kernel core part 1**: init + scheduler + irq + the syscall dispatcher and its jump table. ⚠️ The core is not one run — the sprite slot band below splits it |
| `$0EE4-$0EFF` | 28B | `syscall.inc` | `syscallTbl` — 14 handler addresses at 2 bytes each, indexed by syscall number. ⚠️ It must END below `$0F00`: a slot's art is DMA'd over its whole 64 bytes, so art would replace the `SYS_SLEEP` entry's two bytes with pixels and the dispatcher would jump wherever they point. `main.asm` asserts the clearance; the size pad in `init.inc` is what holds the table's address |
| `$0F00-$0FBF` | 192B | sprite slots 5-7 | ⚠️ **Not free RAM** — 3 × 64B VIC sprite blocks (`$0F00 $0F40 $0F80`, the **high band**). Ordinary task sprites, like every other slot. Carved out of `verify-map.ps1`'s free total |
| `$0FC0-$0FC9` | 10B | `main.asm` | `libNameMouse` — the `"mouse.lib"` name string, in the relocation slack above the slot band. `$0FC0` is deliberately not a slot: eight is the VIC's ceiling |
| `$0FCA-$0FCB` | 2B | | ✓ Free — the rest of that slack |
| `$0FCC-$13BF` | ~1.0KB | | **Kernel core part 2**: `spawnCore`'s remainder (`$0FCC-$10D8`) + `sysSpawn`/`sysKill` and the rest of the syscall API (hard limit is `reuDirBuf` at `$13D4`, guarded by the `kernelCoreEnd` assert) |
| `$13C5-$13D3` | 15B | | ✓ Free — the kernel core's growth headroom (`kernelCoreEnd` is at `$13C5`; `main.asm` asserts it stays `<= $13D4`) |
| `$13D4-$14D3` | 256B | `reuDirBuf` | REU directory page buffer |
| `$14D4-$1795` | 706B | | REU filesystem code (init, detect, find/dma helpers, `reuLoad`, `reuDmaRange`, `reuLoadAtomic`). With `reuDirBuf` the whole FS block is 962B (`$13D4-$1795`) |
| `$1796-$1843` | 174B | `syscall.inc` | `spawnCore`'s first 132B + a 3B `jmp` seam back to the remainder at `$0FCC` (`$1796-$181C`, guarded by the `spawnPieceEnd <= $186F` assert), then `warmBootReset` 28B (`$181D-$1838`) and `sprite.lib`'s name string (`$1839-$1843`). **`$1844-$186E` (43B) is free.** See the SEAM note in `syscall.inc` |
| `$529E-$52CC` | 47B | `sprite.inc` | `warmSpriteReset` 35B (`$529E-$52C0`) + `kbScreenGate` 11B (`$52C1-$52CB`) + 1B free (`$52CC`). `kbScreenGate` is the switch path's first stop: it applies a display change the key scan recorded, or jumps straight back. It lives here because every band it is reached from is pinned. `warmSpriteReset` is the reboot half. A reboot must forget every task's sprite state — the live copy in kernel RAM, `sprLiveOwner`, and the whole per-task REU block region — or the boot task (slot 0, which never goes through the spawn path) would inherit the last session's sprites. Called by `warmBootReset` and by `init.inc`'s cold boot (the REU image persists) |
| `$186F-$189E` | 48B | | `tasks.inc` — task lookup tables (`taskLo`/`taskHi`, populated at runtime) |
| `$189F-$1A1A` | 380B | | Static data — lib runtime (`libStartPage/Pages/RefCount`) + `libJumpLo/Hi` + `libInitLo/Hi` (both `LIB_CALLS` = 42 wide) + the spent `LIB_CALLS` growth point + gfx LUTs (`gfxRowLut/gfxCellRowLut`) + font record/glyph scratch + `taskShadowFlag/Hi` |
| `$1A1B-$1C69` | 591B | `libstubs.inc` | 19 lazy call stubs (time 3 / filesys 9 / string 7) + `libColdSave`/`libColdRestore` + the shared fail trampolines + `libLoadFail` + `libFailExit` + the message. `libStubsEnd` is asserted at `$1C6E`, where `syscall.inc`'s `sysExit` block begins |
| `$1C6A-$1C6D` | 4B | | ✓ Free — the stub block's tail |
| `$1C6E-$1CBF` | 82B | `syscall.inc` | `sysExit` + `seClean` (`$1C6E-$1CBB` used, `$1CBC-$1CBF` free; guarded by the `sysExitMovedEnd <= $1CC0` assert). Safe with no glue: entered from `syscallTbl` by an assemble-time `.word` and it ends in `jmp reschedule` |
| `$1CC0-$1D3F` | 128B | `sprite.inc` + `main.asm` | `sprFrameDma` (`$1CC0-$1D15`, 86B) then `kLibHold` (42B, `$1D16-$1D3F`) — **no free run left**; guarded by the `sprFrameEnd <= $1D40` assert. The library's `kSpriteFrame` calls it, and so does `sprRestoreFrames` for every sprite on a display hand-over |
| `$1D40-$1FFF` | 704B | | Per-instance data heap — bump allocator (recycled via same-size slot reuse + orphan free-list) |
| **Screen Buffers** — `$2000-$3FFF` | | | ⚠️ live framebuffer — the DISPLAYED surface's pixels |
| `$2000-$3FFF` | 8KB | — | Framebuffer: pixels of the focused surface (hires bitmap). Swapped via REU DMA with the surface slot on every view switch. All 28 surfaces live in REU (10 KB slots, banks 1+), never here permanently |
| **Kernel Data** — `$4000-$5FFF` | | | |
| `$4000-$4007` | 8B | | kArg(4) + kResult(4) |
| `$4008-$401F` | 24B | `savedSP` | Per-task saved stack pointer (only TCB data in C64 RAM) |
| `$4020-$404F` | 48B | `taskStackReuLo/Hi` | Per-task REU stack base addresses (precomputed at boot) |
| `$4050-$42DD` | ~654B | | Per-task arrays: taskState, priority, surface, ZP DMA, data heap, thread name REU addrs, gfx colors (`taskGfxBorder`/`Bg0`/`Bg1`/`Bg2`), REU FS state (dirBase, dataBase, 24-bit capacity, totalBanks, enabled, name, 24-bit ptr, remain, file, len, flags) |
| `$42DE-$4303` | 38B | `cmdArgsBuf` | Foreground-command args buffer (shell writes, command tasks read) |
| `$4304-$430F` | 12B | `freeList` | Orphan free-list — size/lo/hi × 4 entries |
| `$4310-$529D` | ~4.0KB | `dynload.inc` | Dynamic task loader: `dynLoad`, `dynParseHeader`, `dlRegister`, `dynFree`, `dlEvict`, `dlRestore`, the chunked fixup walk, `dlCopyArgs`, `dlEvLibs`/`dlReLibs`, `dlCallerPages`/`dlSelfEvictOk`/`dlSelfEvictedExit` (the library-top placement + caller-lib accounting helpers live in `pool-top.inc` below) |
| `$52CD-$52DB` | 15B | `kernel.asm` | `dlProbeFit` — asks the allocator whether a free run of X pages exists (trial-allocate, then hand the run straight back). Used by the pre-evict sufficiency test and the caller-sacrifice guard |
| `$52DC-$5336` | 91B | `sprite.inc` | `sprInstall` + `sprStateMove`/`sprStateLoad`/`sprDmaSetup` — the **per-task sprite hand-over**: saves the live state into the outgoing display owner's REU block, loads the incoming owner's, re-DMAs its frames, sets `sprPubMask` and drops the collision latches. Called from the scheduler's restore path (`switchTask`/`reschedule`, i.e. the timer tick and every yield/sleep/exit/kill — between the save and the reload of the kernel ZP, so its ZP clobber is free) and from the top of every `sprite.lib` setter. A compare and an `rts` when nothing has changed |
| `$5337-$533F` | 9B | | ✓ Free (loader headroom) |
| `$5340-$53F1` | 178B | `font-help.inc` | REU font helpers: `bootFontResolve` (resolve `gordon.fnt` → `fontRec*`) + `fontGlyph` (8-byte glyph DMA); its 24-bit FS-offset arithmetic expands the `fs-offset.inc` macros |
| `$53F2-$5456` | 101B | `pool-top.inc` | Library pool placement + caller-eviction accounting: `dlLibCore`, `allocFromPoolTop`, `dlAllocCode`, `dlCallerAddLibs`, `dlCallerLibPages` |
| `$5457-$5481` | 43B | `cursor-helpers.inc` | `dlFindMaster` (`$5457`), `dlInstallCursor` (`$546F`), end `$5482` |
| `$5482-$54A1` | 32B | `slot-shadow.inc` | `clearSlotShadows` — zeroes a slot's per-task ZP shadow when the slot is spawned, so a recycled id cannot inherit the previous occupant's ZP window |
| `$54A2-$54AA` | 9B | | ✓ Free |
| **scrollScreenSlot + Task Pool** — `$54AB-$C3FF` | | | |
| `$54AB-$567C` | 466B | `scrollScreenSlot` | Per-row background slot scroll up; guarded by `.assert scrollSlotEnd <= POOL_BASE` |
| `$567D-$56FD` | 129B | `sprite.inc` | `rasterCommit` — the vblank sprite commit: shadow → `$D000-$D02E`, `$D010` assembled from the per-sprite X-MSB flags, sprite pointers → `$07F8-$07FF`, collision latch, `$D015` masked by `sprPubMask`, the `inc sprFrameCount` clock, and the deadline guard |
| `$56FE-$56FF` | 2B | | ✓ Free (headroom below the pool) |
| `$5700-$C3FF` | ~27.25KB | ✓ Free (task pool, 109 × 256B pages) | Dynamic tasks load here (relocatable). `POOL_BASE=$5700`, `POOL_END=$C400` (hard against the `$C400` loader/scroll scratch). BASIC's program RAM is the REU working file; resident tasks are evicted to REU and restored on exit (see kernel.md) |
| **Font (REU-only)** | | | |
| (REU FS) | 2KB | `fontRecLo/Mid/Hi` = `$19D7-$19D9` | Bitmap text font — 256 glyphs × 8 bytes (lowercase/uppercase), screencode order. Lives in the REU FS (`gordon.fnt`); the boot task resolves the record, the blitter DMA's glyphs on demand |
| **Scratch** — `$C400-$CFFF` | | | |
| `$C400-$C7FF` | 1KB | `scratchBuf` | Multi-use C64 scratch: dynamic-loader header staging + char-shadow scroll DMA redirect |
| `$C800-$CA2E` | ~559B | | `reu.inc` + `math.inc` (DMA routines, byteToDec, mul16/div16/random) — `reu.inc` `$C800-$C964`, `math.inc` `$C965-$CA2E` |
| `$CA2F-$CA8B` | 93B | `sprite.inc` | `kSpriteCollide` + `clearSlotSprite` (60B, `$CA2F-$CA6A`) + `printGlyphAt`'s tail (32B, `$CA6B-$CA8A`) + 1B free. `kSpriteCollide` is the one sprite call that is **not** a library entry — it reads the collision latches, which are kernel state. `clearSlotSprite` is the spawn hook that zeroes a recycled slot's sprite block and forgets the install if that slot was the live one |
| `$CA8C-$CA98` | 13B | `dlEvMaybeSelf` | Sets `dlEvictedSelf` when the task just swapped or killed is the caller; called by `dlEvMark`, `dlEvMarkShared` and `dlEvSwapOrKill`'s kill branch (one `jsr`, so its address is not part of any contract) |
| `$CA99-$CC75` | 477B | dyn task tables + malloc table + per-task buffers | `dynTaskOriginLo`..`dynTaskCount`, residency records, `poolBitmap`, malloc table, `dynTaskRam*`, per-slot name buffers, `taskTextColor`/`taskCursorColor`/`taskReadStr*` |
| `$CC76-$CD0B` | 150B | `boot.inc` | Boot task (resolves `gordon.fnt` → `fontRec*`, then `kDynLoad`s the shell) |
| `$CD0C-$CD4B` | 64B | lib descriptors | `libNameLo`/`libNameHi`/`libEntryCount`/`libEager` |
| `$CD4C-$CD5B` | 16B | `dynTaskLibMask` | Per-dyn-slot 16-bit library mask |
| `$CD5C-$CD6B` | 16B | `kernel.asm` | `gfxSurfPrep` — the running task's cursor prepared for `surfSave`: `eraseCursor` (so a live block cannot be baked into the outgoing slot) then the cursorCol store. Its tail lives in the `$FFE9` run. **1B free at `$CD6C`**, between `dynTaskLibMask` and the scroll-region data |
| `$CD6D-$CD9E` | 50B | | `taskScrollTop`/`taskScrollBottom`/`scrollSeedBuf` |
| `$CD9F-$CDFF` | 97B | `sprite.inc` | `sprBlkAddr` + `sprRestoreFrames` (48B, `$CD9F-$CDCE`) + `kbApplyScreenReq` (14B, `$CDCF-$CDDC`) + `kbScreenReq` (1B at `$CDDD`, the requested screen, `$FF` = none; the routine applies it and jumps to the restore path) + **all 5 public entry stubs** (`$CDDE-$CDEC`, 15B: `kSpriteSheet`/`kSpriteFrame`/`kSpritePos`/`kSpriteCollide`/`kSpriteReg`) + `sprPtrBytes` (`$CDED-$CDF4`, 8B) + 9B used by `blitGlyphFb`. The four `kSprite*` setters **are** `sprite.lib`'s call entries (patched in place by `libLoad`); `kSpriteCollide` is resident. Shares its band with the scroll-region data's headroom below it |
| `$CE00-$CFA3` | 420B | char shadows | `setCharShadow` + shadow/print/clear/scroll mirror hooks (bank 0, 24×1KB at `$2000-$7FFF`) |
| `$CFA4-$CFFF` | 92B | `sprite.inc` | **The per-task sprite state, then the kernel-only bytes** — the block is exactly full. `spriteSheetLo/Mid/Hi` (24B: one 24-bit record per sprite, `Hi = 0` = unresolved), the **shadow** (39B: `sprShReg` 16B X/Y, `sprShXHi` 8B per-sprite X-MSB flags assembled into `$D010` by the commit, `sprShColour` 8B, 7 control bytes) and `sprFrameIdx` (8B) are **one contiguous 71-byte run** — `SPR_BLK_LEN` — that is DMA'd in and out of a task's REU block on every display hand-over. Then the kernel-only bytes: `spriteSlotLo/Hi` (16B), `sprLiveOwner` 1B (the installed slot, `$FF` = none), `sprPubMask` 1B (ANDed into the `$D015` publish), the 2B collision latch and `sprFrameCount` 1B (the per-frame clock a task reads to align an animation with the display). Every array is 8-wide, matching the hardware |
| **I/O** — `$D000-$DFFF` | | | |
| `$D000-$DFFF` | 4KB | — | ⚠️ Bankable RAM — `$01=$34` (CHAREN=0) maps RAM here. Display freezes, no IRQs/REU while banked. See §Bankable I/O RAM below. |
| (normal mode) | | | |
| `$D000-$D3FF` | 1KB | | ⛔ VIC-II registers (mirrored). ⚠️ `$D012`/`$D01A`/`$D019` are **kernel-owned**: the raster compare is line 0 and the RST interrupt is enabled, so the sprite commit runs once per frame in vblank. `$D000-$D02E` (sprite registers) and `$07F8-$07FF` (data pointers) are written **only** by `rasterCommit` |
| `$D400-$D7FF` | 1KB | | ⛔ SID registers (mirrored) |
| `$D800-$DBFF` | 1KB | | ⛔ Color RAM (4-bit SRAM) |
| `$DC00-$DCFF` | 256B | | ⛔ CIA #1 (Timer A = scheduler tick, Port A = keyboard) |
| `$DD00-$DDFF` | 256B | | ⛔ CIA #2 (disabled) |
| `$DF00-$DF0F` | 16B | | ⛔ REU registers |

---

## Bankable I/O RAM (`$D000-$DFFF`, 4KB)

With `CHAREN=0` (`$01` bit 2 clear), the 4KB I/O region maps to RAM instead of
hardware registers. This is **not** general-purpose RAM — it requires disabling I/O.

### How to access

```asm
    sei                         // interrupts must be off
    lda $01; pha                // save current banking
    lda #$34; sta $01           // HIRAM=0, CHAREN=0 → RAM at $D000
    ; ... use $D000-$DFFF as 4KB scratch ...
    pla; sta $01                // restore $01=$35
    cli
```

### Caveats

| What breaks | Why |
|---|---|
| Display freezes | VIC-II registers (`$D000-$D02E`) inaccessible |
| No IRQs | CIA #1 (`$DC00-$DC0F`) inaccessible — timer stops, keyboard dead |
| No REU DMA | REU registers (`$DF00-$DF0F`) inaccessible |
| Color RAM gone | `$D800-$DBFF` becomes RAM, not color nybbles |

The VIC-II retains its last programmed state — the screen goes static
but doesn't blank. ~1ms of freeze is tolerable for burst operations.

### Future use cases

- **REU transfer staging** — load 4KB from REU into `$D000`, swap I/O back, DMA elsewhere
- **Compression/decompression buffer** — unpack data here, copy out after restoring I/O
- **Disk sector cache** — 16 × 256B C64 disk sectors
- **Large sort/scratch space** — algorithms needing temporary working memory

---

### Kernel High Region (`$E000-$FFFF`)

| Address | Size | Label | Description |
|---|---|---|---|
| `$E000-$E0C2` | 195B | jump table | 65 × 3B JMP vectors (`kClearScreen`..`kBlinkReset`) |
| `$E0C3-$E0F5` | 51B | jump table | 16 × 3B gfx/scroll entries — the eager gfx ones are `jmp libTrap` (patched to the gfx.lib routine on load) + `kPrintGlyphAt` (`$E0F3`) |
| `$E0F6-$E0F8` | 3B | `kernel.asm` | `kMouseCall` — mouse.lib's one call entry, patched in place by `libLoad`. The `$E000` band has no spare entry left |
| `$E0F9-$E104` | 12B | jump table | 4 × 3B filesys in-place I/O stubs (`kReuCreate`/`kReuOpen`/`kReuReadAt`/`kReuWriteAt`) |
| `$E105-$E106` | 2B | | ✓ Free |
| `$E107-$E118` | 18B | | kStrcmp, kFillMatrix, kSetGfxMode, kFillColorRam, kFpCall, kReuDmaRange |
| `$E119` | 1B | | ✓ Free (vector headroom) |
| `$E11A-$E247` | 302B | `kernel-vars.inc` | Cursor state, screen base, semaphores, readString state, timeBuf, kbFocus, randomSeed, `taskSleepTicks` — plus reserved-but-dead bytes used as code/data homes, which is why the block's **SIZE is ABI**: `hexChars`' 16B is address-stability slack (keep the size or every label after it shifts), 15 of it holding `kmEvictAlloc` (`$E201`) — `kMalloc`'s pool-full recovery: evict one resident task (**never the caller**), then retry — and the 16th an `$EA` pad; two further dead bytes hold the kill cascade's root and fixpoint flag (`dlCascadeRoot`/`dlCascadeFlag`) — and the reserved byte after `randomSeed` is `surfResolved`, `surfDisplayed`'s scratch for `resolve(kbFocus)` (it must not use `kArg`: the scheduler calls it from the timer IRQ and `sysExit` calls it with a parked task's `kArg` live) |
| `$E248-$EA70` | ~2.0KB | screen/input group | `screen-io.inc` (`$E248-$E4CE`) + `keyboard.inc` (`$E4CF-$EA70`), which also holds `sysSpeedShift` (`$E531`) — the machine's speed as a signed power of two, written by `speed.com` and read by sid.lib (see *VICE speed* in `quick-start.md`) — and `mouseKind` (`$E530`): the pointer device, 0 = off / 1 = 1351, written by the `mouse` command. Both ride in the band's NOP sled, so they add nothing to the band's size. ⚠️ **This band's labels are pinned ABI** — `keyrpt.com` pokes `keybRepeatLda`, and gfx.lib's `ffStk*`/`kCircle*`/`kEll*` scratch aliases sit above it (17 asserts in `main.asm` pin labels in the band), so a size change here must be paid back in place (an inert `.fill n, $ea` NOP sled keeps the size if the bytes are free) |
| `$EA71-$ECDB` | 619B | `scroll-region.inc` (frag 1) | `setScrollRegion`/`scrollScreen`/`blitCharAt`/`blitCharAtRev` (`$EA71-$ECBC`) + `paRoute` (`$ECBD-$ECDB`, `kPrintCharAt`'s surface router, filling the pocket under `gfx.inc`'s anchor exactly) |
| `$ECDC-$F69F` | ~2.5KB | gfx + mgmt + utils | `gfx.inc` (`$ECDC-$F075`) + `text-blit.inc` (`$F076-$F195`) + `screen-mgmt.inc` (`$F196-$F5A0`) + `semaphore.inc`/`screen-lock.inc`/`task-util.inc` (`$F5A1-$F651`) + `reuCmpName` (`$F652-$F69F`). The sub-spans are routine-entry boundaries: `blitChar` opens `text-blit.inc`, `surfSlotToReu` opens `screen-mgmt.inc`, `semWait` opens the semaphore group and `reuCmpName` the last run |
| `$F6A0-$F97D` | 734B | `malloc.inc` | Page-granular `kMalloc`/`kFree`. On a full pool `kmAllocNow` retries once through `kmEvictAlloc` — the step into `dlEvict` protects the caller, so the victim is always another task. ⚠️ **This block's SIZE is ABI**: the malloc tables that follow are pinned by exact-address asserts in `main.asm`, so any change here must be paid back in place |
| `$F97E-$FACC` | 335B | `poolevict.inc` | `dlPreEvict`..`dlFreePages` (the pre-evict loop's sufficiency test lives here) |
| `$FACD-$FC39` | 365B | `lib.inc` | Dynamic library loader + lib name strings (⚠️ `libNameSid` and `libNameIpc` are the odd ones out — their strings live in the `$FF7E` block, because more bytes here would have eaten that pocket) |
| `$FC3A-$FC3E` | 5B | — | ✓ Free — the code chain's growth room, below the `$FC3F` gfx scratch pin. Growing past `$FC3E` trips that `.pc` anchor |
| `$FC3F-$FF7D` | 831B | gfx.lib scratch | **One contiguous block** (no `.pc` pin): flood-fill span-seed stacks + working vars + `kEll*` ellipse scratch (`ffStkXLo`..`kEllTemp`, `$FC3F-$FF6F`) **+ `kCircle*` circle scratch (`$FF70-$FF7D`)** |
| `$FF7E-$FFE8` | 107B | `main.asm` | **`sid.lib` + `ipc.lib` call entries, their lazy cold stubs and both name strings**: `kSidPlay` `$FF7E` / `kSidHush` `$FF81` / `kIpcPost` `$FF84` / `kIpcPick` `$FF87` (four 3-byte entries — they cannot go in the `$E000` table, which is full) + the four cold stubs + `"sid.lib"` + `"ipc.lib"`, all under one `.pc = $FF7E`. The four entries come first, so each address is fixed arithmetic ($FF7E + 3n) and can be pinned by an assert. **`kLibHold` `$FFE6`** is *not* a library entry — it is library-system machinery — so its stub sits at the far end of the pocket instead of joining that run. ⚠️ This block must stay the **last thing assembled**: a `.pc` moves the location counter, and anything emitted after it continues past `$FFFF` |
| `$FFE9-$FFF5` | 13B | `kernel.asm` | `gfxSurfPrep`'s tail — the cursorRow/cursorOn stores, reached by `jmp` from `$CD5C`. **4B free at `$FFF6-$FFF9`**, the run above the library-entry block and `kLibHold` |
| `$FFFA-$FFFF` | 6B | | ⛔ Hardware vectors (NMI, RESET, IRQ) |

---

## Zero Page Detail

| Address | Label | Size | Owner | IRQ Safe? | Purpose |
|---|---|---|---|---|---|
| `$00-$01` | — | 2B | CPU | — | 6510 port registers (never use) |
| `$02-$EF` | — | 238B | Tasks | ✓ | Task ZP scratch; DMA-preservable per-task via REU |
| `$F0` | `blinkRate` | 1B | Kernel | ⛔ | Cursor blink interval (ticks), set via `blink.com` and re-derived by `speed.com` |
| `$F1-$F2` | `dataPtr` | 2B | Scheduler | ⚠️ saved/restored | Task-private data pointer |
| `$F3-$F4` | `taskNamePtr` | 2B | Spawn (SEI) | ✓ | Task name pointer for spawn |
| `$F5-$F6` | `kPtr` | 2B | Kernel | ⚠️ saved/restored | String/screen pointer |
| `$F7-$F8` | `spawnPtr` | 2B | Spawn (SEI) | ✓ | Task entry address for spawn |
| `$F9-$FA` | `srcPtr` | 2B | Kernel | ⚠️ saved/restored | Scroll/keyboard scratch (kernel-clobbered) |
| `$FB-$FC` | `tmpPtr` | 2B | Scheduler | ⛔ IRQ | TCB pointer — do not use in tasks |
| `$FD` | `curTask` | 1B | Scheduler | ⛔ IRQ | Current task index |
| `$FE` | `saveSP` | 1B | Scheduler | ⛔ IRQ | Temp SP during context switch |
| `$FF` | `kbTemp` | 1B | IRQ | ⛔ IRQ | Keyboard scan temp — do not use in tasks |

---

## Kernel Argument Block (`$4000-$4007`)

`kArg` (4 bytes at `$4000`) and `kResult` (4 bytes at `$4004`, overlapping `kArg+4..+7`)
are the kernel's shared parameter block. They are clobbered by virtually every kernel call.
Tasks must assume the entire 8-byte range is garbage after any `jsr` to a kernel routine.

| Bytes | Label | Purpose |
|---|---|---|
| `$4000-$4003` | `kArg` | Primary kernel arguments (4 bytes) |
| `$4004-$4007` | `kResult` | Math results / extended arguments (4 bytes, overlaps `kArg+4`) |

### Routines that use kArg/kResult

| Category | Routines | Usage |
|---|---|---|
| Math | `kMul16` | Operands: `kArg`/`kArg+2` (16-bit). Result: `kResult` (32-bit product) |
| Math | `kDiv16` | Operands: `kArg`/`kArg+2` (16-bit). Result: `kResult` (16-bit quotient + 16-bit remainder) |
| REU DMA | `kReuToC64`, `kReuFromC64` | REU addr lo/hi/bank: `kArg`..`kArg+2`. Length: `kArg+3`/`+4`. Control: `kArg+5` |
| REU fill | `kReuFillC64`, `kReuFillReu` | REU addr: `kArg`..`kArg+2`. Length: `kArg+3`/`+4`. Fill byte in A |
| REU FS | `kReuSave`, `kReuLoad`, `kReuDelete`, `kReuDirEntry`, `kReuFormat` | Name: `kArg`/`+1`. End addr: `kArg+2`/`+3`. Size: `kArg+4`/`+5`. Flags: `kArg+2`. Entry index in A/X; 24-bit offset in `kArg+3/4/5` |
| Time | `kGetTime` | Writes CIA TOD hours/min/sec/decisec → `kArg`..`kArg+3` |
| | `kSetTime` | Reads `kArg`..`kArg+3` → CIA TOD |
| | `kPrintTime` | Uses `kArg` as scratch during formatting |
| Screen lock | `kLockScreen` | Saves `kArg`..`kArg+7` to per-task `taskKArg*` arrays |
| | `kUnlockScreen` | Restores `kArg`..`kArg+7` from per-task arrays |
| Screen mgmt | `kAllocScreen` | `kArg+1` = charset (0=lower, non-zero=upper). `kArg+2` = screen hi |
| | `viewScreen`, `switchView` | `kArg` = target task index |
| gfx.inc | `doGfxSwitch` | `kArg+0` = fromTask, `kArg+7` = toTask |
| Syscalls | `spawnCore` | `kArg` = error code, `kArg+1` = dataSize, `kArg+6`/`+7` = zpBase/zpLen |
| | `sysSetPrio` | `kArg+1` = priority (0-5) |
| | `sysSleep` | `kArg+1` = tick count (1-255) |
| | `sysAllocScreen` | `kArg+1` = charset |
| Misc | `gfxSlotAlloc` | `kArg` = bitmap free-map byte scratch |

---

## Kernel + Task Code (`$0810-$13BF` — ~2.9KB)

Core OS code in low RAM. Task binaries live on the REU FS and are loaded into the pool at runtime.

| File | Contents |
|---|---|
| `kernel.inc` | `MAX_TASKS=24`, TCB offsets, timer constants, ZP labels, screen tail constants |
| `init.inc` | Boot sequence, `$01=$35`, REU detection, `initTCB`/`initTCB_ptr`, `nmiNull` |
| `scheduler.inc` | `switchTask`, REU DMA save/restore, `findNextAlive`, `reschedule` |
| `irq.inc` | `irqHandler`, `irqRet`, keyboard poll dispatch, sleep tick |
| `syscall.inc` | Dispatcher, 14 syscalls, `findFreeSlot`, `shrinkTotalTasks`, `transferFocusAway`, cascading kill |

---

## Task Lookup Tables (`$186F-$189E` — 48B)

Runtime lookup tables `taskLo`/`taskHi` (`MAX_TASKS` slots each,
populated at spawn time).

---

## Kernel Data (`$4000-$4303`)

Kernel data lives in C64 RAM at `$4000-$4303` (772B). The per-task
**stack images** (256B each) live in REU; only `savedSP` remains in
C64 RAM. Layout in `main.asm` order:

| Address | Label | Size | Description |
|---|---|---|---|
| `$4000-$4007` | `kArg`/`kResult` | 8B | Kernel argument block (see below) |
| `$4008-$401F` | `savedSP` | 24B | Per-task saved stack pointer (the ONLY TCB data in C64 RAM) |
| `$4020-$4037` | `taskStackReuLo` | 24B | Per-task REU stack base lo (precomputed at boot) |
| `$4038-$404F` | `taskStackReuHi` | 24B | Per-task REU stack base hi |
| `$4050-$4067` | `taskState` | 24B | `0`=DEAD, `1`=ALIVE, `2`=PAUSED, `3`=SLEEPING, `4`=SWAPPED (code evicted; scheduler skips, `resume` refuses) |
| `$4068` | `totalTasks` | 1B | Runtime scheduler scan range |
| `$4069-$4080` | `taskNameLo` | 24B | Task name string pointers (lo) |
| `$4081-$4098` | `taskNameHi` | 24B | Task name string pointers (hi) |
| `$4099-$40B0` | `taskPriority` | 24B | Priority 0-5 |
| `$40B1-$40C8` | `taskSliceLeft` | 24B | Slices remaining this round |
| `$40C9-$40E0` | `screenAlloc` | 24B | `1` = task has an allocated surface |
| `$40E1-$40F8` | `screenOwner` | 24B | `$FF`=owns, index=shares another's screen |
| `$40F9-$4110` | `taskDataPtrLo` | 24B | Per-instance data buffer pointer (lo) |
| `$4111-$4128` | `taskDataPtrHi` | 24B | Per-instance data buffer pointer (hi) |
| `$4129-$4140` | `taskDataSize` | 24B | Bytes allocated for this instance |
| `$4141-$4158` | `taskParent` | 24B | Parent task index (`$FF` = none) |
| `$4159-$4170` | `taskThreadIdx` | 24B | Counter for `threadSpawn` naming |
| `$4171-$4188` | `taskThreadNameReuLo` | 24B | Per-task REU address of the generated `parent.N` thread name (lo) |
| `$4189-$41A0` | `taskThreadNameReuHi` | 24B | … (hi) |
| `$41A1-$41A2` | `dataHeap` | 2B | Bump allocator pointer into `$1D40-$1FFF` |
| `$41A3-$41A4` | `dataHeapEnd` | 2B | End of data heap (`$2000`) |
| `$41A5-$41BC` | `taskZpBase` | 24B | ZP DMA base (0=disabled) |
| `$41BD-$41D4` | `taskZpLen` | 24B | ZP DMA length |
| `$41D5-$41EC` | `taskZpReuLo` | 24B | Precomputed REU ZP shadow address (lo) |
| `$41ED-$4204` | `taskZpReuHi` | 24B | … (hi) |
| `$4205-$421C` | `screenKind` | 24B | `0`=none, `2`=hires-text, `3`=mc-graphics |
| `$421D-$4234` | `taskGfxReuLo` | 24B | REU surface-slot address (lo) |
| `$4235-$424C` | `taskGfxReuHi` | 24B | … (hi) |
| `$424D-$4264` | `taskGfxReuBank` | 24B | … (bank) |
| `$4265-$427C` | `taskGfxBorder` | 24B | Per-task bitmap border color |
| `$427D-$4294` | `taskGfxBg0` | 24B | Per-task bitmap bg0 color |
| `$4295-$42AC` | `taskGfxBg1` | 24B | Per-task bitmap bg1 color |
| `$42AD-$42C4` | `taskGfxBg2` | 24B | Per-task bitmap bg2 color |
| `$42C5-$42D0` | `reuFs*` | 12B | REU FS state: dirBase/dataBase (lo/hi/bank), capacity (lo/hi/2), `reuTotalBanks` (word), `reuFsEnabled` |
| `$42D1-$42DD` | `reuFs*` | 13B | `reuFsNameTmp`, `reuFsPtr` (3B, 24-bit), `reuFsRemain`, `reuFsFile`, `reuFsLen`, `reuFsFlags`, `reuFsName` |
| `$42DE-$4303` | `cmdArgsBuf` | 38B | Foreground-command args buffer (shell writes, command tasks read) |

---

## Surface Slot Layout (REU, bank 1+, 10 KB per slot)

| Offset | Size | Content |
|---|---|---|
| `+$0000` | 8KB | Pixels (hires bitmap, 320×200) |
| `+$2000` | 1KB | Video matrix (hires: color nibbles; mc: colors) |
| `+$2400` | 1KB | MC color RAM |
| `+$23E8` | 2B | Cursor column/row (matrix tail) |
| `+$23EA` | 1B | Cursor enable (matrix tail) |
| `+$23EB` | 1B | Saved matrix byte under the block (save/restore blink) |
| `+$23EC` | 2B | Saved column/row — block-OFF position (save/restore blink) |
| `+$23EE` | 2B | Scroll region top/bottom (matrix tail) |
| `+$23F0` | 8B | Saved glyph bytes — block-OFF (save/restore blink) |

---

## Screen Buffer Layout — ⚠️ LIVE FRAMEBUFFER (all-bitmap model)

> `$2000-$3FFF` holds the **displayed surface's pixels** (hires bitmap,
> 8KB) and `$0400-$07FF` its video matrix. Every view switch DMAs the
> current surface back to its REU slot and the incoming surface into the
> framebuffer (`surfSave`/`surfLoad` in `gfx.inc`). Surfaces **never live
> permanently in this range** — all 28 slots are in REU (bank 1+, 10 KB
> each). Never place permanent code or kernel data here.

```
$2000 ┌──────────────────── framebuffer — 8KB pixel data
      │  320×200 hires bitmap; cell N at (row*40+col)*8 bytes
$3FFF
$0400 ┌──────────────────── video matrix — 1KB, hires color nibbles
$07E8 │  cursor col / row (matrix tail)
$07EA │  cursor enable
$07EB │  saved matrix byte (save/restore blink)
$07EC │  saved col / row (block-OFF position)
$07EE │  scroll region top / bottom
$07F0 │  saved glyph bytes ×8 (block-OFF)
$07FF
```

`kAllocScreen(mode)` allocates a REU slot (mode 0 = hires-text,
1 = mc-graphics), fills it (pixels = 0, matrix bg nibble = bg0), and
`doGfxSwitch` brings it into the framebuffer when the task gains focus.

### Framebuffer Matrix Tail (offsets within `$0400-$07FF`)

| Offset | Constant | Size | Content |
|---|---|---|---|
| `+$3E8` | `GFX_CURSOR_COL` | 1B | Cursor column |
| `+$3E9` | `GFX_CURSOR_ROW` | 1B | Cursor row |
| `+$3EA` | `GFX_CURSOR_ON` | 1B | Cursor enable (`cursorOn`) |
| `+$3EB` | `GFX_CURSOR_NIB` | 1B | Saved matrix byte under the block |
| `+$3EC` | `GFX_CURSOR_SCOL` | 1B | Saved column (block-OFF position) |
| `+$3ED` | `GFX_CURSOR_SROW` | 1B | Saved row (block-OFF position) |
| `+$3EE` | `GFX_SCROLL_TOP` | 1B | Scroll region top |
| `+$3EF` | `GFX_SCROLL_BOTTOM` | 1B | Scroll region bottom |
| `+$3F0` | `GFX_CURSOR_GLYPH` | 8B | Saved glyph bytes (block-OFF) |

The same tail layout exists in every surface slot at `slot + $23E8`
(`GFX_CURSOR_*`); the scheduler syncs the focused task's cursor state
between the framebuffer tail and its slot tail on context switches.

---

## TCB Layout (stack images in REU)

Each task's 256-byte stack image (`$0100-$01FF`) lives in REU (bank 0,
`task × 256`), DMA-swapped on every context switch. The only per-task TCB
data kept in C64 RAM is `savedSP`.

| Where | Size | Field |
|---|---|---|
| C64 `$4008 + index` | 1B | `savedSP` — stack pointer when preempted (`$F7` initially) |
| REU `taskStackReu + savedSP` | 256B | Stack image — copy of `$0100-$01FF`. Only the used portion (`$0100 - savedSP` bytes) is DMA'd per switch (typically ~9B for idle tasks). |

---

## I/O Region (`$D000-$DFFF`)

All registers are mirrored within their allocated blocks. No usable RAM exists in this range.

| Range | Device | Registers |
|---|---|---|
| `$D000-$D02E` | VIC-II | 47 registers: sprite positions, raster line, screen control (`$D011`, `$D016`, `$D018`), border/bg colors (`$D020`-`$D023`), sprite colors. Mirrored every 64 bytes through `$D3FF`. |
| `$D400-$D41C` | SID #1 | 29 registers: 3 voice oscillators (freq, pulse width, waveform, ADSR), filter cutoff/resonance/mode, volume. Mirrored every 32 bytes through `$D7FF`. |
| `$D800-$DBFF` | Color RAM | 1KB of 4-bit SRAM (nybbles). Stores foreground color per screen cell. Not affected by `$01` banking. Saved/restored on screen switch via REU DMA. |
| `$DC00-$DC0F` | CIA #1 | 16 registers: Port A (`$DC00`, keyboard matrix column drive), Port B (`$DC01`, keyboard row read), Timer A (`$DC04`-`$DC05`, scheduler tick), Timer B (`$DC06`-`$DC07`), ICR (`$DC0D`, IRQ ack), CRA (`$DC0E`, continuous mode). Mirrored every 16 bytes through `$DCFF`. |
| `$DD00-$DD0F` | CIA #2 | 16 registers: Port A bits 0-1 (`$DD00`) = VIC-II bank select. Disabled via `$DD0D = $7F`. Mirrored every 16 bytes through `$DDFF`. |
| `$DE00-$DEFF` | Open bus / REU | REU uses some addresses in this range on some hardware revisions. |
| `$DF00-$DF0F` | REU | 16 registers: status (`$DF00`), command (`$DF01`), C64 addr (`$DF02`-`$DF03`), REU addr (`$DF04`-`$DF06`), transfer length (`$DF07`-`$DF08`), control (`$DF0A`). Boot halts if REU not detected. |

---

## EhBASIC Memory (`basic.tsk`)

Gordon Basic (`basic.tsk`, relocatable) is loaded from the REU FS by
`run basic` — it is **not** embedded in the kernel PRG
(`tools/build-reu.ps1` pre-seeds it).

| Parameter | Value |
|---|---|
| Binary | `basic.tsk` — relocatable (`BASIC_FLAGS=$01` = RELOCATABLE), code ≈ 16.2KB + 256B header + fixup tail; loads into the task pool (relocatable, nominal origin `$5000`). Single-instance — `run basic` twice → `? already running` |
| Program RAM | Persistent 64 KB REU **working file** `basicwrk` — `run basic` reuses it if present and creates it if absent; deleted on `EXIT` (a crash leaves it for the next run); the 5-byte file record is handed to BASIC in the instance buffer (`dataPtr`) |
| `ram_base`/`ram_top` | REU working-file offsets `$0000-$FFFF` — no pinned C64 region |
| `data_size` | 12 (file record + line-buffer control) |
| Input buffer | `ibuffs` — **pinned page 2**, `$0221-$02A0` (127B): `ibuffs = vec_sv+$16` where `vec_sv = $020B` is a fixed address (`ehbasic.asm:490`). It is **not** derived from the task's data region. Together with `$0200-$020C` this makes `$0200-$02A0` EhBASIC's (see "NOT Free") |
| ZP DMA | header declares `zp_base=$04`, `zp_len=$EC` (preserves `$04-$EF` across context switches) |

---

## REU Layout

### C64 Stack Images (bank 0)
| REU Offset | Size | Owner |
|---|---|---|
| `$000000-$0017FF` | 6KB | Task stack images (24 × 256B) |
| `$001800-$001FFF` | 2KB | (free) |

### Char Shadows (bank 0) — live, opt-in
| REU Offset | Size | Owner |
|---|---|---|
| `$002000-$007FFF` | 24KB | **Live char shadows (opt-in)** — 24 × 1KB screen-code mirrors at `SHADOW_BASE + gfxSlot×$400` (`kSetCharShadow`) |

### ZP DMA Shadows (bank 0)
| REU Offset | Size | Owner |
|---|---|---|
| `$008000-$00967F` | ~5.6KB | Per-task ZP shadows (24 × max 240B) |
| `$009700-$0097BF` | 192B | Per-task kArg/kResult shadows (24 × 8B) — **page-aligned on purpose** (`$9700`): the scheduler forms the address as `task × 8` with no add, which needs the base's low byte to be 0 and the whole table to fit one page (both asserted in `main.asm`) |
| `$0097C0-$009FFF` | ~2.6KB | (free) |

### REU_BOUNCE + dead seed data (bank 0)
`$A000-$BDFF` is the `REU_BOUNCE` scroll/fill bounce (max 7680B).
`$BE00-$BFFF` is dead. The boot task seeds the whole region each boot;
the first scroll clobbers it — harmless.

### Per-task sprite state (bank 0)
| REU Offset | Size | Owner |
|---|---|---|
| `$00C000-$00C17F` | 384B | Thread names (24 × 16B) — the `parent.N` names `ps` prints |
| `$00C180-$00C3FF` | 640B | (free) |
| `$00C400-$00CFFF` | 3KB | **Per-task sprite state, 24 × 128B** at `REU_SPR_BASE + slot × 128` — the sheet records, the 39-byte shadow and the frame indices (71B used per block). Page-aligned on purpose: the block address is `slot × 128` with no add, so the base's low byte must be 0 (asserted in `main.asm`). Only the display owner's copy is live in kernel RAM; `sprInstall` swaps them with the display, and `warmSpriteReset` zeroes the region at a warm reboot |
| `$00D000-$00D2CF` | 720B | **`grpaint`'s saved UI band** — the canvas's bottom two cell rows as the task found them: 640 pixel bytes at `$D000` and 80 matrix bytes at `$D280`, kept only while the palette is up so the release can put them back (`gpDma` in `src/tasks/dynamic/grpaint.inc`). The band's own image — the palette and the tools — is not here: it is the REU-FS file `gpui.bin` -- and `gpui_mc.bin` for the multicolour band
-- written by `tools/gen-ui.py`. Bank 0 is free below the FS (which starts at bank 5 `$9000`), so the save costs the filesystem no capacity |
| `$00D2D0-$00FFFF` | ~11.3KB | (free in bank 0) |

### Bitmap Slots (banks 1+)
28 slots × 10KB each at `$010000-$055FFF` (slot N = `$010000 + N×$2800`):

| Offset within slot | Size | Content |
|---|---|---|
| `+$0000` | 8KB | Pixel data |
| `+$2000` | 1KB | Video matrix |
| `+$2400` | 1KB | MC color RAM |
| `+$23E8` | 2B | Cursor column/row (matrix tail) |
| `+$23EA` | 1B | Cursor enable |
| `+$23EB` | 1B | Saved matrix byte under the block |
| `+$23EC` | 2B | Saved column/row (block-OFF position) |
| `+$23EE` | 2B | Scroll region top/bottom |
| `+$23F0` | 8B | Saved glyph bytes (block-OFF) |

### REU Full Summary
| REU Offset | Size | Usage |
|---|---|---|
| `$000000-$0017FF` | 6KB | Stack images |
| `$001800-$001FFF` | 2KB | (free) |
| `$002000-$007FFF` | 24KB | Live char shadows (opt-in, 24 × 1KB) |
| `$008000-$00967F` | ~5.6KB | ZP DMA shadows |
| `$009700-$0097BF` | 192B | kArg/kResult shadows (24 × 8B) — page-aligned so the address is just `task × 8` |
| `$0097C0-$009FFF` | ~2.6KB | (free) |
| `$00A000-$00BDFF` | ~7.5KB | Scroll bounce (7680B) + `kReuFillC64` fill byte |
| `$00BE00-$00BFFF` | ~0.5KB | (free) |
| `$00C000-$00C17F` | 384B | Thread names (24 × 16B) |
| `$00C180-$00C3FF` | 640B | (free in bank 0) |
| `$00C400-$00CFFF` | 3KB | **Per-task sprite state (24 × 128B)** — one block per task slot, swapped with the display |
| `$00D000-$00D59F` | 1440B | **`grpaint`'s UI band images** ([gordonpaint.md](gordonpaint.md)) — the palette/tools pixels (640B), their matrix (80B), and the band's saved pixels and matrix (the same two sizes, see the table above). Four REU DMAs per show or hide, so the task's code image holds no copy of the band |
| `$00D5A0-$00FFFF` | ~10.6KB | (free in bank 0) |
| `$010000-$055FFF` | 280KB | Bitmap slots (28 × 10KB, banks 1+) |
| `$056000-$058FFF` | 12KB | (free — gap between bitmap slots and FS) |
| `$059000-$FAFFFF` | ~15.7MB | REU filesystem (16 KB directory + 24-bit data region, banks 5–250, capacity `$F53000`) — see table below |
| `$FB0000-$FBFFFF` | 64KB | `grpaint`'s **undo/redo ring** ([gordonpaint.md](gordonpaint.md)) — six 10,240-byte canvas states (a `.pic` payload plus the mode and the palette), bank 251 |
| `$FC0000-$FFFFFF` | 256KB | Malloc shadow (banks 252–255, 32 KB/slot × 8 dyn slots) |

### REU Filesystem (banks 5+, multi-bank)
| REU Offset | Size | Usage |
|---|---|---|
| `$059000-$05CFFF` | 16KB | Directory (512 entries × 32 bytes, bank 5) |
| `$05D000-$05FFFF` | 12KB | Data region — bank 5 tail (`REU_FS_BANK5_CAP = $3000`) |
| `$060000-$06FFFF` | 64KB | Data region — bank 6 (+`$10000` per additional bank, up to bank 250) |
| `$FA0000-$FAFFFF` | 64KB | Data region — the highest bank the filesystem may use. `reuFsCapacity` is `$3000 + (banks - 11) × $10000`, so the last data byte is `$FAFFFF` and the undo band above it can never be allocated into |
| `$FC0000-$FFFFFF` | 256KB | **Malloc shadow** — banks 252–255, 32 KB/slot × 8 dyn slots (bank `252 + slot>>1`, within-bank offset `(slot&1)<<7`) |

Capacity formula (24-bit): `$3000 + (reuTotalBanks − 10) × $10000` — byte0 = `$00`, byte1 = `$30`, byte2 = `max(0, totalBanks − 10)` (= `$F6` at 256 banks). The top 4 banks (252–255) are reserved for the malloc shadow.
For 16MB REU (256 banks): the FS data region spans banks 5–251, capacity ≈ 15.8 MB (`$F63000`).

---

## Free Memory Summary (C64 RAM)

Free ranges in C64 RAM, recomputed from the KickAssembler build map (every
range below is a gap between two emitted blocks or the tail of a pinned
pocket). `tools/verify-map.ps1` checks this exact set: `-ExpectTotal 127
-ExpectPockets 22` are its built-in defaults — no arguments needed.

> **The jump-table addresses in the docs have their own gate:**
> `tools/verify-jumptable-docs.ps1`. It pairs every `` `kName` `` in a
> `docs/kernel.md` section heading with the `$XXXX` that follows it and compares
> that against `src/kernel/jumptable.inc` — which `main.asm`'s `.assert`s pin to
> the assembled table, so `jumptable.inc` is the authority. A stale address is
> worse than a missing one: a task that assembles against the doc calls whatever
> now lives there. Two traps are documented in the script: a heading may list
> several entries on one line (pair each address with the name *before* it), and
> a stale address can collide with another entry's correct one (one routine's
> address can be another's), so repairs must be scoped to a section's own
> heading, never mapped globally.
>
> `tools/verify-inventory-docs.ps1` is the companion gate for
> [`kernel-call-inventory.md`](kernel-call-inventory.md) and
> [`library-call-inventory.md`](library-call-inventory.md): it checks every
> address those two quote (table rows and detail sections alike, 196 of them)
> against `jumptable.inc`, plus the alias rows
> (`kFreeBitmap` must resolve to the same address as `kFreeScreen`). Both gates
> read the whole `.const` list, trailing comments included — an end-of-line
> anchor in the pattern would silently skip every entry that has one, which is
> most of the table.

| Range | Size | Notes |
|---|---|---|
| `$020D-$021E` | 18B | Free — below the BASIC stub. ⚠️ Never usable for kernel code: KickAssembler writes PRG blocks in ascending address order and VICE's autostart treats the first block as the load base |
| `$02A1-$02BF` | 31B | Free — the rest of the only free run in pages 2-3 (`$0200-$02A0` is EhBASIC's; see NOT Free); `$02C0-$03FF` is sprite slots 0-4. ⚠️ Below `$0801`, so never usable for kernel code |
| `$080D-$080F` | 3B | Free — the tail of the BASIC loader block |
| `$0EFE-$0EFF` | 2B | Free — the gap under the high sprite band (`$0F00-$0FBF` is slots 5-7); the core's last block ends at `$0EFD` |
| `$0FC0-$0FC9` | 10B | `libNameMouse` — the `"mouse.lib"` name string, in the relocation slack above the high band |
| `$0FCA-$0FCB` | 2B | Free — the rest of that slack. `$0FC0` is deliberately **not** a slot: eight is the VIC's ceiling |
| `$13C5-$13D3` | 15B | Free — the kernel core's growth headroom (the core's linear end is `kernelCoreEnd` at `$13C5`). ⚠️ Never park a routine at the bottom of this run: it is the core's only spare space |
| `$1844-$186E` | 43B | `printGlyphAt` (40B, `$1844-$186B`) + 4B free — above `sprite.lib`'s name string (`$1839-$1843`, 11B) and `warmBootReset` (28B at `$181D-$1838`), below `taskLo` at `$186F` |
| `$1C6A-$1C6D` | 4B | Free — the tail of the `$1A1B` stub block, 4B below `sysExit` at `$1C6E` (the block's limit is asserted in `main.asm`) |
| `$1CBC-$1CBF` | 4B | Free — above `sysExit`+`seClean` (`sysExitMovedEnd <= $1CC0`) |
| `$1D14-$1D15` | 2B | Free — the tail of the frame routine's pocket, above `sprFrameDma` (86B) and below `kLibHold` |
| `$52C1-$52CC` | 11B used + 1B free | `kbScreenGate` (11B, `$52C1-$52CB`) — the switch path's entry for a display change the key scan recorded — then 1B free at `$52CC` |
| `$5337-$533F` | 9B | Free — the loader's growth budget: after `sprInstall` + the state mover (`$52DC-$5336`) and before `font-help.inc` at `$5340` |
| `$54A2-$54AA` | 9B | Free (rest of the loader band after `cursor-helpers.inc`: `pool-top.inc` 101B at `$53F2-$5456`, `cursor-helpers.inc` 43B at `$5457-$5481`, `slot-shadow.inc` 32B at `$5482-$54A1`) |
| `$56FB-$56FF` | 5B | Free — headroom below the pool, after `rasterCommit` (126B at `$567D-$56FA`) |
| `$CA1B-$CA2B` | 17B | `warmClearBufRecs` (kernel/warm-boot-reset.inc) — clears every slot's `taskDataSize`/`taskDataPtrLo/Hi` at a warm reboot, `jsr`-ed from `warmBootReset`. Between the REU DMA routines in `reu.inc` (ending `$CA1A`) and the sprite API (`$CA2F`) |
| `$CA2C-$CA2E` | 3B | Free — the tail of that run |
| `$CA6B-$CA8B` | 33B | `printGlyphAt`'s tail (32B, `$CA6B-$CA8A`) + 1B free — the pocket after `kSpriteCollide` + `clearSlotSprite` (60B at `$CA2F-$CA6A`), below `dlEvMaybeSelf` (13B at `$CA8C-$CA98`). The routine is split here by SIZE and its two halves are joined by a `jmp` |
| `$CD5C-$CD6C` | 17B | Free (between `dynTaskLibMask` and the scroll-region data; the library-failure policy lives in the `$1A17` stub block) |
| `$CDCF-$CDDD` | 15B | `kbApplyScreenReq` (14B, `$CDCF-$CDDC`) + `kbScreenReq` (1B at `$CDDD`) — the deferred display switch, applied from the scheduler's switch path so it never lands in a running task's `kArg` block. `sprBlkAddr` + `sprRestoreFrames` are 48B at `$CD9F-$CDCE`, before it |
| `$CDF5-$CDFD` | 9B | `blitGlyphFb` — the framebuffer glyph blitter, placed here so the code chain keeps its growth room (see `$FC3E`); + 2B free at `$CDFE-$CDFF` |
| `$E0F3-$E0F8` | 6B | `kPrintGlyphAt` (3B at `$E0F3`) then `kMouseCall` (3B at `$E0F6`) — the `$E000` band's own slack, where jump table group 2 stops. **No spare entry left** |
| `$E105-$E106` | 2B | Free (between the gfx table and the filesys stubs) |
| `$E119` | 1B | Free (vector headroom) |
| `$ECBD-$ECDB` | 31B | `paRoute` (`scroll-region.inc`) — `kPrintCharAt`'s surface router, filling the pocket above `gfx.inc`'s anchor exactly |
| `$FC3A-$FC3E` | 5B | — | ✓ Free — the code chain's growth room below the `$FC3F` gfx scratch pin |
| `$FFE9-$FFF5` | 13B | `gfxSurfPrep`'s tail (the cursorRow/cursorOn stores, `jmp`ed to from `$CD5C`); `$FFF6-$FFF9` free above the library-entry block and `kLibHold` |
| **Total (fixed headroom)** | **127B across 22 pockets** | ⚠️ This EXCLUDES the **512B of sprite slots (8 × 64B)**, which `verify-map.ps1` carves out because the map cannot show them. The sprite feature occupies **~1.1KB** in total: those 512B of fixed slots plus the code (`sprInstall` 91 + `warmSpriteReset` 35 + the helpers 48 + `kSpriteCollide`/`clearSlotSprite` 60 + `sprFrameDma` 86 + `rasterCommit` 126), the five entry stubs, the 71-byte per-task state block and the per-task REU blocks. `tools/verify-map.ps1` pins this total and the pocket count (its `-ExpectTotal` / `-ExpectPockets` defaults) and recomputes the runs from the build map, so the map stays the authority. Keep the free runs as long, clean runs rather than splitting them: every reader of this table budgets from the total | |

Usable beyond the fixed headroom:

| Range | Size | Notes |
|---|---|---|
| `$1D40-$1FFF` | 704B | Data heap (bump allocator, per-instance task data; `dataHeap` resets to `$1D40` on warm reboot) |
| `$5700-$C3FF` | ~27.25KB | Task pool (109 × 256B pages) — task code grows **up** from the bottom, `.lib` libraries are placed **down** from the top |
| `$D000-$DFFF` | 4KB | Bankable I/O RAM (`$01=$34`) — requires disabling I/O |

### Library pool footprints

A `.lib` file's **code** is allocated from the **top** of the pool when the library loads and is
released when its last holder lets go, so a library's footprint is its code rounded up to
256-byte pages. The sizes are the build's own (its `N bytes of code` line per library), and
`tools/check-pool-budget.ps1` folds that sum, a task's own code, every library it holds
while alive — the eager ones its `libMask` names plus the lazy ones it loads — and the
`kMalloc` blocks it holds into the `? no space in pool` test:

| Library | Code | Pool pages |
|---|---|---|
| `time.lib` | 213 B | 1 |
| `filesys.lib` | 2438 B | 10 |
| `gfx.lib` | 6680 B | 27 |
| `fp.lib` | 2039 B | 8 |
| `string.lib` | 335 B | 2 |
| `sid.lib` | 3318 B | 13 |
| `ipc.lib` | 638 B | 3 |
| `sprite.lib` | 224 B | 1 |
| `mouse.lib` | 309 B | 2 |

A task's live footprint is its own code plus whichever of these it holds while it runs — the
eager ones its `libMask` names at spawn, and any lazy one its startup touches. The pool is 109
pages.

### NOT Free (commonly mistaken)

| Range | Why |
|---|---|
| `$0200-$02A0` | **EhBASIC page-2 block** — `ccflag`/`ccbyte`/`ccnull`/`vec_cc` (`$0200-$0204`), the four `vec_*` I/O vectors (`$0205-$020C`), and `ibuffs` (`$0221-$02A0`, 127B). `basic` only just fits and only after the shell is evicted — do not move or reuse this |
| `$0400-$07FF` | Bitmap video matrix — VIC-II reads this during bitmap mode |
| `$02C0-$03FF` | **Sprite slots 0-4** (5 × 64B, the low band) — the VIC fetches sprite pixels from here whenever a sprite is enabled, and a task may write a slot's pixels directly |
| `$0F00-$0FBF` | **Sprite slots 5-7** (3 × 64B, the high band) — the VIC fetches sprite pixels from here, and a task may write a slot's pixels directly. `$0FC0` is deliberately not a slot |
| `$13D4-$1795` | REU filesystem: `reuDirBuf` (256B) + FS code |
| `$1796-$181C` | `spawnCore`'s relocated first 132B + the 3-byte `jmp` seam back to the byte-identical remainder at `$0FCC` |
| `$529E-$52C0` | `warmSpriteReset` (a reboot unpublishes the sprite state, forgets which slot is installed and zeroes every task's REU block; called by `warmBootReset` and by the cold boot) |
| `$186F-$189E` | `tasks.inc` — `taskLo`/`taskHi` lookup tables |
| `$189F-$1A16` | Static data — lib tables (+ growth reservoir) + gfx LUTs + task font/shadow |
| `$1A17-$1C6D` | `libstubs.inc` (lazy call stubs) |
| `$1C6E-$1CBB` | `sysExit` + `seClean` |
| `$1CC0-$1D15` | `sprFrameDma` (frame-load routine; `$1CC0-$1D3F` is its pocket, shared with `kLibHold`) |
| `$2000-$3FFF` | Live framebuffer — never general-purpose RAM |
| `$4000-$4303` | Kernel data (`kArg`/`kResult`, `savedSP`, per-task arrays, REU FS state, `cmdArgsBuf`) |
| `$4304-$430F` | `freeList` (orphan free-list) |
| `$4310-$529D` | Dynamic task loader (`dynload.inc` — can grow; `dlProbeFit` and `warmSpriteReset` follow it, then nothing may be pinned directly after it) |
| `$5340-$53F1` | `font-help.inc` (REU font helpers; its `fs-offset.inc` macro expansions live here too) |
| `$53F2-$5456` | `pool-top.inc` (library pool placement + caller-eviction accounting) |
| `$54AB-$567C` | `scrollScreenSlot` (background slot scroll up) |
| `$567D-$56FA` | `rasterCommit` — the per-frame vblank sprite commit (shadow → `$D000-$D02E`, `$D010`, sprite pointers, collision latch, deadline guard, frame counter) |
| `$5700-$C3FF` | The task pool (109 × 256B pages) |
| `$C400-$C7FF` | `scratchBuf` |
| `$C800-$CA2E` | `reu.inc` + `math.inc` |
| `$CA2F-$CA6A` | `kSpriteCollide` (the resident collision reader) + `clearSlotSprite` (zeroes a recycled slot's sprite block at spawn) |
| `$CA99-$CC75` | Dynamic task tables + malloc table + per-task buffers |
| `$CC76-$CD0B` | Boot task code |
| `$CD0C-$CD4B` | Lib descriptors |
| `$CD4C-$CD5B` | `dynTaskLibMask` |
| `$CD6D-$CD9E` | `taskScrollTop`/`taskScrollBottom`/`scrollSeedBuf` |
| `$CD9F-$CDF4` | `sprBlkAddr` + `sprRestoreFrames` (48B) + the five public `kSprite*` entry stubs (15B — four of them **are** `sprite.lib`'s call entries) + `sprPtrBytes` (8B) |
| `$CE00-$CFA3` | Char-shadow code |
| `$CFA4-$CFFF` | The per-task sprite state — one contiguous 71-byte run (24B sheet records + 39B shadow + 8B frame indices, DMA'd per hand-over) followed by `spriteSlotLo/Hi`, `sprLiveOwner`, `sprPubMask`, the 2B collision latch and `sprFrameCount` (**92B**) |
| `$D000-$DFFF` | I/O region — VIC-II, SID, CIA, Color RAM, REU registers |
| `$E000-$E0C2` | Kernel jump table group 1 (65 entries, `kClearScreen`..`kBlinkReset`) |
| `$E0C3-$E0F2` | Kernel jump table group 2 (16 gfx/scroll entries) |
| `$E0F9-$E104` | filesys.lib in-place I/O stubs (`kReuCreate`/`kReuOpen`/`kReuReadAt`/`kReuWriteAt`) |
| `$E107-$E118` | `kStrcmp`/`kFillMatrix`/`kSetGfxMode`/`kFillColorRam`/`kFpCall`/`kReuDmaRange` |
| `$E11A-$E247` | Kernel vars (`kernel-vars.inc`) + `kmEvictAlloc` + the cascade root/flag bytes |
| `$E248-$EA70` | `screen-io.inc` + `keyboard.inc` |
| `$EA71-$ECBC` | `scroll-region.inc` (frag 1) |
| `$ECDC-$F6A3` | `gfx.inc` + `text-blit.inc` + `screen-mgmt.inc` + semaphore/screen-lock/task-util + `reuCmpName` |
| `$F6A0-$F97D` | `malloc.inc` (size ABI — the malloc tables are address-asserted) |
| `$F97E-$FACC` | `poolevict.inc` |
| `$FACD-$FC39` | `lib.inc` |
| `$FC3F-$FF7D` | gfx.lib scratch — flood-fill + `kEll*` + `kCircle*`, one block (no pin) |
| `$5457-$5481` | `cursor-helpers.inc` (`dlFindMaster`/`dlInstallCursor`) — loader band |
| `$5482-$54A1` | `slot-shadow.inc` (`clearSlotShadows` — zeroes a recycled slot's ZP shadow) |
| `$FF70-$FF7D` | gfx.lib circle scratch (`kCircle*`) — part of the `$FC3F-$FF7D` block |
| `$FFFA-$FFFF` | Hardware vectors |
