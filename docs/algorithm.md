# Algorithm and threshold provenance

## 1. Format

One-track Pharmacode encodes an integer from 3 to 131070 as a sequence of 2 to
16 bars. Each bar is one of two width classes, **narrow** (weight 1) or
**wide** (weight 2). Reading the bars from the most significant one, the value
is built incrementally as `value = value * 2 + weight` for every bar in turn.
`pharmacode.encoding.encode` constructs a sequence for a given value by running
this in reverse: it repeatedly takes the value modulo 2 to choose the next
(least significant) bar and integer-divides it down (`(v - 1) // 2` after a
narrow bar, `(v - 2) // 2` after a wide one), then reverses the result so the
most significant bar comes first. `pharmacode.decoding.bars_to_value` computes
the same formula directly in one pass over a bar sequence (Wikipedia,
"Pharmacode": value range, weights, decoding formula).

Because the format has no start or stop pattern, a sequence of bars can be
read in either direction and both readings are valid integers in range; only
external context (packaging layout, a check elsewhere on the label) says which
one was intended. The toolkit therefore always reports both: `value` reads the
bars in the order they were measured — left to right for a horizontal code,
top to bottom for a vertical one — and `mirror_value` reads the same bars in
reverse. The Laetus guide's own convention (section 4.6.1) is to place the
highest-value bar at the left (or top) of the printed code, and its inverse
reading is used when a code is scanned in the other direction (section 4.6.3).
Its worked example on p.36 prints the bars for 25 (`WNWN`) and notes that
reading them back to front gives 20 (`NWNW`) — the same value/mirror pair
produced by this toolkit for that bar sequence. Rotation compounds this
(section 4.6.2): `orientation_deg` lies in `(-90, 90]`, with 0 meaning the
primary reading runs left to right and 90 meaning it runs top to bottom. A
code rotated a quarter turn counter-clockwise from upright reports
`orientation_deg = 90`, and the bar that was leftmost (highest place value)
before the turn is now at the bottom of the vertical code — so the code's
nominal value comes out in `mirror_value`, not `value` (see the `12345`
example below, rotated: `value` 11136, `mirror_value` 12345).

Test vectors (`N` = narrow, `W` = wide bar, most significant bar first),
cross-checked against zint (`backend/medical.c`, BSD-3-Clause), BWIPP
(`src/pharmacode.ps.src`, MIT) and JsBarcode (MIT), and the worked example for
91 at <https://www.computalabel.com/aboutpharmacodes.htm>:

| value | bars | mirror value |
|---|---|---|
| 3 | NN | 3 |
| 4 | NW | 5 |
| 5 | WN | 4 |
| 6 | WW | 6 |
| 7 | NNN | 7 |
| 8 | NNW | 11 |
| 9 | NWN | 9 |
| 10 | NWW | 13 |
| 13 | WWN | 10 |
| 25 | WNWN | 20 (Laetus guide, p.36 example) |
| 91 | NWWWNN | 77 |
| 100 | WNNWNW | 104 |
| 1234 | NNWWNWNNWW | 1835 |
| 12345 | WNNNNNNWWWNWN | 11136 |
| 65535 | NNNNNNNNNNNNNNNN | 65535 |
| 123456 | WWWNNNWNNWNNNNNW | 98886 |
| 131070 | WWWWWWWWWWWWWWWW | 131070 |

## 2. Physical dimensions

The renderer and the DPI-aware checks use the nominal dimensions and tolerance
ranges from the Laetus PHARMA-CODE Guide, sections 1.2 and 1.3:

| variant | narrow bar | wide bar | gap | bar height | quiet zone |
|---|---|---|---|---|---|
| standard | 0.5 mm (0.4-0.7) | 1.5 mm (1.3-2.5) | 1.0 mm (0.9-2.5) | 8 mm | >= 6 mm (7 mm for laser readers) |
| miniature | 0.35 mm (0.3-0.45) | 1.0 mm (0.9-1.7) | 0.65 mm (0.55-1.65) | 6 mm | >= 6 mm (7 mm for laser readers) |

The quiet-zone minimum is section 2.2.1; `pharmacode generate --miniature`
selects the miniature column, the default is standard.

## 3. Pipeline

`decode_image` runs the same stages on every image. They assume dark bars
on a light background; `DecoderConfig.polarity` (`decode --polarity`) says
which way round the code is printed:

- `"dark"` (default) — dark bars on light, the stages below run once;
- `"light"` — light bars on dark: the stages run once on the inverted image
  (`255 - gray`);
