# Limitations

- **Dark-on-light only.** The decoder assumes dark bars on a light background;
  inverted (light bars on a dark background) codes are not detected.
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
- **No validation on real print samples.** Every image used to build and
  benchmark this toolkit is synthetic (see [provenance.md](provenance.md));
  nothing here has been checked against a scanned or photographed printed
  code.
- **A caption touching the bars with no white gap** is still measured as
  part of the bar: `measure_heights`/`bar_profile` only skip ink that is
  separated from the bars by a blank row, so touching ink is included and
  the candidate is rejected (as an inconsistent height, or as a broken
  group further upstream) rather than decoded as a wrong value.
