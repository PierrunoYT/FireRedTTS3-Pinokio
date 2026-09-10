"""Gradio Web UI for FireRedTTS3.

Upstream ships a Python API but no interface, so this launcher provides one.
It exposes the four documented tasks -- zero-shot voice cloning, voice design,
semantic editing, and acoustic editing -- over the same `fireredtts3.core`
entry points used in the upstream README.

The Base and Instruct checkpoints are roughly 8.5 GB each and share a 3.8 GB
audio autoencoder, so only one variant is ever resident: switching tabs to a
task served by the other variant unloads the current one first.

Upstream runs on CUDA only -- the device, the bfloat16 autocast, and the
FlashAttention backend are all hardcoded -- so this interface is CUDA only too.

This file sits beside the upstream checkout rather than inside it, so that
Reset and Update can wipe and re-clone `src/` without touching it.
"""

import argparse
import os
import sys
import gc
import time
from datetime import datetime

import gradio as gr
import torch
import torchaudio

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(APP_DIR, "src")
if not os.path.isdir(SRC_DIR):
    raise SystemExit(f"Upstream checkout '{SRC_DIR}' not found. Run the launcher's Install first.")
sys.path.insert(0, SRC_DIR)

from fireredtts3.core import FireRedTTS3, FireRedTTS3Instruct
from fireredtts3.utils.text_tokenizer import MULTI_LANG_TAGS, MULTI_DIALECT_TAGS


AUTO_LANGUAGE = "Auto-detect"
LANGUAGES = [tag.strip("<|>") for tag in MULTI_LANG_TAGS]
DIALECTS = [tag.strip("<|>") for tag in MULTI_DIALECT_TAGS]
LANGUAGE_CHOICES = [AUTO_LANGUAGE] + LANGUAGES + DIALECTS

OUTPUT_DIR = os.path.join(APP_DIR, "outputs")


class ModelManager:
    """Loads one FireRedTTS3 variant at a time and keeps it warm."""

    def __init__(self, model_dir: str, use_wetext: bool, use_llm_tn: bool, use_fasttext: bool):
        self.model_dir = model_dir
        self.use_wetext = use_wetext
        self.use_llm_tn = use_llm_tn
        self.use_fasttext = use_fasttext
        self.variant = None
        self.model = None

    def get(self, variant: str, progress=None):
        if self.variant == variant:
            return self.model
        if self.model is not None:
            if progress is not None:
                progress(0.0, desc=f"Unloading {self.variant}")
            self.unload()
        if progress is not None:
            progress(0.1, desc=f"Loading FireRedTTS3-{variant.capitalize()} (first run takes a while)")
        cls = FireRedTTS3 if variant == "base" else FireRedTTS3Instruct
        self.model = cls(
            self.model_dir,
            use_fasttext=self.use_fasttext,
            use_wetext=self.use_wetext,
            use_llm_tn=self.use_llm_tn,
        )
        self.variant = variant
        return self.model

    def unload(self):
        self.model = None
        self.variant = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


MANAGER: ModelManager = None


def save_audio(audio: torch.Tensor, sample_rate: int, prefix: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"{prefix}-{stamp}.wav")
    torchaudio.save(path, audio.cpu(), sample_rate)
    return path


def load_prompt(path: str):
    audio, sr = torchaudio.load(path)
    return audio, sr


def resolve_language(choice: str):
    return None if choice == AUTO_LANGUAGE else choice