- `"auto"` — the stages run on the image as it is and, only when that pass
  decodes nothing, once more on the inverted image. A printed code therefore
  costs one pass and gets exactly the `"dark"` result. When neither pass
  decodes anything, the dark pass's errors are reported, unless the dark
  pass found no candidate at all and the light pass did.

Each detection's `polarity` says which pass read it (`"dark"` or `"light"`);
bounding boxes refer to the original image either way.

1. **load** — `pharmacode.io.load_image` reads a PNG, JPEG or TIFF file into
   an 8-bit grayscale array (the CLI's `decode` command does this before
   calling the library; callers passing an array directly skip it).
2. **flatten background** — `imageops.flatten_background` divides the image
   by a morphological-closing estimate of the paper, removing illumination
   gradients and uneven lighting so ink reads as near-black everywhere. The
   closing kernel must be larger than every bar in the image or it fails to
   erase them from the paper estimate, so `pipeline.decode_image` sizes it
   from the image itself before flattening: `detection.estimate_stroke_px`
   measures the thickest bar-like stroke of the raw (unflattened) ink mask,
   and the kernel is set to `background_kernel_stroke_factor` (3x) that
   stroke, on top of the existing image-fraction (`background_kernel_fraction`)
   and DPI-based (`background_kernel_min_mm`) floors. Without this, a code
   whose bars are wide relative to the image (filling the frame, as in a
   tightly cropped photo) can have its bars only partly erased, leaving
   their edges as spurious ink once the image is normalised — read as a
   plausible but wrong sequence of thin bars instead of the real ones. When
   a thin rule crosses every bar, the raw mask holds no isolated bar-shaped
   component to measure either; `detection.estimate_stroke_px_past_crossing_lines`
   retries the same measurement on the mask opened lengthwise (step 5's
   crossing-line fallback), so the kernel is still sized from the true bar
   width on such an image.
3. **binarise** — `imageops.otsu_mask`, applied to the flattened image inside
   `find_candidates`, produces a 0/255 ink mask with Otsu's threshold; images
   with too little ink/paper contrast (`min_contrast`) are rejected here with
   no candidates at all.
4. **bar components** — `detection.find_bar_components` fits an oriented
   rectangle to every connected ink component and keeps only the ones shaped
   like a solid bar: long enough (`min_bar_length_px`), thin relative to their
   length (`min_bar_aspect`), and solidly filled (`min_fill_ratio`) rather
   than text, glyphs or noise.
5. **group** — `detection.group_bars` chains parallel, co-axial, similarly
   long bars into ordered runs, splitting wherever the spacing between
   consecutive bars jumps past a legal gap (`max_angle_diff_deg`,
   `max_length_ratio`, `max_axis_offset_ratio`, `max_spacing_factor`,
   `max_spacing_length_ratio`); each surviving chain of two or more bars
   becomes a `DetectionCandidate` with a bounding box and an orientation. If
   this plain pass finds no candidate at all, `find_candidates` tries once
   more: a rule crossing every bar of a code joins them into one connected
   component that fails the bar-component filters above (too little of its
   bounding box is ink), so two more passes open the ink mask lengthwise —
   with a tall, one-pixel-wide element and a wide, one-pixel-tall element
   (`crossing_line_max_px`) — which erases a rule up to that thick wherever
   it is not already covering a bar, splitting the bars back apart while
   leaving a thicker rule (or unrelated dense ink, such as a table grid or
   text) untouched. This fallback only searches components that already look
   bar-shaped but suspiciously under-filled, and only recovers chains of
   `fallback_min_bars` (3) or more bars, so it cannot turn ordinary clutter
   into a false code.

For each candidate:

6. **straighten** — `segmentation.normalize_roi` crops the candidate's box out
   of the flattened image and rotates it (`imageops.rotate_bound`) so the code
   axis runs left to right, producing an upright grayscale region of interest.
7. **profile** — `segmentation.bar_profile` re-binarises that region and
   measures, column by column, the fraction of ink over the central band of
   the inked rows (`profile_band_fraction`), avoiding rounded corners and
   edge noise at the very top and bottom of the bars; both this band and,
   later, each bar's own height (`segmentation.measure_heights`) are taken
   from the contiguous block of ink around the region's centre row, so a
   caption sharing the candidate box but separated from the bars by a blank
   row is not measured as part of them.
