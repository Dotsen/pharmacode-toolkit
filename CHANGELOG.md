# Changelog

## Unreleased

- The package ships a `py.typed` marker (PEP 561), so type checkers use its annotations.
- CI also tests Python 3.13, which the package metadata already declared.
- `decode --polarity light|auto` (`DecoderConfig.polarity`) reads light bars on a dark
  background; `auto` adds the inverted pass only when the normal one decodes nothing.
  Every detection reports its `polarity` in the JSON result.
- A code on a light patch inside a dark area (a white knockout on a dark carton, or an
  inverted code) decodes when the patch leaves less than 11 mm around it: the patch edge now
  ends the quiet zone instead of being read as one more bar.
- Benchmark: a `patch` group (`inverted-auto`, `knockout-dark`), and every negative image is
  also decoded inverted, with `polarity="auto"`.

## 0.2.1 - 2026-09-20

- Documentation describes the real-world sample check made before each release.
- README renders on PyPI: absolute image and documentation links, `pip install pharmacode-toolkit`.
- Releases are published to PyPI by a tag-triggered workflow using trusted publishing.
- CI actions updated to their current major versions.

## 0.2.0 - 2026-09-19

Fixes and options that came out of checking the decoder on publicly available
sample images.

- Human-readable captions printed next to a code no longer break the bar-height check.
- Codes that fill the frame keep their wide bars: the background kernel is sized from the strokes.
- A thin rule crossing the bars is removed by a directional opening when nothing else is found.
- `decode --allow-cropped-quiet-zone` downgrades a quiet zone cut by the image edge to a warning.
- `decode --min-confidence` reports weak detections as `LOW_CONFIDENCE` errors.
- The documentation states how the decoder was checked beyond the synthetic benchmark.

## 0.1.0 - 2026-09-18

First release.

- Encoding and decoding of one-track Pharmacode values 3..131070 with both reading directions.
- Synthetic renderer with Laetus standard and miniature dimensions, DPI, rotation, blur, noise,
  JPEG, contrast, illumination, perspective, scaling, multi-code scenes and negative samples.
- Detector and decoder for PNG, JPEG and TIFF: 0/90/180/270 degrees and small tilts,
  quiet-zone and geometry validation, stable error codes, confidence.
- `pharmacode generate`, `pharmacode decode` (JSON, annotated image, exit codes) and
  `pharmacode benchmark` (condition matrix with failure artefacts); `python -m pharmacode ...`
  is equivalent to the `pharmacode` console script.
- Documentation: algorithm and threshold provenance, CLI, benchmark, limitations, provenance.
- CI on Linux and Windows with a wheel install smoke test.