def run_clone(
    prompt_audio_path, prompt_text, text, language,
    n_timesteps, inference_cfg, stop_threshold, seed,
    do_tn, do_split, cross_fade_ms,
    progress=gr.Progress(),
):
    if not prompt_audio_path:
        raise gr.Error("Upload or record a reference clip first.")
    if not text or not text.strip():
        raise gr.Error("Enter some text to synthesize.")
    if not prompt_text or not prompt_text.strip():
        raise gr.Error(
            "Enter the transcript of the reference clip. FireRedTTS3 conditions on "
            "the reference text, so an empty or wrong transcript degrades the clone."
        )

    model = MANAGER.get("base", progress)
    prompt_audio, prompt_audio_sr = load_prompt(prompt_audio_path)
    progress(0.4, desc="Synthesizing")
    started = time.time()
    audio, sr = model.generate(
        text=text,
        language=resolve_language(language),
        prompt_text=prompt_text,
        prompt_audio=prompt_audio,
        prompt_audio_sr=prompt_audio_sr,
        n_timesteps=int(n_timesteps),
        inference_cfg=float(inference_cfg),
        stop_threshold=float(stop_threshold),
        seed=int(seed),
        do_tn=bool(do_tn),
        do_split=bool(do_split),
        cross_fade_ms=float(cross_fade_ms),
    )
    path = save_audio(audio, sr, "clone")
    elapsed = time.time() - started
    duration = audio.shape[-1] / sr
    return path, f"{duration:.1f} s of audio in {elapsed:.1f} s -> {path}"


def run_voice_design(
    instruction, text, language,
    n_timesteps, inference_cfg, seed, do_tn, do_split, cross_fade_ms,
    progress=gr.Progress(),
):
    if not instruction or not instruction.strip():
        raise gr.Error("Describe the voice you want (gender, age, timbre, pace, emotion, accent).")
    if not text or not text.strip():
        raise gr.Error("Enter some text to synthesize.")

    model = MANAGER.get("instruct", progress)
    progress(0.4, desc="Planning voice and synthesizing")
    audio, sr, plan = model.generate_voice_design(
        instruction=instruction,
        text=text,
        language=resolve_language(language),
        n_timesteps=int(n_timesteps),
        inference_cfg=float(inference_cfg),
        seed=int(seed),
        do_tn=bool(do_tn),
        do_split=bool(do_split),
        cross_fade_ms=float(cross_fade_ms),
    )
    path = save_audio(audio, sr, "design")
    return path, plan or "", f"Saved to {path}"


def run_instruct_clone(
    prompt_audio_path, prompt_text, text, language,
    n_timesteps, inference_cfg, stop_threshold, seed,
    do_tn, do_split, cross_fade_ms,
    progress=gr.Progress(),
):
    if not prompt_audio_path:
        raise gr.Error("Upload or record a reference clip first.")
    if not prompt_text or not prompt_text.strip():
        raise gr.Error("Enter the transcript of the reference clip.")
    if not text or not text.strip():
        raise gr.Error("Enter some text to synthesize.")

    model = MANAGER.get("instruct", progress)
    prompt_audio, prompt_audio_sr = load_prompt(prompt_audio_path)
    progress(0.4, desc="Synthesizing")
    audio, sr = model.generate_tts(
        prompt_text=prompt_text,
        prompt_audio=prompt_audio,
        prompt_audio_sr=prompt_audio_sr,
        text=text,
        language=resolve_language(language),
        n_timesteps=int(n_timesteps),
        inference_cfg=float(inference_cfg),
        stop_threshold=float(stop_threshold),
        seed=int(seed),
        do_tn=bool(do_tn),
        do_split=bool(do_split),
        cross_fade_ms=float(cross_fade_ms),
    )
    path = save_audio(audio, sr, "clone-instruct")
    return path, f"Saved to {path}"


def run_semantic_edit(audio_path, instruction, n_timesteps, inference_cfg, seed, progress=gr.Progress()):
    if not audio_path:
        raise gr.Error("Upload the audio you want to edit.")
    if not instruction or not instruction.strip():
        raise gr.Error("Describe the edit, for example: Replace 'cats' with 'dogs'.")

    model = MANAGER.get("instruct", progress)
    audio_in, audio_in_sr = load_prompt(audio_path)
    progress(0.4, desc="Editing")
    audio, sr, edited_text = model.generate_semantic_edit(
        instruction=instruction,
        audio_in=audio_in,
        audio_in_sr=audio_in_sr,
        n_timesteps=int(n_timesteps),
        inference_cfg=float(inference_cfg),
        seed=int(seed),
    )
    path = save_audio(audio, sr, "edit-semantic")
    return path, edited_text or "", f"Saved to {path}"