8. **runs** — `segmentation.runs_from_profile` and `measure_runs` threshold
   the profile (`profile_threshold`) and run-length encode it into bar
   `(start, width)` pairs, inner gap widths, and the leading/trailing quiet
   zones; `check_bar_count` rejects a count outside `[min_bars, max_bars]`
   here (`TOO_FEW_BARS`, `TOO_MANY_BARS`). Before measuring,
   `segmentation.drop_background_edges` removes an ink run at either end
   that is the edge of a dark area around the code rather than a bar: a
   code on a light patch inside a dark area (a white knockout on a dark
   carton, or an inverted code's patch once inverted) puts the patch edge
   inside the candidate window whenever the patch margin is narrower than
   the window (7 to 11 mm with DPI). Such a run covers nearly the whole
   window height (`background_edge_height_fraction`) and stands taller than
   the code's other bars by more than `max_height_deviation`; dropping it
   ends the quiet zone at the patch edge, where it is then checked like any
   other. Bars of a tightly cropped code also fill the window, but all to
   the same height, so they are never dropped.
9. **classify** — `segmentation.classify_widths` assigns narrow or wide to
   every bar, splitting the sorted widths at their largest ratio jump and
   testing each bar against the resulting class medians (see below);
   `validate_shape` checks bar-height and gap-width consistency on the raw
   runs just before this, and `validate_quiet_zone` checks the quiet zones
   just after, once the wide bars are known. By default a quiet zone below
   the hard limit is always `QUIET_ZONE_VIOLATION`; if the caller opted in
   with `allow_truncated_quiet_zone` (`--allow-cropped-quiet-zone`) and the
   short side is one where the candidate's box touches the image border
   (`segmentation.extract_bars` derives this from the candidate's bbox and
   orientation), the violation becomes a `quiet_zone_truncated_by_image_edge`
   warning instead — a short quiet zone caused by ink still inside the
   image, on a side that is not touching the border, is always an error.
10. **validate** — the three checks above (`validate_shape` twice, for height
    and gaps, and `validate_quiet_zone`) each either pass and record a
    confidence margin, or fail with `INCONSISTENT_BAR_HEIGHT`,
    `INCONSISTENT_GAPS`, `WIDTH_CLASSES_NOT_SEPARABLE`, `AMBIGUOUS_WIDTH` or
    `QUIET_ZONE_VIOLATION`.
11. **decode** — `decoding.decode_bars` turns the classified sequence into
    `value` and `mirror_value` with `bars_to_value`, once forwards and once
    reversed; no heuristic prefers one over the other.
12. **confidence** — `decode_image` takes the minimum of every margin
    recorded in steps 9-10 as the detection's overall confidence (see
    section 6).

**Width classification in detail.** The bar widths are sorted and split at
their largest ratio jump (`width_split_ratio`); if no jump reaches that ratio,
every bar is treated as one class instead. When there is a split, the narrow
and wide clusters' medians each define a tolerance band — a bar is "near" a
class if it is within `max_intra_class_ratio` (1.35x) or `width_pixel_tolerance_px`
(2 px) of that class's median. A bar inside neither band is `AMBIGUOUS_WIDTH`.
A bar inside both bands (possible only at very low DPI, where the two classes'
tolerance bands overlap) takes whichever class it is proportionally nearer to.
After every bar is assigned, each class's own widths must still be tight
(same ratio/pixel test, against each other rather than the median) or the
whole candidate fails as `WIDTH_CLASSES_NOT_SEPARABLE`. A legal single-width-class
code (only ever produced by values with all-narrow or all-wide bars, e.g. 3, 7,
65535, 131070) has no split to classify against, so it falls back to a
physical test: when the DPI is known, its median width in millimetres is
compared to `physical_width_boundary_mm` (0.8 mm, warning `single_width_class`);
without DPI, it is compared instead to the code's own median gap width
(`gap_ruler_boundary`, warnings `single_width_class` and
`single_width_class_no_dpi`), and its confidence margin is capped at
`single_class_no_dpi_confidence_cap` (0.5) because a gap-based ruler has no
absolute scale to check against.

## 4. Threshold provenance

Every field of `DecoderConfig` (`src/pharmacode/models.py`), its default and
where the number comes from:

