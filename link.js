module.exports = {
  run: [
    {
      when: "{{exists('app/.dependencies-ready')}}",
      method: "fs.rm",
      params: {
        path: "app/.dependencies-ready"
      }
    },
    {
      method: "fs.link",
      params: {
        venv: "app/env"
      }
    },
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "python -c \"import torch, torchaudio; from pathlib import Path; Path('.dependencies-ready').touch()\""
      }
    }
  ]
}
