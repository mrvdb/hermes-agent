import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { afterEach, expect, test } from 'vitest'
import { unloadableWebNatives } from '../scripts/build/web-natives.mjs'

const temporary = []
afterEach(() => { for (const dir of temporary.splice(0)) rmSync(dir, { recursive: true, force: true }) })

function put(root, name, content) {
  const file = path.join(root, name)
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, content)
}

// A dashboard workspace whose `name` package loads with `body`. The manifest
// hides package.json behind "exports", as lightningcss does.
function workspace(packages) {
  const source = mkdtempSync(path.join(tmpdir(), 'web natives '))
  temporary.push(source)
  put(source, 'web/package.json', '{"name":"web"}')
  for (const [name, body] of Object.entries(packages)) {
    put(source, `node_modules/${name}/package.json`,
      JSON.stringify({ name, version: '1.2.3', main: 'index.js', exports: { '.': './index.js' } }))
    put(source, `node_modules/${name}/index.js`, body)
  }
  return source
}

const missingDotNode = "throw Object.assign(new Error(\"Cannot find module '../lightningcss.linux-ppc64-gnu.node'\"), {code: 'MODULE_NOT_FOUND'})"
const napiMissing = "throw new Error('Cannot find native binding. npm has a bug related to optional dependencies')"

test('reports modules whose platform binary is missing, in either loader shape', () => {
  const source = workspace({ lightningcss: missingDotNode, '@tailwindcss/oxide': napiMissing })
  expect(unloadableWebNatives(source)).toEqual(['lightningcss@1.2.3', '@tailwindcss/oxide@1.2.3'])
})

test('reports nothing when the modules load or are not dependencies', () => {
  expect(unloadableWebNatives(workspace({ lightningcss: 'module.exports = {}' }))).toEqual([])
})

test('a broken JavaScript dependency is not mistaken for a platform gap', () => {
  const source = workspace({ lightningcss: "require('detect-libc')" })
  expect(() => unloadableWebNatives(source)).toThrow(/detect-libc/)
})