| field | default | origin |
|---|---|---|
| `dpi` | `None` | optional resolution in dots per inch; when set, enables the physical (mm) checks below instead of the nominal-ratio fallbacks |
| `min_bars` | 2 | format minimum bar count |
| `max_bars` | 16 | format maximum bar count |
| `polarity` | `"dark"` | `"dark"`, `"light"` or `"auto"`; see section 3 |
| `background_kernel_fraction` | 0.05 | closing kernel = 5% of the image's longer side |
| `background_kernel_min_mm` | 3.2 mm | absolute floor for the closing kernel, applied when DPI is known: the kernel must exceed the widest legal bar (wide tolerance up to 2.5 mm) so it fully erases every bar from the background estimate; a code's height is a fixed ~24 mm (8 mm bars plus two 8 mm margins), so for a short, few-bar code 5% of the image's longer side (its height) can be narrower than even a nominal 1.5 mm wide bar — 3.2 mm clears the 2.5 mm tolerance limit with margin while staying below the span of a run of several same-class bars |
| `background_kernel_stroke_factor` | 3.0 | the closing kernel must exceed the widest bar; the kernel floor is set to 3x the thickest bar-like stroke measured on the raw (unflattened) mask by `detection.estimate_stroke_px`, so a code whose bars are wide relative to the image (filling the frame) still gets a kernel bigger than them, regardless of DPI or the image-fraction floor |
| `max_stroke_fraction` | 0.25 | strokes thicker than a quarter of the image's longer side are blobs, not bars, and are ignored by `estimate_stroke_px` |
| `min_bar_length_px` | 8 px | discards specks; an 8 mm bar is already >= 47 px at 150 DPI |
| `min_bar_aspect` | 2.5 | height 8 mm / wide bar 2.5 mm = 3.2 at tolerance limits; non-uniform scaling (1.3 x 0.7) can lower a wide bar's aspect to 2.75, and Laetus allows 5 mm bars on labels (aspect 2) |
| `min_fill_ratio` | 0.6 | bars are solid rectangles (fill 1.0); two real narrow bars from `encode(12345)` under harsh degradation (blur 1.5, noise sigma 20, contrast 0.6, JPEG 40) measured fill 0.657 and 0.674 — 0.6 keeps them with a small margin while an outline glyph (a 1 px border plus a diagonal) stays far below it |
| `min_contrast` | 30.0 | ink-vs-paper contrast after flattening; below this the page is effectively blank |
| `max_angle_diff_deg` | 10.0 deg | bars of one code are parallel |
| `max_length_ratio` | 1.25 | bars of one code share one height |
| `max_axis_offset_ratio` | 0.25 | bar centres lie on one axis, relative to bar length |
| `max_spacing_factor` | 3.0 | legal in-code gaps vary at most 2.8x; separate codes are placed at least 4.8x a gap apart |
| `max_spacing_length_ratio` | 1.0 | a gap between bars of one code never exceeds the bar height in practice |
| `crossing_line_max_px` | 8 px | the crossing-line fallback (see section 3, step 5) opens the mask with a `(1, 9)` and a `(9, 1)` element, removing a rule up to this thick that crosses the bars |
| `fallback_min_bars` | 3 | a chain recovered only by the crossing-line fallback's directional opening needs three bars; two strokes are what a single glyph's own outline yields, so a 2-bar recovered chain is discarded rather than risking a false code |
| `profile_band_fraction` | 0.6 | central band of the bar height used to build the ink profile |
| `profile_threshold` | 0.5 | ink-fraction threshold that turns the profile into bar/gap runs |
| `width_split_ratio` | 1.5 | nominal wide/narrow ratio is 3; below 1.5 the widths are treated as one class instead of split |
| `max_intra_class_ratio` | 1.35 | spread allowed inside one width class; the 0.4-0.7 mm narrow tolerance alone allows up to 1.75x, but printed codes measure tighter |
| `width_pixel_tolerance_px` | 2 px | a class is also considered tight if its widths differ by no more than 2 px (covers low DPI, where the ratio test is too strict) |
| `physical_width_boundary_mm` | 0.8 mm | narrow is <= 0.7 mm and wide is >= 0.9 mm in both the standard and miniature Laetus variants, so 0.8 mm sits in the gap between them |
| `gap_ruler_boundary` | 1.0 | without DPI, a single-class code's bars are classified as narrow below, or wide above, one median gap width (nominal narrow = 0.5x gap, wide = 1.5x gap) |
| `quiet_zone_hard_mm` | 3.0 mm | half the nominal 6 mm quiet zone |
| `quiet_zone_nominal_mm` | 6.0 mm | Laetus nominal quiet zone (section 2.2.1) |
| `quiet_zone_hard_wide_ratio` | 2.0 | without DPI, the hard quiet-zone limit as a multiple of the code's mean wide-bar width (6 mm / 2.5 mm max wide tolerance = 2.4) |
| `quiet_zone_nominal_wide_ratio` | 4.0 | without DPI, the nominal quiet zone as a multiple of the mean wide-bar width (6 mm / 1.5 mm nominal wide) |
| `allow_truncated_quiet_zone` | `False` | opt-in (`--allow-cropped-quiet-zone`): when a candidate touches the image border, a short quiet zone on that side becomes a `quiet_zone_truncated_by_image_edge` warning instead of `QUIET_ZONE_VIOLATION`; a short zone on a side that is not touching the border is always an error |
| `max_height_deviation` | 0.20 | bars of one code share one height, within 20% of the median |
| `background_edge_height_fraction` | 0.9 | an ink run at an end of the profile covering this much of the window height, and taller than the bars by more than `max_height_deviation`, is the edge of a dark area around the code and is dropped (section 3, step 8); the window is twice the bar length, so a bar alone covers about half of it |
| `gap_ratio_range` | (0.6, 1.5) | one code's printed gaps should be close to one width; the 1.5x upper tolerance absorbs blur and low-DPI rounding |
| `single_class_no_dpi_confidence_cap` | 0.5 | ceiling on the width-margin (and so overall) confidence for a single-width-class code classified without DPI, since a gap-based ruler has no absolute scale |
| `min_confidence` | 0.0 | detections below this confidence are reported as `LOW_CONFIDENCE` errors instead (`decode --min-confidence`); 0 keeps every decoded candidate |

