module.exports = {
  requires: {
    bundle: "ai"
  },
  run: [
    // `fireredtts3/core.py` is the marker for a usable checkout. Testing for
    // it rather than for `.git` also catches a checkout of a different
    // project, which is what earlier versions of this launcher installed.
    {
      when: "{{exists('app/env') && !exists('app/src/fireredtts3/core.py')}}",
      method: "fs.rm",
      params: {
        path: "app/env"
      }
    },
    {
      when: "{{exists('app/src') && !exists('app/src/fireredtts3/core.py')}}",
      method: "fs.rm",
      params: {
        path: "app/src"
      }
    },
    {
      when: "{{!exists('app/src/fireredtts3/core.py')}}",
      method: "shell.run",
      params: {
        path: "app",
        message: "git clone https://github.com/FireRedTeam/FireRedTTS3.git src"
      }
    },
    // Swap the three hardcoded FlashAttention call sites for PyTorch SDPA,
    // which every model class here already declares support for. This is what
    // keeps flash_attn out of requirements.txt: it has no Windows wheels and
    // compiling it from source takes hours and often fails.
    //
    // The checkout is restored first, so re-running Install over an already
    // patched tree is a no-op rather than a conflict.
    {
      method: "shell.run",
      params: {
        path: "app/src",
        message: [
          "git checkout -- fireredtts3/llm/fireredtts3_base.py fireredtts3/redae/redae.py",
          "git apply ../../sdpa.patch"
        ]
      }
    },
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: [
          "uv pip install -r requirements.txt"
        ]
      }
    },
    // Last, so that the platform-matched build wins. Resolving
    // requirements.txt pulls in whatever torch the dependency graph asks for,
    // and torch.js force-reinstalls over it.
    {
      method: "script.start",
      params: {
        uri: "torch.js",
        params: {
          venv: "env",
          path: "app"
        }
      }
    },
    // Base + Instruct + RedAE + speaker encoder, about 21 GB in total.
    {
      method: "shell.run",
      params: {
        venv: "../env",
        path: "app/src",
        message: [
          "python -c \"from huggingface_hub import snapshot_download; snapshot_download('FireRedTeam/FireRedTTS3', local_dir='pretrained_models')\""
        ]
      }
    },
    {
      method: "notify",
      params: {
        html: "FireRedTTS3 installation complete. Click Start to open the Web UI."
      }
    }
  ]
}
