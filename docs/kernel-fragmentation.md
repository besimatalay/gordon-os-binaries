# GordonOS — Kernel Code Fragmentation Survey

> Snapshot of where every resident kernel module currently lives.
> Verified against the KickAssembler `Memory Map` block printed by
> `tools/build-kernel.ps1`; `tools/verify-map.ps1` recomputes these runs and pins
> the totals. What those free bytes mean in practice — and every other limit the
> system has — is [limitations.md](limitations.md).

The kernel's code and data are emitted as ~34 contiguous blocks, spread
from `$0801` to `$FF7D`. Most files assemble contiguously; the table below
splits a block further where it is useful (the per-file split comes from
`build/gordon-os.dbg`, which maps every address to its source file).
`scroll-region.inc`/`scroll-slot.inc` are two fragments by design, and the
`main.asm`/`kernel.asm` data blocks are placed intentionally.

> This document is about **kernel code/data** placement. The *task pool* is a
> different kind of fragmentation (a load needs N **adjacent** free pages) and is
> documented as an accepted limitation in
> [programmers-guide.md](programmers-guide.md) § Pool fragmentation.

---

## Kernel layout, by address (low → high)

| Address | Size | File | What's there |
|---|---|---|---|
| `$0801-$080C` | 12B | `main.asm` | BASIC stub |
| `$0810-$0EFF` | 1776B | `init.inc` + `scheduler.inc` + `irq.inc` + `syscall.inc` (the dispatcher and its 28B jump table, which ends at `$0EFF`) | Kernel core part 1 |
| `$0EFB-$0EFF` | 5B | — | free — the gap under the high sprite band |
| `$0F00-$0FBF` | 192B | (VIC) | **sprite slots 5-7** — three 64B VIC sprite data blocks the VIC fetches pixels from. Not free, and not kernel RAM |
| `$0FC0-$0FC9` | 10B | `main.asm` | `libNameMouse` -- the `"mouse.lib"` name string (`libNameLo/Hi[8]` points at it), in the relocation slack above the band |
| `$0FCA-$0FCB` | 2B | — | free — the rest of the band's relocation slack |
| `$0FCC-$13C1` | ~1.0KB | `syscall.inc` | Kernel core part 2 — `spawnCore`'s remainder (its first 132B sit at `$1796`) + the rest of the syscall layer, ending at `kernelCoreEnd` |
| `$13C5-$13D3` | 15B | — | free — the kernel core's growth headroom (`kernelCoreEnd` is `$13C5`). ⚠️ Never park a routine at the bottom of it: it is the core band's only spare space, and a change larger than it needs a relocation |
| `$13D4-$14D3` | 256B | `main.asm` | `reuDirBuf` |
| `$14D4-$1795` | 706B | `reu-fs.inc` | FS code (assembled after `reuDirBuf`) |
| `$1796-$181C` | 132B | `syscall.inc` | `spawnCore`'s relocated front half + the 3B `jmp` seam into the byte-identical remainder at `$0FCC` |
| `$181D-$1838` | 28B | `warm-boot-reset.inc` | `warmBootReset` — the warm-reboot entry point: releases every library, drops the sprite intent, then `jmp start` |
| `$1839-$1843` | 11B | `main.asm` | `sprite.lib`'s name string (`libNameSprite`, `"sprite.lib"`) — the `$FFxx` band has no room for it (`kLibHold` is pinned at `$FFE6`) |
| `$1844-$186E` | 43B | `kernel.asm` | `printGlyphAt` (40B, `$1844-$186B`) + 4B free -- the `kPrintGlyphAt` fixed-cell glyph writer, a leaf reached from its jump-table entry |
| `$186F-$189E` | 48B | `tasks.inc` | `taskLo`/`taskHi` |
| `$189F-$1A1A` | 380B | `main.asm` | lib runtime + `libJumpLo/Hi` + `libInitLo/Hi` (`LIB_CALLS` = 42 wide) + the spent `LIB_CALLS` growth point + gfx LUTs + font record/glyph scratch + `taskShadow`. ⚠️ The four tables end flush against `gfxRowLutLo`, so a further call index shifts this whole tail and every aliased copy of it |
| `$1A1B-$1C69` | 591B | `libstubs.inc` | lazy call stubs + their shared fail trampolines + `libColdSave`/`libColdRestore` + `libLoadFail` + `libFailExit` |
| `$1C6A-$1C6D` | 4B | — | free (the stub block's tail; `libStubsEnd` is asserted at `$1C6E`) |
| `$1C6E-$1CBB` | 78B | `syscall.inc` | `sysExit`+`seClean` — the task-exit path and its cleanup |
| `$1CC0-$1D15` | 86B | `sprite.inc` | `sprFrameDma` — the frame DMA (called by the library's `kSpriteFrame` and by `sprRestoreFrames`) |
| `$1D16-$1D3F` | 42B | `main.asm` | `kLibHold` — **fills this pocket exactly** (42B): there are no free bytes here |
| `$1D40-$1FFF` | 704B | — | data heap |
| `$4000-$4303` | 772B | `main.asm` | kernel data (kArg, TCB arrays, FS state) |
| `$4304-$430F` | 12B | `main.asm` | `freeList` |
| `$4310-$529D` | 3982B | `dynload.inc` | loader + `dlCopyArgs` + lib-lifecycle helpers (nothing may be pinned right after it — it grows) |
| `$529E-$52C0` | 35B | `sprite.inc` | `warmSpriteReset` — a reboot unpublishes the sprite state, forgets `sprLiveOwner` and zeroes every task's REU block; called by `warmBootReset` and by the cold boot |
| `$52C1-$52CC` | 12B | — | free |
| `$52CD-$52DB` | 15B | `kernel.asm` | `dlProbeFit` — asks the allocator whether a free run of X pages exists |
| `$52DC-$5336` | 91B | `sprite.inc` | `sprInstall` + `sprStateMove`/`sprStateLoad`/`sprDmaSetup` — the per-task sprite hand-over |
| `$5337-$533F` | 9B | — | free (loader headroom) |
| `$5340-$53F1` | 178B | `font-help.inc` | REU font helpers (`bootFontResolve` + `fontGlyph`); the `fs-offset.inc` macros it expands live here too |
| `$53F2-$5456` | 101B | `pool-top.inc` | library pool placement (`dlLibCore`, `allocFromPoolTop`, `dlAllocCode`) + caller-eviction accounting (`dlCallerAddLibs`, `dlCallerLibPages`) |
| `$5457-$5481` | 43B | `cursor-helpers.inc` | `dlFindMaster` (`$5457`) + `dlInstallCursor` (`$546F`) — the four loader-band helpers share one `.pc` chain |
| `$5482-$54A1` | 32B | `kernel/slot-shadow.inc` | `clearSlotShadows` — zeroes a new task's ZP shadow when its slot is reused |
| `$54A2-$54AA` | 9B | — | free |
| `$54AB-$567C` | 466B | `scroll-slot.inc` | `scrollScreenSlot` |
| `$567D-$56FA` | 126B | `sprite.inc` | `rasterCommit` — the vblank sprite commit: shadow → `$D000-$D02E`, `$D010` assembly, sprite pointers, collision latch, `sprPubMask` gate, deadline guard and the `frameCount` increment |
| `$56FB-$56FF` | 5B | — | free |
| `$5700-$C3FF` | 27.25KB | — | task pool (109 × 256B pages; tasks grow up, libs come down) |
| `$C400-$C7FF` | 1KB | `main.asm` | `scratchBuf` |
| `$C800-$C964` | 357B | `reu.inc` | DMA routines |
| `$C965-$CA2E` | 202B | `math.inc` | byteToDec, mul16/div16, random |
| `$CA2F-$CA6A` | 60B | `sprite.inc` | `kSpriteCollide` (the resident collision reader) + `clearSlotSprite` (zeroes a recycled slot's sprite block at spawn) |
| `$CA6B-$CA8B` | 33B | `kernel.asm` | `printGlyphAt`'s tail (32B, `$CA6B-$CA8A`) + 1B free -- the routine is split across two runs by SIZE and its halves are joined by a `jmp` |
| `$CA8C-$CA98` | 13B | `kernel.asm` | `dlEvMaybeSelf` — caller-self detection for eviction (`dlEvMark`/`dlEvMarkShared`) |
| `$CA99-$CC75` | 477B | `main.asm` | dyn task tables + malloc table + per-task buffers |
| `$CC76-$CD0B` | 150B | `boot.inc` | boot task |
| `$CD0C-$CD4B` | 64B | `main.asm` | lib descriptors |
| `$CD4C-$CD5B` | 16B | `main.asm` | `dynTaskLibMask` |
| `$CD5C-$CD6C` | 17B | — | free |
| `$CD6D-$CD9E` | 50B | `main.asm` | scroll region per-task data |
| `$CD9F-$CDCE` | 48B | `sprite.inc` | `sprBlkAddr` (slot → REU block address) + `sprRestoreFrames` (re-DMA every resolved frame on a hand-over) |
| `$CDCF-$CDDD` | 15B | — | free |
| `$CDDE-$CDEC` | 15B | `sprite.inc` | the five public sprite entry stubs — four of them **are** `sprite.lib`'s call entries, patched in place by `libLoad` |
| `$CDED-$CDF4` | 8B | `sprite.inc` | `sprPtrBytes` (VIC data pointer bytes, one per slot) |
| `$CDF5-$CDFD` | 9B | `kernel.asm` | `blitGlyphFb` — the framebuffer glyph blitter, kept out of the packed code chain (+ `$CDFE-$CDFF`, 2B free) |
| `$CE00-$CFA3` | 420B | `char-shadow.inc` | char-shadow code |
| `$CFA4-$CFFF` | 92B | `sprite.inc` | the per-task sprite state — one contiguous 71-byte run (24B sheet records + 39B shadow + 8B frame indices, DMA'd per hand-over) — then the kernel-only bytes: `spriteSlotLo/Hi`, `sprLiveOwner`, `sprPubMask`, the 2B collision latch and `sprFrameCount` (the per-frame clock) |
| `$E000-$E0C2` | 195B | `kernel.asm` | jump table group 1 (65 entries, `kClearScreen`..`kBlinkReset`) |
| `$E0C3-$E0F2` | 48B | `kernel.asm` | jump table group 2 (16 gfx/scroll entries) |
| `$E0F3-$E0F5` | 3B | `kernel.asm` | `kPrintGlyphAt` -- the `$E000` band's own slack, where jump table group 2 stops |
| `$E0F6-$E0F8` | 3B | `kernel.asm` | `kMouseCall` -- mouse.lib's one call entry, patched in place by `libLoad` |
| `$E0F9-$E104` | 12B | `kernel.asm` | filesys.lib in-place I/O stubs (`kReuCreate`/`kReuOpen`/`kReuReadAt`/`kReuWriteAt`) |
| `$E105-$E106` | 2B | — | free |
| `$E107-$E118` | 18B | `kernel.asm` | kStrcmp/kFillMatrix/kSetGfxMode/kFillColorRam/kFpCall/kReuDmaRange |
| `$E119` | 1B | — | free |
| `$E11A-$E247` | 302B | `kernel-vars.inc` | cursor/semaphore/keyboard/readString vars |
| `$E248-$E4CE` | 647B | `screen-io.inc` | screen + cursor + blit |
| `$E4CF-$EA70` | 1442B | `keyboard.inc` | keyboard scan + ring buffer + `readRow` |
| `$EA71-$ECBC` | 588B | `scroll-region.inc` (frag 1) | `setScrollRegion`/`scrollScreen`/`blitCharAt`/`blitCharAtRev` |
| `$ECBD-$ECDB` | 31B | `scroll-region.inc` | `paRoute` — `kPrintCharAt`'s surface router, filling the pocket above `gfx.inc`'s anchor exactly |
| `$ECDC-$F075` | 410B | `gfx.inc` | bitmap mode switch + surface alloc + `printCharAt`. ⚠️ **`.pc`-anchored at `$ECDC`**: its data addresses are ABI (gfx.lib hardcodes `gfxPixelMasks`/`gfxCol`/`dispIsBitmap`/`kLineX1Lo`/`kBoxColor`), so it must not drift when `scroll-region.inc` changes size |
| `$F076-$F195` | 288B | `text-blit.inc` | glyph blitters: `blitChar`/`blitFbCommon` (framebuffer) + `blitCharSlot`/`blitGlyphSlot` (REU slot); `blitGlyphFb` lives in the `$CDF5` pocket |
| `$F196-$F5A0` | 1035B | `screen-mgmt.inc` | surface alloc/free/share/view + `setGfxMode` |
| `$F5A1-$F5DA` | 58B | `semaphore.inc` | `semWait` + `semSignal` |
| `$F5DB-$F60B` | 49B | `screen-lock.inc` | `lockScreen` + `unlockScreen` |
| `$F60C-$F651` | 70B | `task-util.inc` | `getTaskName` |
| `$F652-$F69F` | 78B | `kernel.asm` | `reuCmpName` (filesys.lib helper) |
| `$F6A0-$F97D` | 734B | `malloc.inc` | `kMalloc`/`kFree` (page-granular) |
| `$F97E-$FACC` | 335B | `poolevict.inc` | `dlPreEvict`..`dlFreePages` |
| `$FACD-$FC39` | 365B | `lib.inc` | library loader + name strings |
| `$FC3A-$FC3E` | 5B | — | ✓ Free — the code chain's growth room. Growing past `$FC3E` trips the `$FC3F` anchor |
| `$FC3F-$FF7D` | 831B | `kernel.asm` (gfx.lib data) | **one contiguous block**: flood-fill span-seed stacks + `kEll*` ellipse scratch + `kCircle*` circle scratch. ⚠️ **`.pc`-anchored at `$FC3F`**: gfx.lib hardcodes these addresses, so the code ahead of it grows into the gap above the anchor instead of moving them |
| `$FF7E-$FFE8` | 107B | `main.asm` | `sid.lib` + `ipc.lib` call entries, lazy cold stubs and name strings, plus the `kLibHold` stub at the far end — the block that must stay the last thing assembled. ⚠️ **The gfx scratch band below it ends at `$FF7D` with ZERO slack**: any growth anywhere in the kernel's code band collides with this block and fails the build |
| `$FFE9-$FFF5` | 13B | `kernel.asm` | `gfxSurfPrep`'s tail (the `cursorRow`/`cursorOn` stores, `jmp`ed to from `$CD5C`) — `$FFF6-$FFF9` is free, the run above the `$FF7E` block
| `$FFFA-$FFFF` | 6B | — | hardware vectors |

---

## Fragmented files

| File | Fragments |
|---|---|
| `dynload.inc` | ✅ **1** — `$4310-$529D` (the band continues with `warmSpriteReset`, the free pocket upstream of `dlProbeFit`, and `sprInstall`) |
| `malloc.inc` | ✅ **1** — `$F6A0-$F97D` |
| `polevict.inc` | ✅ **1** — `$F97E-$FACC` |
| `scroll-region.inc` | frag 1 `$EA71-$ECBC` + `paRoute` `$ECBD-$ECDB`; `scrollScreenSlot` → `scroll-slot.inc` `$54AB-$567C` |
| `kernel.asm` | jump table `$E000-$E118` (no spare entry left — `kMouseCall` took the last one); `reuCmpName` `$F652`; `blitGlyphFb` `$CDF5`; the gfx.lib working RAM at `$FC3F-$FF7D` (one block) |
| gfx.lib working RAM | **1** — flood-fill + ellipse + circle all at `$FC3F-$FF7D` |
| `main.asm` | BASIC stub `$0801`; `reuDirBuf` `$13D4`; static data block `$189F-$1A16` (lib tables + LUTs + font record + taskShadow); `libHold` `$1D16-$1D3F` (the pocket below the data heap, filled exactly); kernel data `$4000-$4303` + `freeList` `$4304`; `scratchBuf` `$C400`; dyn tables `$CA99`; lib descriptors `$CD0C`; `dynTaskLibMask` `$CD4C`; scroll-region data `$CD6D`; sid.lib + ipc.lib entries + stubs + names + `kLibHold` `$FF7E-$FFE8` |
| `warm-boot-reset.inc` | **2 fragments** — `warmBootReset` `$181D-$1838` + `warmClearBufRecs` `$CA1B-$CA2B` |
| `sprite.inc` | **6 fragments** — `sprBlkAddr` + `sprRestoreFrames` + the 5 stubs + `sprPtrBytes` `$CD9F-$CDF4`, `warmSpriteReset` `$529E-$52C0`, `sprInstall` + the state mover `$52DC-$5336`, `sprFrameDma` `$1CC0-$1D15`, `rasterCommit` `$567D-$56FA`, `kSpriteCollide` + `clearSlotSprite` `$CA2F-$CA6A`, tables/state `$CFA4-$CFFF`. Deliberate: no free pocket is large enough for two of these together |
| `warm-boot-reset.inc` | **2 fragments** — `warmBootReset` `$181D-$1838` (the warm-reboot entry point: every library released, every task's sprite state forgotten, reached by re-pointing the scheduler's `jmp start`) + `warmClearBufRecs` `$CA1B-$CA2B` |
| `irq.inc` | `$0E76-$0EA5` — the interrupt dispatch, with two sources (VIC raster + CIA Timer A) |

---

## Constraints on any move

- Jump table (`$E000-$E118`) is at fixed addresses — moving it breaks every `jsr`/`jmp` in tasks and libs; treat as pinned.
- The `main.asm` data blocks are pinned by hardcoded aliases in
  `src/tasks/kernel-data.inc`, `src/libs/gfx.asm`, `src/tasks/dynamic/shell.asm`,
  `src/tasks/dynamic/basic.asm` — a move must update those aliases **and**
  the `.assert` guards in `main.asm` in the same change.
- `poolevict.inc` has four exact-address asserts (`kEllCxLo`, `kEllTemp`,
  `ffStkXLo`, `ffSeedBit`) — it cannot move without breaking `gfx.lib`.
- `.inc` files must stay listed in `project-config.json` `sources`.
- Largest free pockets (largest first, as `tools/verify-map.ps1` reports them):
  `$02A1-$02BF` (31B), `$020D-$021E`
  `$CD5C-$CD6B` (16B, `gfxSurfPrep`) and `$FFE9-$FFF5` (13B, its tail) are now code, leaving 1B and 4B
  respectively; next come `$13C5-$13D3` and
  `CDCF-CDDD` (15B each), then a tail of 12B-or-less remnants, for **176B free in
  total** across **25 pockets** (`$1844` and `$CA6B` hold `printGlyphAt`) - excluding
  the 512B of fixed sprite slots (`memory-map.md` has the full list). ⚠️ `$02A1-$02BF`
  and `$020D-$021E` are below `$0801`, so they can never hold kernel code, and
  nothing may occupy the core's growth headroom at `$13C5-$13D3`. The largest
  pocket there is 43B, which is why `kLibHold` (42B) had to be written to fit one
  exactly.
  ⚠️ Sprite data can only live in its two bands: `$1000-$1FFF` is char ROM *to the
  VIC* (sprite fetches included), so no address between the bands can hold a
  frame. `memory-map.md`'s *NOT free* table lists what else reads as free but is
  not - the EhBASIC page-2 block at `$0221-$02A0` is the largest of them.
- The loader band `$4310-$529D` grows with the loader: never sit kernel data
  directly after it - the band that follows it is `warmSpriteReset`, `dlProbeFit`
  and `sprInstall`, each pinned by an address assert.