## 5. Detection errors versus decoding errors

`NO_CANDIDATES` is the only error that can occur before any candidate exists:
`decode_image` reports it directly, with no bounding box, when the grouping
stage finds no chain of two or more aligned, similarly sized, co-axial bars
anywhere in the image. It is the sole *detection* outcome, and it means the
image, at these thresholds, contains nothing that resembles a Pharmacode.

Every other `ErrorCode` is a *decoding* outcome: it is produced only once a
`DetectionCandidate` (a bounding box and a chain of bars) already exists, and
it is always attached to that candidate's `bbox` so the caller (and the
`--annotated` image) can show exactly where the failed candidate was —
`TOO_FEW_BARS`, `TOO_MANY_BARS`, `INCONSISTENT_BAR_HEIGHT`,
`INCONSISTENT_GAPS`, `WIDTH_CLASSES_NOT_SEPARABLE`, `AMBIGUOUS_WIDTH` and
`QUIET_ZONE_VIOLATION`.

`LOW_CONFIDENCE` is also a decoding outcome, but a later one than the six
above: it replaces a detection that segmentation and classification already
completed successfully — `value` and `mirror_value` are known — once
`pipeline.decode_image` finds its `confidence` (section 6) below
`DecoderConfig.min_confidence` (`decode --min-confidence`, default 0.0, which
keeps every candidate). The message still carries the value and its mirror,
for diagnosis, even though neither is reported as a detection.

Two further codes, `INPUT_UNREADABLE` and `INVALID_ARGUMENT`, exist in
`ErrorCode` as part of the JSON contract's vocabulary but are never
constructed as a `DecodeError` by the pipeline itself: an unreadable input
file or an invalid command-line argument is rejected by the CLI before
`decode_image` is even called, and is reported only as an `error:` line on
stderr and a non-zero exit code (see [docs/cli.md](cli.md)) — no JSON is
produced for that image at all.

## 6. Confidence

A detection's `confidence` is the weakest of the validation margins recorded
while segmenting it — `min(sequence.metrics.values())`, or 0.0 if a candidate
somehow recorded none. Each margin is independently clipped to `[0, 1]`, so
the overall confidence is bounded by whichever check came closest to failing:

- `height_consistency` — from bar-height validation: `1 - deviation / max_height_deviation`,
  where `deviation` is the largest relative difference from the median bar height.
- `gap_consistency` — from gap-width validation (present whenever the code
  has an inner gap, i.e. always for a 2-bar-or-longer code): how far the
  worst gap ratio sits from 1.0, relative to the room allowed by
  `gap_ratio_range`.
- `width_margin` — from width classification: for a two-class code, how far
  the wide/narrow class-mean ratio sits above `max_intra_class_ratio`; for a
  single-class code, how far its measured width sits from the physical or
  gap-based boundary (capped at 0.5 without DPI, as above).
- `quiet_zone_margin` — from quiet-zone validation: the smaller of the two
  quiet zones as a fraction of the nominal 6 mm quiet zone.
