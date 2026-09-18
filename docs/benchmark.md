# Benchmark

The benchmark renders a matrix of synthetic images and decodes every one of
them; it reports a table of conditions, never a single headline number.

## Running it

```bash
pharmacode benchmark --seed 20260919
```

`--seed 20260919` is also the default, so a bare `pharmacode benchmark`
reproduces the run below. `--output DIR` changes where `results.md`,
`results.json` and the `failures/` directory are written (default
`benchmark-output`, which is git-ignored — nothing under it is committed).
`--quick` runs a small subset of conditions and values for CI instead of the
full matrix.

## What the matrix contains

Every condition renders 55 images: the 15 boundary values (3, 4, 5, 6, 7, 8,
13, 25, 91, 100, 1234, 12345, 65535, 123456, 131070 — every all-narrow,
all-wide, or otherwise structurally distinct case) plus 40 values drawn from a
seeded random generator over the full `[3, 131070]` range. 23 conditions, by
group:

- **clean** — `clean-300`: no distortion, 300 DPI.
- **rotation** — `rotation-90`, `rotation-180`, `rotation-270`: exact
  quarter/half turns; `tilt-plus-3`, `tilt-minus-3`: a 3-degree tilt either way.
- **dpi** — `dpi-150`, `dpi-600`: the same clean render at other resolutions.
- **blur** — `blur-1`, `blur-2`: Gaussian blur, sigma 1 and 2 px, at 300 DPI;
  `dpi-150-blur-1`: sigma 1 at 150 DPI.
- **noise** — `noise-10`, `noise-25`: Gaussian noise, sigma 10 and 25.
- **jpeg** — `jpeg-50`, `jpeg-30`: a JPEG round trip at quality 50 and 30.
- **contrast** — `contrast-0.4`: contrast reduced to 0.4.
- **illumination** — `illumination-0.5`: an illumination gradient losing up
  to half the brightness across the image.
- **perspective** — `perspective-3`: a 3-degree perspective tilt.
- **scale** — `scale-0.7x1.3`: non-uniform scaling, 0.7x horizontal, 1.3x
  vertical, decoded without `--dpi`.
- **edge** — `edge-corner`: the code placed against the edge of the canvas.
- **multi** — `multi-3`: three codes in one image, one of them rotated 90 degrees.
- **tolerance** — `miniature-600`: Laetus miniature dimensions at 600 DPI;
  `tolerance-max-gap`: bars and gap at the far edge of the Laetus tolerance
  range (narrow 0.7 mm, wide 2.5 mm, gap 2.5 mm).

Separately, 200 negative images (five kinds, cycled: a linear (non-Pharmacode)
barcode, rows of text, a table, random stripes, and a blank page) are decoded
and checked for any detection at all, to measure the false-positive rate.

## Metrics

- **detected** — the fraction of a condition's images where at least one
  candidate was found, whether or not its value was read correctly.
- **correct** — the fraction where the target value (or its mirror) appears
  among the detections' `value`/`mirror_value`. Always `<= detected`.
- **mean ms** — mean wall-clock time of `decode_image` per image.
- **negatives / false positives** — of the 200 negative images, how many
  produced any detection at all; a Pharmacode reader should produce none.

A failing image (target value not found) is saved, annotated, under
`failures/<condition>/<value>.png`; a false positive is saved under
`failures/negatives/<kind>-<index>.png`.

## CI gate

After writing the report, `pharmacode benchmark` checks it against
`--min-correct` (default 1.0) and `--max-false-positives` (default 0): any
condition whose correct rate falls below `--min-correct`, or a negatives
count above `--max-false-positives`, is printed to stderr as a `gate:`
line and the command exits 7 (`EXIT_BENCHMARK_FAILED`). CI (see
[test.yml](../.github/workflows/test.yml)) runs `pharmacode benchmark --quick`
with no gate flags, so it relies on these strict defaults: a single
regression anywhere in the matrix or a single false positive among the
negatives turns the CI job red.

## Result

Pasted verbatim from `benchmark-output/results.md` (produced by
`pharmacode benchmark --seed 20260919`, full matrix, not `--quick`):

```markdown
# Benchmark (seed 20260919, full)

Python 3.13.5, numpy 2.5.3, OpenCV 5.0.0, Windows-10-10.0.19045-SP0

| condition | group | images | detected | correct | mean ms |
|---|---|---|---|---|---|
| clean-300 | clean | 55 | 100.0% | 100.0% | 5.7 |
| rotation-90 | rotation | 55 | 100.0% | 100.0% | 5.8 |
| rotation-180 | rotation | 55 | 100.0% | 100.0% | 5.0 |
| rotation-270 | rotation | 55 | 100.0% | 100.0% | 5.2 |
| tilt-plus-3 | rotation | 55 | 100.0% | 100.0% | 5.6 |
| tilt-minus-3 | rotation | 55 | 100.0% | 100.0% | 5.4 |
| dpi-150 | dpi | 55 | 100.0% | 100.0% | 1.9 |
| dpi-600 | dpi | 55 | 100.0% | 100.0% | 21.2 |
| blur-1 | blur | 55 | 100.0% | 100.0% | 4.7 |
| blur-2 | blur | 55 | 100.0% | 100.0% | 4.7 |
| noise-10 | noise | 55 | 100.0% | 100.0% | 4.8 |
| noise-25 | noise | 55 | 100.0% | 100.0% | 4.7 |
| jpeg-50 | jpeg | 55 | 100.0% | 100.0% | 5.0 |
| jpeg-30 | jpeg | 55 | 100.0% | 100.0% | 4.9 |
| contrast-0.4 | contrast | 55 | 100.0% | 100.0% | 4.9 |
| illumination-0.5 | illumination | 55 | 100.0% | 100.0% | 4.7 |
| perspective-3 | perspective | 55 | 100.0% | 100.0% | 5.0 |
| scale-0.7x1.3 | scale | 55 | 100.0% | 100.0% | 4.0 |
| edge-corner | edge | 55 | 100.0% | 100.0% | 7.3 |
| multi-3 | multi | 55 | 100.0% | 100.0% | 51.1 |
| miniature-600 | tolerance | 55 | 100.0% | 100.0% | 14.7 |
| tolerance-max-gap | tolerance | 55 | 100.0% | 100.0% | 7.3 |
| dpi-150-blur-1 | blur | 55 | 100.0% | 100.0% | 1.8 |

Negatives: 200 images, 0 false positives (0.0%).
```

## Known weak conditions

None. Every one of the 23 conditions above detected and correctly decoded all
55 images (100.0% / 100.0%), and none of the 200 negative images produced a
false positive; `benchmark-output/failures/` is empty for this run. There is
nothing to single out as weak here.

This is not evidence that the toolkit is reliable on real scans: every image
in this matrix is synthetic, generated by `pharmacode.rendering` from the same
model the decoder itself reasons about. A clean 100% result here says the
implementation is internally consistent with its own generator and the
distortions it was told to expect, not that it will perform this way on
printed, scanned or photographed packaging, which can fail in ways this
matrix does not model (ink spread, substrate texture, uneven real lighting,
sensor artefacts, folds and creases, print misregistration). See
[limitations.md](limitations.md) for what is and is not covered.
