# Limitations

- **Light bars on a dark background need `--polarity light` or `auto`.** The
  default (`dark`) looks for dark bars on a light background only, as in
  0.2; `auto` adds a second, inverted pass only when the first decodes
  nothing. A code whose bars are partly lighter and partly darker than
  their surroundings (printed across a boundary between two backgrounds)
  is read by neither pass.
- **A dark area closer than the nominal quiet zone ends the quiet zone.** When
  a code sits on a light patch inside a dark area, the patch edge is where
  its quiet zone ends: a margin of 3 to 6 mm decodes with
  `quiet_zone_below_nominal`, a margin under 3 mm is a
  `QUIET_ZONE_VIOLATION`. The edge is recognised only when it fills nearly
  the whole candidate window height; a shorter dark object at the same
  distance (a rule, a neighbouring graphic) is measured as a bar and the
  candidate is rejected.
- **Single-width-class codes without `--dpi`** (values whose bars are all
  narrow or all wide, e.g. 3, 7, 65535, 131070) cannot be classified against a
  physical boundary and fall back to the code's own nominal gap ratio instead;
  their confidence is capped at 0.5 as a result. Pass `--dpi` to avoid this.
- **Two codes closer together than a quiet zone** are grouped as one
  inconsistent candidate and rejected, rather than being separated and read
  individually.
- **Codes made only of wide bars, decoded without `--dpi`,** use an 18 mm
  search window (there is no physical measurement to size it from, so it
  falls back to a multiple of the thickest bar) and may be rejected as one
  inconsistent group when another code lies closer than that.
- **Tilts beyond ±5 degrees are outside the tested range.**
- **DPI is never read from file or image metadata.** Pass `--dpi` explicitly
  whenever you know the resolution.
- **Very small codes are not supported:** bars shorter than about 8 px, or
  narrower than about 2 px, fall below the component filters and are ignored.
- **Degradation beyond the benchmarked range is untested:** JPEG quality
  below 30, or Gaussian blur sigma above 2 at 300 DPI, are both outside what
  [the benchmark](benchmark.md) covers.
- **Perspective distortion above about 5 degrees** is untested.
- **No two-track or colour Pharmacode.** Only the one-track, single-colour
  format described in [algorithm.md](algorithm.md) is supported.
- **Real-world coverage is a small hand-checked set, not a benchmark.** Every
  image used to build and benchmark this toolkit is synthetic (see
  [provenance.md](provenance.md)). In addition, a set of real-world sample
  images (codes with captions, tightly cropped codes, a code with a rule drawn
  across the bars, a chart of symbologies) is decoded by hand before each
  release; those fixes shaped 0.2.0. The set is small and is not part of the
  repository or the test suite, so results on other material may differ.
- **A caption touching the bars with no white gap** is still measured as
  part of the bar: `measure_heights`/`bar_profile` only skip ink that is
  separated from the bars by a blank row, so touching ink is included and
  the candidate is rejected (as an inconsistent height, or as a broken
  group further upstream) rather than decoded as a wrong value.
- **A quiet zone cut by the image edge is a `QUIET_ZONE_VIOLATION` by
  default**, same as any other short quiet zone — a tightly cropped photo is
  not distinguished from a genuinely too-close neighbour unless you ask for
  that leniency explicitly. Pass `--allow-cropped-quiet-zone`
  (`DecoderConfig.allow_truncated_quiet_zone`) to turn a violation on a side
  that touches the image border into a `quiet_zone_truncated_by_image_edge`
  warning instead; a short quiet zone caused by real ink still inside the
  image is always an error, flag or not.
- **A thin rule crossing only part of a code is not handled.** The
  crossing-line fallback (`detection.find_candidates`) recovers a code whose
  bars were all merged into one component by a rule running across the
  whole group; a rule that only touches some of the bars, or several rules
  of different thickness, are outside what it was built for.
- **A two-bar code crossed by a rule is not recovered.** The crossing-line
  fallback only accepts a recovered chain of `fallback_min_bars` (3) or more
  bars: two isolated recovered strokes are exactly what a single text
  glyph's own outline produces, so they are discarded rather than risking a
  false code.
