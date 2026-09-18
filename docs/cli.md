# Command line

```
pharmacode [--version] {generate,decode,benchmark} ...
```

`--version` prints the package version and exits.

## `pharmacode generate`

Render a synthetic Pharmacode image.

| option | default | meaning |
|---|---|---|
| `--value INT` (required) | - | integer 3..131070 to encode |
| `--output PATH` (required) | - | output PNG, JPEG or TIFF path |
| `--dpi FLOAT` | 300.0 | render resolution; must be positive |
| `--miniature` | off | use the Laetus miniature dimensions instead of standard |
| `--rotation FLOAT` | 0.0 | rotation in degrees, counter-clockwise |
| `--scale-x FLOAT` | 1.0 | horizontal scale factor |
| `--scale-y FLOAT` | 1.0 | vertical scale factor |
| `--perspective FLOAT` | 0.0 | perspective tilt in degrees |
| `--blur FLOAT` | 0.0 | Gaussian blur sigma, in pixels |
| `--noise FLOAT` | 0.0 | Gaussian noise sigma |
| `--contrast FLOAT` | 1.0 | contrast factor; 1.0 is full contrast |
| `--illumination FLOAT` | 0.0 | illumination-gradient brightness loss, 0..1 |
| `--jpeg INT` | none | round-trip the image through JPEG at this quality |
| `--seed INT` | 0 | seed for every random distortion above |

On success it writes the image and prints a one-line JSON summary
(`value`, `bars`, `output`, `width`, `height`, `dpi`) to stdout.

## `pharmacode decode`

Find and decode every Pharmacode in an image.

| option | default | meaning |
|---|---|---|
| `input` (positional, required) | - | PNG, JPEG or TIFF file to read |
| `--dpi FLOAT` | none | resolution in DPI; enables the physical checks (see [algorithm.md](algorithm.md)) |
| `--json PATH` | none | write the JSON result here instead of stdout |
| `--annotated PATH` | none | also write an annotated copy of the image here |
| `--min-bars INT` | 2 | reject candidates with fewer bars than this (2..16) |
| `--max-bars INT` | 16 | reject candidates with more bars than this (2..16) |

`--min-bars` and `--max-bars` must satisfy `2 <= min-bars <= max-bars <= 16`.

## `pharmacode benchmark`

Run the synthetic benchmark matrix described in [benchmark.md](benchmark.md).

| option | default | meaning |
|---|---|---|
| `--seed INT` | 20260919 | seed for every rendered image |
| `--output PATH` | `benchmark-output` | directory for `results.md`, `results.json` and `failures/` |
| `--quick` | off | small subset of conditions and values, for CI |

Prints the resulting Markdown report to stdout as well as writing it.

## JSON contract

`decode` always structures its result the same way, whether written to
`--json` or printed to stdout. This is the actual output for
`examples/generated/value_1234.png` (`examples/expected/value_1234.json`):

```json
{
  "version": "0.1.0.dev0",
  "image": {
    "path": "value_1234.png",
    "width": 208,
    "height": 141,
    "dpi": 150.0
  },
  "detections": [
    {
      "bbox": { "x": 5, "y": 23, "width": 197, "height": 94 },
      "orientation_deg": 0.0,
      "bars": ["narrow", "narrow", "wide", "wide", "narrow", "wide", "narrow", "narrow", "wide", "wide"],
      "bar_widths_px": [3, 3, 9, 9, 3, 9, 3, 3, 9, 9],
      "value": 1234,
      "mirror_value": 1835,
      "confidence": 1.0,
      "warnings": []
    }
  ],
  "errors": []
}
```

`errors` is a list of `{"code", "message", "bbox"}` objects (`bbox` is `null`
for `NO_CANDIDATES`, which has no candidate to attach to); see
[algorithm.md](algorithm.md#5-detection-errors-versus-decoding-errors) for
what each `code` means and when it appears instead of, or alongside, a
detection.

A detection's `warnings` list holds zero or more of these strings:

| warning | appears when |
|---|---|
| `single_width_class` | every bar in the code measured the same width, so there is no wide/narrow ratio to split on; the single class is assigned by comparing it to a physical or gap-derived boundary instead (`classify_widths` in `segmentation.py`) |
| `single_width_class_no_dpi` | `single_width_class` above, and additionally no `--dpi` was given, so the boundary is the code's own median gap rather than a physical measurement in mm; confidence is capped at `single_class_no_dpi_confidence_cap` (0.5) |
| `width_ratio_below_nominal` | two width classes were found and are each internally tight, but the wide/narrow ratio between their means is below 2.0 (nominal is 3.0), i.e. the split is real but narrower than the Laetus nominal ratio |
| `quiet_zone_below_nominal` | the smaller of the leading/trailing quiet zone is at or above the hard minimum (so decoding still succeeds) but below the nominal quiet zone (6 mm with `--dpi`, else 4x the estimated wide bar width) |

## Exit codes

| code | name | meaning |
|---|---|---|
| 0 | `EXIT_OK` | every candidate in the image decoded successfully (at least one detection, no errors) |
| 2 | `EXIT_USAGE` | a command-line argument was invalid (bad `--value`, non-positive `--dpi`, or `--min-bars`/`--max-bars` out of order) — nothing was decoded and no JSON is produced |
| 3 | `EXIT_INPUT` | an image file could not be read (`decode`'s input) or written (`generate --output`, or `decode --annotated`), the output path has an unrecognised suffix (`save_image` only knows the formats OpenCV can encode; an unknown suffix such as `.txt` fails the same way as a missing output directory), or `decode --json` could not be written to its path (e.g. the parent directory is missing); when the input cannot be read, no JSON is produced; when `decode --annotated` fails to write, the JSON has already been written or printed; when `decode --json` fails to write, no JSON reaches either destination (stdout is only used when `--json` is absent); `generate` has no JSON result to produce either way |
| 4 | `EXIT_NO_CANDIDATES` | decoding ran but found no group of aligned bars at all (`NO_CANDIDATES`) |
| 5 | `EXIT_VALIDATION_FAILED` | one or more candidates were found but every one of them failed segmentation or validation |
| 6 | `EXIT_PARTIAL` | a mix: at least one candidate decoded successfully and at least one other failed |

For `decode`, the JSON result is written (to `--json` or stdout) for every
exit code that follows from actually running the decoder — 0, 4, 5 and 6, and
the `--annotated`-write failure case of 3 — because it is produced right after
`decode_image` returns, before the exit code itself is computed. The two
cases with no JSON at all are a usage error (2) and an unreadable input file
(3): both are caught before `decode_image` is called, so there is no result
to report.

`generate` and `benchmark` do not produce this JSON result; `generate` prints
its own one-line summary on success (see above) and exits 0, 2 or 3.
`benchmark` always exits 0 once it finishes writing its report.
