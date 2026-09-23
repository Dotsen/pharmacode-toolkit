# Command line

```
pharmacode [--version] {generate,decode,batch,benchmark} ...
```

`--version` prints the package version and exits.

## `pharmacode generate`

Render a synthetic Pharmacode image.

| option | default | meaning |
|---|---|---|
| `--value INT` (required) | - | integer 3..131070 to encode |
| `--output PATH` (required) | - | output PNG, JPEG or TIFF path, or an `.svg` path for a vector (see below) |
| `--dpi FLOAT` | 300.0 | render resolution; must be positive |
| `--miniature` | off | use the Laetus miniature dimensions instead of standard |
| `--rotation FLOAT` | 0.0 | rotation in degrees, counter-clockwise |
| `--scale-x FLOAT` | 1.0 | horizontal scale factor; must be > 0 |
| `--scale-y FLOAT` | 1.0 | vertical scale factor; must be > 0 |
| `--perspective FLOAT` | 0.0 | perspective tilt in degrees; abs() must be < 45 |
| `--blur FLOAT` | 0.0 | Gaussian blur sigma, in pixels; must be >= 0 |
| `--noise FLOAT` | 0.0 | Gaussian noise sigma; must be >= 0 |
| `--contrast FLOAT` | 1.0 | contrast factor; 1.0 is full contrast; must be >= 0 |
| `--illumination FLOAT` | 0.0 | illumination-gradient brightness loss; must be 0..1 |
| `--jpeg INT` | none | round-trip the image through JPEG at this quality; must be 1..100 |
| `--seed INT` | 0 | seed for every random distortion above |

On success it writes the image and prints a one-line JSON summary
(`value`, `bars`, `output`, `width`, `height`, `dpi`) to stdout. The
resolution is stored in the file (PNG `pHYs`, JPEG JFIF density, TIFF
resolution tags; `--dpi` times `--scale-x` and `--scale-y`), so
`decode --dpi auto` reads it back.

With an `.svg` output, `generate` writes the code as a vector in exact
millimetres instead: the document's `width` and `height` are in mm and one
user unit is 1 mm, so it prints at its physical size, with the same layout
as the raster (quiet zone and a 2 mm margin on every side) and no pixel
rounding. `--dpi` does not apply; the raster distortions (`--rotation`,
`--scale-x`, `--scale-y`, `--perspective`, `--blur`, `--noise`,
`--contrast`, `--illumination`, `--jpeg`) are a usage error with SVG. The
summary line then holds `value`, `bars`, `output`, `width_mm` and
`height_mm`. In Python: `pharmacode.render_svg(bars, spec, title)`.

## `pharmacode decode`

Find and decode every Pharmacode in an image.

