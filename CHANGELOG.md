# Changelog

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
