# Changelog

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
