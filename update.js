module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        message: "git pull"
      }
    },
    {
      when: "{{exists('app/src/fireredtts3/core.py')}}",
      method: "shell.run",
      params: {
        path: "app/src",
        message: "git pull"
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
