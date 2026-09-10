const assert = require('node:assert/strict')
const test = require('node:test')
const launcher = require('../pinokio.js')

const complete = [
  'app/env',
  'app/.dependencies-ready',
  'app/src/fireredtts3/core.py',
  'app/src/pretrained_models/redae/model.safetensors',
  'app/src/pretrained_models/.download-complete'
]

function menu(files, running = null, local = {}) {
  return launcher.menu({}, {
    exists: path => files.includes(path),
    running: path => path === running,
    local: () => local
  })
}

test('Start requires every readiness condition', async () => {
  assert.equal((await menu(complete))[0].href, 'start.js')
  for (const missing of complete) {
    const result = await menu(complete.filter(path => path !== missing))
    assert.equal(result[0].href, 'install.js', missing)
    assert.equal(result.some(item => item.href === 'start.js'), false)
  }
})

test('fresh and partial installs offer appropriate recovery actions', async () => {
  assert.equal((await menu([]))[0].text, 'Install')
  const partial = await menu(['app/env'])
  assert.equal(partial[0].text, 'Resume Install')
  assert.equal(partial[1].href, 'reset.js')
})

test('running operations stay visible even after readiness files are removed', async () => {
  for (const running of ['install.js', 'update.js', 'reset.js', 'link.js', 'start.js']) {
    for (const files of [[], ['app/env'], complete]) {
      const result = await menu(files, running)
      assert.equal(result.length, 1)
      assert.equal(result[0].href, running)
      assert.equal(result[0].default, true)
    }
  }
})

test('a running server still opens its captured URL', async () => {
  const result = await menu(complete, 'start.js', {url: 'http://127.0.0.1:7860'})
  assert.equal(result[0].href, 'http://127.0.0.1:7860')
  assert.equal(result[1].href, 'start.js')
})