| option | default | meaning |
|---|---|---|
| `input` (positional, required) | - | PNG, JPEG or TIFF file to read |
| `--dpi FLOAT\|auto` | none | resolution in DPI; enables the physical checks (see [algorithm.md](algorithm.md)). `auto` reads it from the file (see [below](#dpi-from-the-file)) and decodes without DPI, with a `note:` on stderr, when the file has no usable value |
| `--json PATH` | none | write the JSON result here instead of stdout |
| `--annotated PATH` | none | also write an annotated copy of the image here |
| `--debug-dir DIR` | none | also write every intermediate image and measurement here, created if missing (see [Debug output](#debug-output)) |
| `--min-bars INT` | 2 | reject candidates with fewer bars than this (2..16) |
| `--max-bars INT` | 16 | reject candidates with more bars than this (2..16) |
| `--allow-cropped-quiet-zone` | off | turn a quiet zone cut by the image edge into a `quiet_zone_truncated_by_image_edge` warning instead of `QUIET_ZONE_VIOLATION` (`DecoderConfig.allow_truncated_quiet_zone`); a violation on a side that is not touching the image border is still an error |
| `--polarity {dark,light,auto}` | `dark` | `dark`: dark bars on a light background; `light`: light bars on a dark background; `auto`: the dark pass, then the light pass only if the dark one decoded nothing (`DecoderConfig.polarity`, see [algorithm.md](algorithm.md#3-pipeline)) |
| `--min-confidence FLOAT` | 0.0 | reject a decoded candidate whose confidence falls below this as a `LOW_CONFIDENCE` error instead of a detection (`DecoderConfig.min_confidence`); must be 0.0..1.0 |

| `--expect INT` | none | verification: exit 0 if a detection reads this value in either direction (`value` or `mirror_value`), exit 8 otherwise, whatever else the image holds; adds an [`expected`](#verification-with---expect) block to the JSON; must be 3..131070 |
| `--report-geometry` | off | add a [`geometry`](#geometry-report) block to every detection: measured sizes in px and, with a DPI, in mm against the Laetus tolerances |

`--min-bars` and `--max-bars` must satisfy `2 <= min-bars <= max-bars <= 16`.
`--min-confidence` must be between 0.0 and 1.0.

### DPI from the file

`--dpi auto` (`decode_file(..., auto_dpi=True)` in Python,
`pharmacode.metadata.read_resolution` on its own) reads, in this order:

- PNG: the `pHYs` chunk, when its unit is the metre;
- JPEG: the JFIF density, when its unit is the inch or the centimetre, else
  the EXIF `XResolution`/`YResolution`/`ResolutionUnit` tags;
- TIFF: the same three tags of the first image.

The value is ignored — and `note:` on stderr says why — when:

- the file carries camera exposure data (EXIF `ExposureTime`, `FNumber` or
  `FocalLength`): a camera writes a fixed 72, 180, 300 or 350 DPI that says
  nothing about how large the photographed package appears;
- it is below 100 DPI: there a nominal 0.5 mm narrow bar is under 2 px,
  which the decoder does not support, so the value is a software default
  (72 or 96 DPI) rather than a scan resolution;
- the horizontal and vertical resolutions differ by more than 1%.

So `auto` suits scans and generated images. For a photo, measure the
resolution instead (for example, photograph a ruler at the same distance)
and pass it as a number, or decode without `--dpi`.

### Debug output

`--debug-dir DIR` (`DebugRecorder` in Python, passed as
`decode_image(..., debug=recorder)`) writes, for every pass the decoder ran
(`dark`, `light`, or both with `--polarity auto`):

| file | content |
|---|---|
| `<polarity>-1-input.png` | the grayscale image the pass works on (inverted for `light`) |
| `<polarity>-2-flattened.png` | after background flattening |
| `<polarity>-3-mask.png` | the ink mask candidates are searched in, ink black |
| `<polarity>-4-candidates.png` | bar-shaped components (blue) and candidate boxes, numbered: green decoded, red rejected with its error code |
| `<polarity>-candidate-<n>.png` | candidate `n` straightened: the region, its ink mask, and its ink profile with the bar threshold (red) and the bar runs found (green) |
| `debug.json` | per pass: the background kernel floor; per candidate: box, orientation, number of bar components, outcome (bars and confidence, or error code and message), and when segmented, bar widths, gaps, quiet zones, bar height, confidence margins and warnings |

Use it to see why a code failed: whether it was found at all (`4-candidates`),
and which measurement rejected it (`candidate-<n>` and `debug.json`).

## `pharmacode batch`

Decode many images with the same options as `decode`, writing one JSON
result per line (JSON Lines).

```
pharmacode batch scans/ --recursive --dpi auto --jsonl results.jsonl --csv summary.csv --jobs 4
```

| option | default | meaning |
|---|---|---|
| `inputs` (positional, one or more) | - | image files, directories (their `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff` files, sorted), or glob patterns such as `'scans/*.png'` (expanded by `batch` itself for shells that do not) |
| `--recursive` | off | also search subdirectories of a directory |
| `--jsonl PATH` | stdout | write the JSON Lines here |
| `--csv PATH` | none | also write a one-row-per-image summary here |
| `--annotated-dir DIR` | none | write an annotated copy of each image here, as `<nnnn>-<name>.png`, created if missing |
| `--debug-dir DIR` | none | write each image's [debug output](#debug-output) into `DIR/<nnnn>-<name>/`, created if missing |
| `--jobs INT` | 1 | decode this many images in parallel processes; must be >= 1 |

plus every decoder option of `decode`: `--dpi` (a number or `auto`, read
per file), `--min-bars`, `--max-bars`, `--allow-cropped-quiet-zone`,
`--polarity`, `--min-confidence`, `--expect`, `--report-geometry`.

`<nnnn>` is the image's position in the input list (from `0000`), so two
inputs with the same name in different directories never overwrite each
other. Records are written in input order, whatever `--jobs` is, and each
as soon as it and every record before it are done.

Each line is the `decode` JSON result for one image (on one line), plus:

- `exit_code` — what `decode` with the same options would have exited
  with for this image (0, 3, 4, 5, 6 or 8);
- `annotated`, `debug` — paths written for this image, when asked for.

An image that cannot be read still gets a line: `image.width`,
`image.height` and `image.dpi` are `null`, `detections` is empty, `errors`
holds one `INPUT_UNREADABLE`, and `exit_code` is 3. The batch goes on.

The CSV has the columns `path`, `exit_code`, `dpi`, `dpi_source`,
`detections` (count), `values`, `mirror_values`, `confidences`, `errors`
(error codes) and `expected_matched` (`true`/`false`, empty without
`--expect`); several values in one cell are joined with `;`.

`note:` lines on stderr carry what `decode` would print, prefixed with the
image path, and a last line counts the images and how many decoded
cleanly. `batch` exits 0 when every image's `exit_code` is 0, and 9
otherwise.

## `pharmacode benchmark`

Run the synthetic benchmark matrix described in [benchmark.md](benchmark.md).

| option | default | meaning |
|---|---|---|
| `--seed INT` | 20260919 | seed for every rendered image |
| `--output PATH` | `benchmark-output` | directory for `results.md`, `results.json` and `failures/` |
| `--quick` | off | small subset of conditions and values, for CI |
| `--min-correct FLOAT` | 1.0 | fail unless every condition reaches this correct rate; must be 0.0..1.0 |
| `--max-false-positives INT` | 0 | fail if more than this many negative images produce a detection; must be >= 0 |

Prints the resulting Markdown report to stdout as well as writing it, then
checks the report against `--min-correct` and `--max-false-positives` (see
[benchmark.md](benchmark.md#ci-gate)).

## JSON contract

`decode` always structures its result the same way, whether written to
`--json` or printed to stdout. This is the actual output for
`examples/generated/value_1234.png` (`examples/expected/value_1234.json`):

```json
{
  "version": "0.2.1",
  "image": {
    "path": "value_1234.png",
    "width": 208,
    "height": 141,
    "dpi": 150.0,
    "dpi_source": "given"
  },
  "detections": [
    {
      "bbox": { "x": 5, "y": 23, "width": 197, "height": 94 },
      "orientation_deg": 0.0,
      "polarity": "dark",
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

`image.dpi_source` says where `image.dpi` came from: `"given"` (`--dpi`
with a number), `"png-phys"`, `"jpeg-jfif"`, `"exif"` or `"tiff"` (read
by `--dpi auto`), or `null` when decoding ran without DPI.

`errors` is a list of `{"code", "message", "bbox"}` objects (`bbox` is `null`
for `NO_CANDIDATES`, which has no candidate to attach to); see
[algorithm.md](algorithm.md#5-detection-errors-versus-decoding-errors) for
what each `code` means and when it appears instead of, or alongside, a
detection.

A detection's `polarity` is `"dark"` (dark bars on a light background) or
`"light"` (light bars on a dark background), whichever pass of
`--polarity` read it.

A detection's `warnings` list holds zero or more of these strings:

| warning | appears when |
|---|---|
| `single_width_class` | every bar in the code measured the same width, so there is no wide/narrow ratio to split on; the single class is assigned by comparing it to a physical or gap-derived boundary instead (`classify_widths` in `segmentation.py`) |
| `single_width_class_no_dpi` | `single_width_class` above, and additionally no `--dpi` was given, so the boundary is the code's own median gap rather than a physical measurement in mm; confidence is capped at `single_class_no_dpi_confidence_cap` (0.5) |
| `width_ratio_below_nominal` | two width classes were found and are each internally tight, but the wide/narrow ratio between their means is below 2.0 (nominal is 3.0), i.e. the split is real but narrower than the Laetus nominal ratio |
| `quiet_zone_below_nominal` | the smaller of the leading/trailing quiet zone is at or above the hard minimum (so decoding still succeeds) but below the nominal quiet zone (6 mm with `--dpi`, else 4x the estimated wide bar width) |
| `quiet_zone_truncated_by_image_edge` | `--allow-cropped-quiet-zone` was given, the smaller quiet zone is below the hard minimum, and that side of the candidate touches the image border — the violation is downgraded to this warning instead of `QUIET_ZONE_VIOLATION` (`segmentation.validate_quiet_zone`) |

### Verification with `--expect`

With `--expect 1234` the JSON result gains:

```json
"expected": {"value": 1234, "matched": true, "matches": [{"detection": 0, "reading": "value"}]}
```

`matches` lists every detection that reads the value, by its index in
`detections`, and whether its `value` or its `mirror_value` did; the format
has no reading direction, so either counts. The exit code is then only the
answer to "is it there": 0 if `matches` is not empty, 8 otherwise, even when
other candidates in the image failed. A detection rejected by
`--min-confidence` is an error, not a detection, so it never matches:
combine the two for a stricter check. In Python: `DecodeResult.matches(value)`.

### Geometry report

`--report-geometry` (`DecodeResult.to_dict(include_geometry=True)` in
Python) adds to every detection:

```json
"geometry": {
  "bar_widths_px": [6, 6, 18], "gap_widths_px": [12, 12],
  "bar_height_px": 94, "quiet_zone_px": [84, 83],
  "pixel_mm": 0.085,
  "bar_widths_mm": [0.508, 0.508, 1.524], "gap_widths_mm": [1.016, 1.016],
  "bar_height_mm": 7.959, "quiet_zone_mm": [7.112, 7.027],
  "variant": "standard",
  "out_of_tolerance": [
    {"element": "wide_bar", "index": 2, "mm": 2.794, "range_mm": [1.3, 2.5]}
  ]
}
```

The `_mm` fields, `pixel_mm`, `variant` and `out_of_tolerance` are `null`
without a DPI. `variant` is the Laetus variant (`standard` or `miniature`,
see [algorithm.md](algorithm.md#2-physical-dimensions)) whose ranges the
most bars and gaps satisfy. `out_of_tolerance` lists every bar
(`narrow_bar`, `wide_bar`) and `gap` outside that variant's range, by its
index in reading order, and every `quiet_zone` (index 0 leading, 1
trailing) below 6 mm, whose `range_mm` has no upper bound (`null`).

It is a diagnostic, not a print-quality grade. Widths are the ones the
decoder measured on its thresholded ink profile, so blur, ink spread and
lighting move them, and they move in whole pixels: `pixel_mm` is the
step, so a bar within a pixel of a limit can land on either side. The
quiet zone is measured only as far as the candidate window reaches (7 to
11 mm with DPI), so a wider quiet zone reads as the window's extent.

## Exit codes

| code | name | meaning |
|---|---|---|
| 0 | `EXIT_OK` | every candidate in the image decoded successfully (at least one detection, no errors) |
| 2 | `EXIT_USAGE` | a command-line argument was invalid (bad `--value`, non-positive `--dpi` or one that is neither a number nor `auto`, an out-of-range `generate` distortion parameter, `--min-bars`/`--max-bars` out of order, an out-of-range `--min-confidence` or `--expect`, an unknown `--polarity`, `--jobs` below 1, or an out-of-range `--min-correct`/`--max-false-positives`) — nothing was decoded and no JSON is produced |
| 3 | `EXIT_INPUT` | `batch` found no input image at all, or could not create its output directories or write its `--jsonl`/`--csv` file; an image file could not be read (`decode`'s input) or written (`generate --output`, or `decode --annotated`), the output path has an unrecognised suffix (`save_image` only knows the formats OpenCV can encode; an unknown suffix such as `.txt` fails the same way as a missing output directory), or `decode --json` could not be written to its path (e.g. the parent directory is missing); when the input cannot be read, no JSON is produced; when `decode --annotated` fails to write, the JSON has already been written or printed; when `decode --json` fails to write, no JSON reaches either destination (stdout is only used when `--json` is absent); `generate` has no JSON result to produce either way |
| 4 | `EXIT_NO_CANDIDATES` | decoding ran but found no group of aligned bars at all (`NO_CANDIDATES`) |
| 5 | `EXIT_VALIDATION_FAILED` | one or more candidates were found but every one of them failed segmentation or validation, or was rejected as `LOW_CONFIDENCE` |
| 6 | `EXIT_PARTIAL` | a mix: at least one candidate decoded successfully and at least one other failed |
| 7 | `EXIT_BENCHMARK_FAILED` | benchmark gate failed: a condition fell below `--min-correct` or negatives exceeded `--max-false-positives` |
| 8 | `EXIT_EXPECTATION_FAILED` | `decode --expect`: no detection reads the expected value (replaces 0, 4, 5 and 6 whenever `--expect` is given; with a match the exit code is 0) |
| 9 | `EXIT_BATCH_FAILURES` | `batch`: at least one image's `exit_code` is not 0 (see its line in the JSON Lines) |

For `decode`, the JSON result is written (to `--json` or stdout) for every
exit code that follows from actually running the decoder — 0, 4, 5, 6 and 8,
and the `--annotated`-write failure case of 3 — because it is produced right after
`decode_image` returns, before the exit code itself is computed. The two
cases with no JSON at all are a usage error (2) and an unreadable input file
(3): both are caught before `decode_image` is called, so there is no result
to report.

`generate` and `benchmark` do not produce this JSON result; `generate` prints
its own one-line summary on success (see above) and exits 0, 2 or 3.
`benchmark` writes its report and then exits 0 or 7, depending on the gate
(see [benchmark.md](benchmark.md#ci-gate)); a bad `--min-correct` or
`--max-false-positives` is rejected before the benchmark runs, exiting 2.