def run_acoustic_edit(audio_path, kind, speed, pitch, volume, n_timesteps, inference_cfg, seed, progress=gr.Progress()):
    if not audio_path:
        raise gr.Error("Upload the audio you want to edit.")

    # The acoustic-edit head was trained on fixed templates; free-form phrasing
    # is not supported, so the instruction is composed from the controls.
    if kind == "Speed":
        instruction = f"adjust the speed to {speed:.1f}x"
    elif kind == "Pitch":
        steps = int(pitch)
        if steps == 0:
            raise gr.Error("Pitch shift must be between -6 and +6 steps, and not 0.")
        instruction = f"shift the pitch by {steps} step{'s' if abs(steps) != 1 else ''}"
    else:
        instruction = f"adjust the volume to {volume:.1f}"

    model = MANAGER.get("instruct", progress)
    audio_in, audio_in_sr = load_prompt(audio_path)
    progress(0.4, desc="Editing")
    audio, sr = model.generate_acoustic_edit(
        instruction=instruction,
        audio_in=audio_in,
        audio_in_sr=audio_in_sr,
        n_timesteps=int(n_timesteps),
        inference_cfg=float(inference_cfg),
        seed=int(seed),
    )
    path = save_audio(audio, sr, "edit-acoustic")
    return path, f'Applied "{instruction}". Saved to {path}'


def advanced_block(default_cfg: float, default_seed: int, with_stop: bool, with_text: bool):
    """Shared inference controls. Returns the components in call order."""
    with gr.Accordion("Advanced", open=False):
        with gr.Row():
            n_timesteps = gr.Slider(
                4, 50, value=10, step=1, label="Flow-matching steps",
                info="More steps trade speed for fidelity.",
            )
            inference_cfg = gr.Slider(
                1.0, 5.0, value=default_cfg, step=0.1, label="CFG scale",
                info="Higher follows the condition more closely.",
            )
        stop_threshold = None
        if with_stop:
            stop_threshold = gr.Slider(
                0.1, 0.9, value=0.5, step=0.05, label="Stop threshold",
                info="Lower ends the utterance sooner.",
            )
        seed = gr.Number(value=default_seed, precision=0, label="Seed")
        do_tn = do_split = cross_fade_ms = None
        if with_text:
            with gr.Row():
                do_tn = gr.Checkbox(value=True, label="Text normalization")
                do_split = gr.Checkbox(value=True, label="Split long text into sentences")
            cross_fade_ms = gr.Slider(
                0, 200, value=50, step=5, label="Sentence cross-fade (ms)",
            )
    return n_timesteps, inference_cfg, stop_threshold, seed, do_tn, do_split, cross_fade_ms


def describe_runtime() -> str:
    if not torch.cuda.is_available():
        return "no CUDA device detected"
    name = torch.cuda.get_device_name(0)
    total = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    return f"{name}, {total:.0f} GB VRAM, bfloat16"


