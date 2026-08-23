module.exports = {
  version: "5.0",
  menu: async (kernel, info) => {
    const installed =
      info.exists("app/env") &&
      info.exists("app/src/fireredtts3/core.py") &&
      info.exists("app/src/pretrained_models/redae/model.safetensors")
    const running = {
      install: info.running("install.js"),
      start: info.running("start.js"),
      update: info.running("update.js"),
      reset: info.running("reset.js"),
      link: info.running("link.js")
    }

    if (running.install) {
      return [{
        default: true,
        icon: "fa-solid fa-plug",
        text: "Installing FireRedTTS3",
        href: "install.js"
      }]
    }

    if (!installed) {
      return [{
        default: true,
        icon: "fa-solid fa-plug",
        text: "Install",
        href: "install.js"
      }]
    }

    if (running.start) {
      const local = info.local("start.js")
      if (local && local.url) {
        return [{
          default: true,
          icon: "fa-solid fa-rocket",
          text: "Open Web UI",
          href: local.url
        }, {
          icon: "fa-solid fa-terminal",
          text: "Terminal",
          href: "start.js"
        }]
      }
      return [{
        default: true,
        icon: "fa-solid fa-terminal",
        text: "Starting FireRedTTS3",
        href: "start.js"
      }]
    }

    if (running.update) {
      return [{
        default: true,
        icon: "fa-solid fa-terminal",
        text: "Updating",
        href: "update.js"
      }]
    }

    if (running.reset) {
      return [{
        default: true,
        icon: "fa-solid fa-terminal",
        text: "Resetting",
        href: "reset.js"
      }]
    }

    if (running.link) {
      return [{
        default: true,
        icon: "fa-solid fa-terminal",
        text: "Deduplicating",
        href: "link.js"
      }]
    }

    return [{
      default: true,
      icon: "fa-solid fa-power-off",
      text: "Start",
      href: "start.js"
    }, {
      icon: "fa-solid fa-rotate",
      text: "Update",
      href: "update.js"
    }, {
      icon: "fa-solid fa-plug",
      text: "Reinstall",
      href: "install.js"
    }, {
      icon: "fa-solid fa-file-zipper",
      text: "<div><strong>Save Disk Space</strong><div>Deduplicate installed Python libraries</div></div>",
      href: "link.js"
    }, {
      icon: "fa-regular fa-circle-xmark",
      text: "<div><strong>Reset</strong><div>Remove the environment, source, models, and outputs</div></div>",
      href: "reset.js",
      confirm: "Reset FireRedTTS3 and delete its downloaded models and generated outputs?"
    }]
  }
}
