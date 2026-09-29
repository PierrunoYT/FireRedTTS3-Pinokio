# FireRedTTS3 for Pinokio

One-click local launcher for
[FireRedTTS3](https://github.com/FireRedTeam/FireRedTTS3), FireRedTeam's
unified speech generation and editing model. It clones a voice from one
reference recording across 24 languages and 21 Chinese dialects, designs a new
voice from a written description, and edits existing recordings by instruction.

The launcher adds two things to the upstream checkout in `app/src`: a Web UI,
`app/webui.py`, which sits beside it rather than inside it so Update and Reset
can replace `app/src` freely; and `sdpa.patch`, a three-line change that swaps
the hardcoded FlashAttention backend for PyTorch SDPA.

## Features

- Zero-shot voice cloning from one reference clip, in 24 languages
- 21 Chinese dialects, including Sichuan, Shanghai, Minnan, and Wu
- Voice design from a natural-language description, with no reference audio
- Semantic editing: insert, delete, or substitute words in a recording
- Acoustic editing: speed, pitch, and volume
- Pinokio install, start, update, reset, and dependency deduplication actions

FireRedTTS3 reports the best average WER/CER and speaker similarity on
Seed-TTS-eval (3.04 / 78.8) and on MiniMax-MLS-Test (3.75 / 84.8) among the
systems in its comparison table.

## Requirements

- Python 3.10 or 3.11, provided by the Pinokio AI bundle
- **An NVIDIA GPU with 16 GB of VRAM**, Ampere (RTX 30-series) or newer
- **About 21 GB of disk space for the checkpoints**, plus room for the
  environment and generated audio

Install checks for an NVIDIA GPU first. Without one it stops with a message
instead of downloading anything.

### CUDA only

Upstream hardcodes three things: `torch.device('cuda')`, a bfloat16 autocast
on the backbone and the audio autoencoder, and
`attn_implementation='flash_attention_2'`. `sdpa.patch` removes the
FlashAttention requirement (see below), but the CUDA device and the bfloat16
autocast stay, so there is no CPU path, no Apple Silicon path, and no path for a GPU without
bfloat16 — a GTX 1080 or other pre-Ampere card cannot run this model, unlike
the IndexTTS launcher this repository previously held.

`torch.js` installs the CUDA 12.8 build of `torch==2.8.0` and
`torchaudio==2.8.0` on Windows and Linux. `webui.py` then checks four things at startup, so a
mismatch surfaces as one clear message instead of a crash mid-synthesis: that
a CUDA device exists, that the installed PyTorch actually contains kernels for
its `sm_XX` architecture, that the card supports bfloat16 natively, and that
`sdpa.patch` applied (or `flash_attn` is installed). It also warns below 15 GB
of VRAM.

### Attention backend

Upstream hardcodes `attn_implementation='flash_attention_2'` in three places:
the LLM backbone config, and twice in the audio autoencoder. `flash_attn` has
no official Windows wheels, and elsewhere pip builds it from source — hours of
compiling that frequently fails.

`sdpa.patch` changes those three strings to `'sdpa'`, so attention runs
through PyTorch's built-in scaled dot-product attention instead. Every model
class involved already declares `_supports_sdpa = True`; the authors simply
did not expose a switch. Install applies the patch after cloning, restoring
the two files first so re-running it is a no-op rather than a conflict.

This costs some speed. FlashAttention's advantage grows with sequence length
and batch size, and this is batch-1 autoregressive decode over sentence-length
chunks — the regime where the gap is narrowest. Output is unaffected.

If you would rather have FlashAttention, install a prebuilt wheel matching
your Python, torch, and CUDA into `app/env`, then delete the `git apply` step
from `install.js`.

### Memory

The Base and Instruct checkpoints are roughly 8.5 GB each and share a 3.8 GB
audio autoencoder, so the Web UI keeps only one variant resident and unloads
the other when you switch to a task it does not serve. Checkpoints load on the
first synthesis rather than at startup, so the first run of each tab is slow.

## Using the Web UI

Five tabs, each mapping to one upstream entry point:

- **Voice Cloning** — FireRedTTS3-Base. Needs the reference clip *and its
  transcript*; the model conditions on both, so a wrong transcript degrades
  the clone. Use a reference in the target language or dialect, since the
  output inherits the reference's speaking style.
- **Voice Design** — FireRedTTS3-Instruct. Describe the voice; the model first
  writes a voice-attribute plan, shown in the UI, then renders the audio.
- **Semantic Edit** — Instruct. Free-form instructions such as
  `Replace 'cats' with 'dogs'.`
- **Acoustic Edit** — Instruct. Speed, pitch, and volume are built from the
  UI controls because the model was trained on fixed instruction templates and
  does not accept free-form phrasing here. Ranges are speed `0.5`–`2.0`,
  pitch `-6` to `+6` steps, volume `0.3`–`2.0`.
- **Cloning (Instruct)** — the cloning task on the Instruct model, so you can
  stay on one checkpoint while editing. Base scores higher on cloning.

Generated audio is written to `app/outputs/`.

### Language selection

Upstream recommends an explicit language tag over auto-detection, and the
dropdown lists all 24 languages and 21 dialects. Auto-detect falls back to
the package's own script heuristic unless FastText is available, and the
launcher installs neither the `fasttext` package (its sdist does not build
against current MSVC) nor its language-id model. To enable it, install both
yourself; the model alone does nothing:

```
uv pip install --python app/env fasttext-wheel
curl -L -o app/src/fireredtts3/utils/llm_tn/models/lid.176.ftz \
  https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz
```

`fasttext-wheel` ships prebuilt wheels of the same `fasttext` module.

### Text normalization

The local `wetext` normalizer handles Chinese and English. Other languages get
basic cleaning only, unless you enable the LLM-based normalizer: put
`LLM_TN_API_URL`, `LLM_TN_API_KEY`, and `LLM_TN_MODEL` in `app/src/.env` and
add `--llm_tn` to the `webui.py` command in `start.js`. That path sends your
input text to whichever OpenAI-compatible endpoint you configure.

## Licensing and use

The code and weights are Apache-2.0. The upstream model card additionally
states that the model is intended for academic research and that **commercial
use of the voice-cloning functionality is prohibited**. Only clone voices you
have permission to use.

## Layout

| File | Purpose |
| --- | --- |
| `install.js` | Clone upstream, install PyTorch and dependencies, download checkpoints |
| `start.js` | Launch the Web UI as a daemon |
| `update.js` | Pull upstream and reinstall |
| `reset.js` | Remove the environment, source, checkpoints, and outputs |
| `link.js` | Deduplicate installed Python libraries |
| `torch.js` | CUDA PyTorch install for Windows and Linux |
| `sdpa.patch` | Swaps the hardcoded FlashAttention backend for PyTorch SDPA |
| `app/webui.py` | The Gradio interface, and the startup GPU check |
| `app/requirements.txt` | Upstream dependencies, minus torch and torchaudio |

Inside `app/`, everything except those two files is generated and safe to
delete: `env/` is the virtual environment, `src/` is the upstream checkout
including its `pretrained_models/` checkpoints, and `outputs/` holds generated
audio. Reset removes all three.

## Tests

Neither suite needs a GPU or the model weights:

```
node --test tests/launcher.test.js
python -m unittest tests/test_runtime.py
```

Name the file for `node --test`: on Windows, passing the `tests/` directory
makes Node try to run it as a single file and fail.
