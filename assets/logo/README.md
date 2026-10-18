# Daedalus logo

A circular labyrinth — Daedalus built the labyrinth — drawn as broken
concentric rings, which is also what sound looks like: rings radiating from a
centre tone, with one way out. The exit faces upper right, the direction the
"done" tone rises. Two short radial walls make it a maze rather than a target.

| File | Use it for |
| :- | :- |
| `daedalus-icon.svg`, `daedalus-icon-{1024…48}.png` | App and marketplace icons, avatars. The primary mark. |
| `daedalus-icon-small.svg`, `daedalus-icon-{32,16}.png`, `favicon.ico` | 32px and under. Three rings stop resolving there, so this keeps two, with the same exit and wall. |
| `daedalus-logo.svg` / `.png` | The full logo on light backgrounds. |
| `daedalus-logo-dark.svg` / `.png` | The full logo on dark backgrounds. |
| `daedalus-mark.svg` | The bare mark, gold, on dark backgrounds. |
| `daedalus-mark-ink.svg` | The bare mark, navy, on light backgrounds — gold is too faint on white. |

Colours: navy `#121A2E`, brass `#E9B44C` (8.8:1 against the navy), paper `#F1ECE2`.

Everything here is generated — edit `tools/build_logo.py`, not these files:

```bash
python tools/build_logo.py          # SVGs, standard library only
python tools/build_logo.py --png    # PNGs and favicon.ico too; needs chrome-headless-shell
```

`tests/test_logo.py` fails if a committed SVG differs from what the generator
writes. The wordmark is Bitstream Charter Bold, outlined into paths so it needs
no font to render; Charter is licensed for any purpose without restriction.
