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
      method: "fs.rm",
      params: {
        path: "app/env"
      }
    },
    {
      method: "fs.rm",
      params: {
        path: "app/src"
      }
    },
    {
      method: "fs.rm",
      params: {
        path: "app/outputs"
      }
    }
  ]
}
