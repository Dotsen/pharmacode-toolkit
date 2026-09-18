# Provenance

- This toolkit is an independent implementation written from public
  descriptions of the one-track Pharmacode format. It shares no code, parameters
  or data with any other Pharmacode reader.
- Every image in this repository (`examples/`) and every test fixture is produced
  by `pharmacode.rendering` from a fixed seed. No real packaging artwork, product
  names or scanned material are included.
- Thresholds derive from the physical dimensions in the Laetus PHARMA-CODE Guide
  or from the synthetic benchmark; `docs/algorithm.md` lists the origin of each.

## Sources for the format

| source | used for |
|---|---|
| Laetus PHARMA-CODE Guide (public PDF mirror, gomaro.ch) | dimensions, tolerances, quiet zone, reading direction, combination table |
| Wikipedia, "Pharmacode" | value range, weights, decoding formula |
| Laetus knowledge base, Pharma-Code series 1 and 3 | direction ambiguity, no start/stop pattern |
| zint `backend/medical.c` (BSD-3-Clause), BWIPP `pharmacode.ps.src` (MIT), JsBarcode (MIT) | cross-checking encoding test vectors only; no code was reused |

## Dependencies and licences

| package | licence |
|---|---|
| numpy | BSD-3-Clause |
| opencv-python-headless (OpenCV) | Apache-2.0 |
| pytest (dev) | MIT |
| ruff (dev) | MIT |
| hatchling (build) | MIT |
