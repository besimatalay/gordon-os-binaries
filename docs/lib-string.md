# `string.lib` — Library Reference

String manipulation + byte formatting library (lib id 4, **lazy**). Shared +
refcounted like the other `.lib` binaries; loaded on first call by the lazy
jump-table stubs.

| | |
|---|---|
| Lib id | 4 |
| Entries | 7 |
| Load policy | lazy |
| Source | `src/libs/string.asm` |
| Kernel entry points | `kStrlen`, `kStrcpy`, `kStrcmp`, `kSkipSpaces`, `kByteToHex`, `kHexDigit`, `kNibbleToHex` |

The seven jump-table entries are lazy stubs — the first call cold-loads
`string.lib` and subsequent calls `jmp` through the resolved vector. The
signature is the kernel call's own, so a caller is written the same way
whether the routine is resident or lazily loaded. `kByteToDec` is resident
in the kernel (used by `syscall.inc` for `"parent.N"` thread names).

**Residency note:** the shell, `dir`, `ps`, and `del` declare lib id 4 in
their header `libMask` (`$0010`, shell/`del` `$0012` with filesys), so `string.lib`
is refcounted like any other lib and freed when the last declaring task
exits. `time.lib`/`filesys.lib` call into it as **undeclared** lib-to-lib
dependencies (libs carry `libMask = 0`), so after a free the next such
call cold-reloads it through the lazy stub. It occupies two pool pages
(512 B) after first use (the wildcard matcher pushed it past one page).

---

## Entry points

Call indices (base 26 = `time` 3 + `filesys` 9 + `gfx` 13 + `fp` 1):

| # | Entry | Signature |
|---|---|---|
| 26 | `strlen` | `(kPtr)` → A = length |
| 27 | `strcpy` | `(kPtr)` → `(srcPtr)`, null-terminated copy |
| 28 | `strcmp` | `(kPtr)` vs `(srcPtr)` → Z=1 equal/match; `kArg`=0 exact, `kArg`=1 wildcard (`*`/`?`) |
| 29 | `skipSpaces` | advance `kPtr` past `$20`; A = first non-space, C=1 at EOL |
| 30 | `byteToHex` | A → 2 hex chars at `(kPtr)` (lib-local `hexChars`) |
| 31 | `hexDigit` | screen-code hex digit → nibble; C=1 on failure |
| 32 | `nibbleToHex` | nibble (0–15) → screen-code hex char |

### `kStrlen` — `$E021`

Length of the null-terminated string at `(kPtr)`.

| | |
|---|---|
| **Input** | `kPtr` = string pointer |
| **Output** | A = length (0–255) |
| **Clobbers** | A, Y |

### `kStrcpy` — `$E024`

Copy the null-terminated string at `(kPtr)` to `(srcPtr)` (terminator
included). Pointers are **not** advanced.

| | |
|---|---|
| **Input** | `kPtr` = source, `srcPtr` = destination |
| **Output** | — |
| **Clobbers** | A, Y |

### `kStrcmp` — `$E107`

Compare/match two null-terminated strings. `kArg` selects the mode:

- `kArg` = 0 (exact): compare `(kPtr)` vs `(srcPtr)`. Z=1 equal, Z=0
  differ; A = last character compared.
- `kArg` = 1 (wildcard): `kPtr` = name, `srcPtr` = pattern. `*` matches
  any run (including empty), `?` matches any single char; mismatches
  backtrack to the last `*`. Z=1 match, Z=0 no match. Pointer-advancement
  walk — both strings are read via `(zp),y`, so there is no self-modifying
  code.

| | |
|---|---|
| **Input** | `kPtr`, `srcPtr` = strings; `kArg` = mode (0 exact, 1 wildcard) |
| **Output** | Z=1 equal/match; Z=0 differ/no-match |
| **Clobbers** | A, Y (exact); A, Y, `kPtr`, `srcPtr`, `kArg+2..kArg+7` (wildcard) |
| **Preserves** | X (both modes) |

`dir`'s `<pattern>` filter delegates here.

### `kSkipSpaces` — `$E075`

Advance `kPtr` past leading space characters (`$20`).

| | |
|---|---|
| **Input** | `kPtr` = string pointer |
| **Output** | `kPtr` advanced past spaces; A = first non-space char; C=1 if end-of-string |
| **Clobbers** | A, Y |
| **Modifies** | `kPtr` |

### `kByteToHex` — `$E027`

Convert a byte to two hex digit characters at `(kPtr)` (not advanced). Uses
a **lib-local** `hexChars` table, so there is no fixed-address dependency on
kernel data.

| | |
|---|---|
| **Input** | A = byte, `kPtr` = 2-byte destination |
| **Output** | — |
| **Clobbers** | A, X, Y |

### `kHexDigit` — `$E078`

Convert a screen-code hex digit to a nibble. Recognises `'0'`–`'9'`
(`$30`–`$39`) and `'a'`–`'f'` (`$01`–`$06`).

| | |
|---|---|
| **Input** | A = screen code |
| **Output** | C=0 + A = nibble (0–15); C=1 + A = 0 on failure |
| **Clobbers** | A |
| **Preserves** | X, Y |

### `kNibbleToHex` — `$E07B`

Convert a nibble (0–15) to its screen-code hex character (upper nibble of A
ignored).

| | |
|---|---|
| **Input** | A = nibble |
| **Output** | A = screen code (`'0'`–`'9'` = `$30`–`$39`, `'a'`–`'f'` = `$01`–`$06`) |
| **Clobbers** | A |
| **Preserves** | X, Y |

---

## Cold-path clobber note

On a **cold** call (the lib not yet loaded) the stub saves and restores
`A/X/Y`, `kArg[0..7]`, `kPtr`, `dataPtr`, and `srcPtr`, so `strcpy`/`strcmp`
inputs survive. `taskNamePtr`/`spawnPtr` are still clobbered on the cold
path (no lib routine uses them). Warm calls go straight through the
patched jump entry.
