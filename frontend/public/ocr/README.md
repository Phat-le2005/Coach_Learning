# Local handwritten-math OCR assets

These files power the student ink-to-LaTeX suggestion in the browser. No paid API,
external model download, answer key, or exercise-content hint is used.

- CoMER INT8 encoder/decoder and vocabulary: [ink-on v0.1.0 release](https://github.com/kimseungdae/ink-on/releases/tag/v0.1.0), Apache-2.0 (see `comer/v0_1/LICENSE`).
- Browser inference code: `ink-on` v0.1.0 Apache-2.0. `ink-on/core.js` is copied from the npm release. Its single inference chunk differs only by replacing the bare ONNX Runtime import with the local relative URL, so Next.js does not rewrite the WASM runtime.
- ONNX Runtime Web files: `onnxruntime-web` v1.24.2, MIT, from the installed npm package. Runtime module and WASM must come from the same version.

The model is loaded on first use and cached by the library/browser. The response
has no calibrated confidence score. It is a suggestion that the student must
inspect and correct before a solution step is saved. OCR failure keeps the ink
visible and allows manual entry.

SHA-256 of model files:
- encoder_int8.onnx: 272f17c7b120db61db6cd8d77e695d0139144044abd57d9b23284435a5d916fa
- decoder_int8.onnx: 658901d81ca3aa4b62b0da262e8fe67ebcfdac19cfb52ca2cfd076bebd481088
- vocab.json: 6ef75b588049981d2b5b2ceedcc7066dddcbb0c7d04ee2cbfb0ec861f192a850