def check_runtime():
    """Fail early and clearly on a GPU or a PyTorch build that cannot work.

    Upstream hardcodes CUDA, a bfloat16 autocast, and FlashAttention 2, so
    each of these is a hard requirement rather than a performance preference.
    Checking here turns three confusing mid-inference failures into one
    startup message.
    """
    if not torch.cuda.is_available():
        raise SystemExit(
            "FireRedTTS3 requires a CUDA GPU. Upstream hardcodes the device, the bfloat16 "
            "autocast, and the FlashAttention backend, so there is no CPU or MPS path."
        )

    major, minor = torch.cuda.get_device_capability()
    arch = f"sm_{major}{minor}"

    # Run a real kernel rather than checking `arch in get_arch_list()`. That
    # comparison gives false negatives: an RTX 4090 reports sm_89, which the
    # cu128 wheels do not list, yet it runs fine because the driver JITs from
    # PTX. Executing an op is the only reliable answer.
    try:
        probe = torch.randn(8, 8, device="cuda")
        (probe @ probe).sum().item()
    except Exception as error:
        raise SystemExit(
            f"This PyTorch build cannot run kernels on {torch.cuda.get_device_name(0)} ({arch}).\n"
            f"It was built for: {', '.join(torch.cuda.get_arch_list())}\n"
            f"Underlying error: {error}\n"
            "Reinstall with a PyTorch build that targets your GPU."
        )

    if not torch.cuda.is_bf16_supported(including_emulation=False):
        raise SystemExit(
            f"{torch.cuda.get_device_name(0)} ({arch}) has no native bfloat16 support, which "
            "FireRedTTS3 requires. An Ampere (RTX 30-series) or newer GPU is needed."
        )

    # Pinokio does not abort a script when a step exits nonzero, so a failed
    # `git apply` during Install would otherwise surface much later as an
    # opaque ImportError deep inside from_pretrained.
    from fireredtts3.llm.fireredtts3_base import Qwen3_1_7B_ConfigDict

    if Qwen3_1_7B_ConfigDict.get("attn_implementation") == "flash_attention_2":
        try:
            import flash_attn  # noqa: F401
        except ImportError:
            raise SystemExit(
                "The upstream checkout still requests FlashAttention, and flash_attn is not "
                "installed. sdpa.patch did not apply. Run Reset, then Install again."
            )

    total = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    if total < 15:
        print(
            f"[WARN] {total:.0f} GB of VRAM detected. The resident weights are about 12 GB, "
            "so synthesis is likely to run out of memory.",
            flush=True,
        )


