module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        message: "git pull"
      }
    },
    // Restore the patched files before pulling, otherwise git refuses to
    // overwrite them. Install re-applies sdpa.patch afterwards.
    {
      when: "{{exists('app/src/fireredtts3/core.py')}}",
      method: "shell.run",
      params: {
        path: "app/src",
        message: [
          "git checkout -- fireredtts3/llm/fireredtts3_base.py fireredtts3/redae/redae.py",
          "git pull"
        ]
      }
    },
    {
      method: "script.start",
      params: {
        uri: "install.js"
      }
    }
  ]
}
