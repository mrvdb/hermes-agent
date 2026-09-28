import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
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

function source() {
  const dir = mkdtempSync(path.join(tmpdir(), 'web natives '))
  temporary.push(dir)
  return dir
}

// A package at `dir` that loads with `body`. The manifest hides package.json
// behind "exports", as lightningcss does.
function pkg(root, dir, name, { version = '1.2.3', body = 'module.exports = {}', dependencies = {} } = {}) {
  put(root, `${dir}/package.json`,
    JSON.stringify({ name, version, main: 'index.js', exports: { '.': './index.js' }, dependencies }))
  put(root, `${dir}/index.js`, body)
}

function link(root, from, to) {
  mkdirSync(path.dirname(path.join(root, from)), { recursive: true })
  symlinkSync(path.join(root, to), path.join(root, from), 'dir')
}

// A dashboard workspace depending directly on each `name`, hoisted as npm lays it out.
function workspace(packages) {
  const root = source()
  put(root, 'web/package.json', JSON.stringify({ name: 'web', devDependencies: Object.fromEntries(
    Object.keys(packages).map(name => [name, '1.2.3'])) }))
  for (const [name, body] of Object.entries(packages)) pkg(root, `node_modules/${name}`, name, { body })
  return root
}

const missingDotNode = "throw Object.assign(new Error(\"Cannot find module '../lightningcss.linux-ppc64-gnu.node'\"), {code: 'MODULE_NOT_FOUND'})"
const napiMissing = "throw new Error('Cannot find native binding. npm has a bug related to optional dependencies')"

test('reports modules whose platform binary is missing, in either loader shape', () => {
  const root = workspace({ lightningcss: missingDotNode, '@tailwindcss/oxide': napiMissing })
  expect(unloadableWebNatives(root)).toEqual(['lightningcss@1.2.3', '@tailwindcss/oxide@1.2.3'])
})

test('reports nothing when the modules load or are not dependencies', () => {
  expect(unloadableWebNatives(workspace({ lightningcss: 'module.exports = {}' }))).toEqual([])
  const root = workspace({})
  pkg(root, 'node_modules/lightningcss', 'lightningcss', { body: missingDotNode })
  expect(unloadableWebNatives(root)).toEqual([])
})

test('a broken JavaScript dependency is not mistaken for a platform gap', () => {
  const root = workspace({ lightningcss: "require('hermes-no-such-js-dependency')" })
  expect(() => unloadableWebNatives(root)).toThrow(/hermes-no-such-js-dependency/)
})

// pnpm links only web's direct dependencies into web/node_modules; lightningcss
// sits beside the packages that load it in the virtual store, and vite carries
// its own copy at another version.
test('finds every copy the dependency tree reaches in a pnpm layout', () => {
  const root = source()
  put(root, 'web/package.json', JSON.stringify({ name: 'web', devDependencies: { '@tailwindcss/vite': '4', vite: '8' } }))
  const store = 'node_modules/.pnpm'
  for (const version of ['1.32.0', '1.33.0']) {
    pkg(root, `${store}/lightningcss@${version}/node_modules/lightningcss`, 'lightningcss', { version, body: missingDotNode })
  }
  pkg(root, `${store}/@tailwindcss+vite@4/node_modules/@tailwindcss/vite`, '@tailwindcss/vite',
    { dependencies: { lightningcss: '1.32.0' } })
  link(root, `${store}/@tailwindcss+vite@4/node_modules/lightningcss`, `${store}/lightningcss@1.32.0/node_modules/lightningcss`)
  pkg(root, `${store}/vite@8/node_modules/vite`, 'vite', { dependencies: { lightningcss: '1.33.0' } })
  link(root, `${store}/vite@8/node_modules/lightningcss`, `${store}/lightningcss@1.33.0/node_modules/lightningcss`)
  link(root, 'web/node_modules/@tailwindcss/vite', `${store}/@tailwindcss+vite@4/node_modules/@tailwindcss/vite`)
  link(root, 'web/node_modules/vite', `${store}/vite@8/node_modules/vite`)
  expect(unloadableWebNatives(root)).toEqual(['lightningcss@1.32.0', 'lightningcss@1.33.0'])
})