def build_ui(model_dir: str):
    # All synthesis events share one queue: model swaps must wait for inference.
    runtime = describe_runtime()

    with gr.Blocks(title="FireRedTTS3", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            f"# FireRedTTS3\n"
            f"Zero-shot voice cloning in 24 languages and 21 Chinese dialects, plus "
            f"instruction-driven voice design and speech editing.\n\n"
            f"`{runtime}` &nbsp;&nbsp; checkpoints: `{model_dir}`"
        )

        with gr.Tab("Voice Cloning"):
            gr.Markdown(
                "Clone a voice from one reference clip using **FireRedTTS3-Base**. "
                "For the best result, use a reference in the same language or dialect "
                "as the text — the output inherits the reference's speaking style."
            )
            with gr.Row():
                with gr.Column():
                    clone_prompt_audio = gr.Audio(
                        label="Reference audio", type="filepath", sources=["upload", "microphone"]
                    )
                    clone_prompt_text = gr.Textbox(
                        label="Reference transcript",
                        placeholder="Exactly what is said in the reference clip",
                        lines=2,
                    )
                    clone_text = gr.Textbox(label="Text to synthesize", lines=5)
                    clone_language = gr.Dropdown(
                        LANGUAGE_CHOICES, value=AUTO_LANGUAGE, label="Language / dialect",
                        info="Explicit tags outperform auto-detection.",
                    )
                    clone_adv = advanced_block(2.0, 1234, with_stop=True, with_text=True)
                    clone_btn = gr.Button("Synthesize", variant="primary")
                with gr.Column():
                    clone_output = gr.Audio(label="Output", type="filepath")
                    clone_status = gr.Textbox(label="Status", interactive=False)

            clone_btn.click(
                run_clone,
                inputs=[
                    clone_prompt_audio, clone_prompt_text, clone_text, clone_language,
                    clone_adv[0], clone_adv[1], clone_adv[2], clone_adv[3],
                    clone_adv[4], clone_adv[5], clone_adv[6],
                ],
                outputs=[clone_output, clone_status],
                concurrency_id="gpu",
                concurrency_limit=1,
            )

        with gr.Tab("Voice Design"):
            gr.Markdown(
                "Generate a brand-new voice from a description, with no reference audio, "
                "using **FireRedTTS3-Instruct**. The model first writes a voice-attribute "
                "plan, then renders the audio."
            )
            with gr.Row():
                with gr.Column():
                    design_instruction = gr.Textbox(
                        label="Voice description",
                        placeholder="A warm young woman's voice, slightly slow, a little playful.",
                        lines=3,
                    )
                    design_text = gr.Textbox(label="Text to synthesize", lines=5)
                    design_language = gr.Dropdown(
                        LANGUAGE_CHOICES, value=AUTO_LANGUAGE, label="Language / dialect"
                    )
                    design_adv = advanced_block(1.2, 2, with_stop=False, with_text=True)
                    design_btn = gr.Button("Generate voice", variant="primary")
                with gr.Column():
                    design_output = gr.Audio(label="Output", type="filepath")
                    design_plan = gr.Textbox(label="Voice plan", lines=6, interactive=False)
                    design_status = gr.Textbox(label="Status", interactive=False)

            design_btn.click(
                run_voice_design,
                inputs=[
                    design_instruction, design_text, design_language,
                    design_adv[0], design_adv[1], design_adv[3],
                    design_adv[4], design_adv[5], design_adv[6],
                ],
                outputs=[design_output, design_plan, design_status],
                concurrency_id="gpu",
                concurrency_limit=1,
            )

        with gr.Tab("Semantic Edit"):
            gr.Markdown(
                "Change the words in an existing recording — insert, delete, or substitute — "
                "while keeping the voice. Uses **FireRedTTS3-Instruct**."
            )
            with gr.Row():
                with gr.Column():
                    semantic_audio = gr.Audio(
                        label="Audio to edit", type="filepath", sources=["upload", "microphone"]
                    )
                    semantic_instruction = gr.Textbox(
                        label="Edit instruction",
                        placeholder="Replace 'cats' with 'dogs'.",
                        lines=2,
                    )
                    semantic_adv = advanced_block(1.2, 1234, with_stop=False, with_text=False)
                    semantic_btn = gr.Button("Apply edit", variant="primary")
                with gr.Column():
                    semantic_output = gr.Audio(label="Output", type="filepath")
                    semantic_text = gr.Textbox(label="Edited transcript", lines=4, interactive=False)
                    semantic_status = gr.Textbox(label="Status", interactive=False)

            semantic_btn.click(
                run_semantic_edit,
                inputs=[
                    semantic_audio, semantic_instruction,
                    semantic_adv[0], semantic_adv[1], semantic_adv[3],
                ],
                outputs=[semantic_output, semantic_text, semantic_status],
                concurrency_id="gpu",
                concurrency_limit=1,
            )

        with gr.Tab("Acoustic Edit"):
            gr.Markdown(
                "Adjust speed, pitch, or volume of a recording. The model was trained on "
                "fixed instruction templates, so the instruction is built from these controls "
                "rather than typed freely."
            )
            with gr.Row():
                with gr.Column():
                    acoustic_audio = gr.Audio(
                        label="Audio to edit", type="filepath", sources=["upload", "microphone"]
                    )
                    acoustic_kind = gr.Radio(
                        ["Speed", "Pitch", "Volume"], value="Speed", label="Attribute"
                    )
                    acoustic_speed = gr.Slider(0.5, 2.0, value=1.0, step=0.1, label="Speed")
                    acoustic_pitch = gr.Slider(-6, 6, value=1, step=1, label="Pitch (steps)", visible=False)
                    acoustic_volume = gr.Slider(0.3, 2.0, value=1.0, step=0.1, label="Volume", visible=False)
                    acoustic_adv = advanced_block(1.2, 1234, with_stop=False, with_text=False)
                    acoustic_btn = gr.Button("Apply edit", variant="primary")
                with gr.Column():
                    acoustic_output = gr.Audio(label="Output", type="filepath")
                    acoustic_status = gr.Textbox(label="Status", interactive=False)

            def toggle_controls(kind):
                return (
                    gr.update(visible=kind == "Speed"),
                    gr.update(visible=kind == "Pitch"),
                    gr.update(visible=kind == "Volume"),
                )

            acoustic_kind.change(
                toggle_controls,
                inputs=acoustic_kind,
                outputs=[acoustic_speed, acoustic_pitch, acoustic_volume],
            )
            acoustic_btn.click(
                run_acoustic_edit,
                inputs=[
                    acoustic_audio, acoustic_kind, acoustic_speed, acoustic_pitch, acoustic_volume,
                    acoustic_adv[0], acoustic_adv[1], acoustic_adv[3],
                ],
                outputs=[acoustic_output, acoustic_status],
                concurrency_id="gpu",
                concurrency_limit=1,
            )

        with gr.Tab("Cloning (Instruct)"):
            gr.Markdown(
                "The same zero-shot cloning task run through **FireRedTTS3-Instruct** instead "
                "of Base. Use this to avoid a model swap when you are already editing or "
                "designing voices; Base scores higher on cloning benchmarks."
            )
            with gr.Row():
                with gr.Column():
                    ic_prompt_audio = gr.Audio(
                        label="Reference audio", type="filepath", sources=["upload", "microphone"]
                    )
                    ic_prompt_text = gr.Textbox(label="Reference transcript", lines=2)
                    ic_text = gr.Textbox(label="Text to synthesize", lines=5)
                    ic_language = gr.Dropdown(
                        LANGUAGE_CHOICES, value=AUTO_LANGUAGE, label="Language / dialect"
                    )
                    ic_adv = advanced_block(2.0, 1234, with_stop=True, with_text=True)
                    ic_btn = gr.Button("Synthesize", variant="primary")
                with gr.Column():
                    ic_output = gr.Audio(label="Output", type="filepath")
                    ic_status = gr.Textbox(label="Status", interactive=False)

            ic_btn.click(
                run_instruct_clone,
                inputs=[
                    ic_prompt_audio, ic_prompt_text, ic_text, ic_language,
                    ic_adv[0], ic_adv[1], ic_adv[2], ic_adv[3],
                    ic_adv[4], ic_adv[5], ic_adv[6],
                ],
                outputs=[ic_output, ic_status],
                concurrency_id="gpu",
                concurrency_limit=1,
            )

        gr.Markdown(
            "Generated audio is written to `outputs/`. FireRedTTS3 is released for academic "
            "research; commercial use of the voice-cloning functionality is prohibited by the "
            "upstream model card. Only clone voices you have permission to use."
        )

    return demo


def main():
    parser = argparse.ArgumentParser(description="FireRedTTS3 Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--model_dir", default=os.path.join(SRC_DIR, "pretrained_models"))
    parser.add_argument("--share", action="store_true")
    parser.add_argument(
        "--llm_tn", action="store_true",
        help="Use LLM-based text normalization for all languages (needs API credentials in .env)",
    )
    parser.add_argument(
        "--no_wetext", action="store_true",
        help="Disable the local wetext Chinese/English normalizer",
    )
    parser.add_argument(
        "--no_fasttext", action="store_true",
        help="Disable FastText language auto-detection",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.model_dir):
        raise SystemExit(
            f"Checkpoint directory '{args.model_dir}' not found. Run the launcher's Install first."
        )

    global MANAGER
    MANAGER = ModelManager(
        model_dir=args.model_dir,
        use_wetext=not args.no_wetext,
        use_llm_tn=args.llm_tn,
        use_fasttext=not args.no_fasttext,
    )

    check_runtime()

    print(f"[INFO] {describe_runtime()}", flush=True)
    print("[INFO] Checkpoints load on the first synthesis, not at startup.", flush=True)

    demo = build_ui(args.model_dir)
    demo.queue().launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        inbrowser=False,
        show_api=False,
    )


if __name__ == "__main__":
    main()
