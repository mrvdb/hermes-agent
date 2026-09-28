#!/usr/bin/env node
// Report web-toolchain native modules that cannot load on this host.
//
// Tailwind v4 compiles CSS through Rust addons (lightningcss, @tailwindcss/oxide)
// that publish prebuilds for a fixed set of platforms. pnpm installs the JS
// package everywhere and silently skips the missing platform binary, so the
// dashboard build later dies inside Vite's config load. Loading every copy the
// web workspace's dependency tree reaches, as the build would, separates "this
// host has no build of X" from an ordinary build failure.
//
// Prints one "<name>@<version>" per unloadable copy; exit 0 either way.
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { parseArgs } from 'node:util'
import { isMain } from './frontend-common.mjs'

export const WEB_NATIVE_MODULES = ['lightningcss', '@tailwindcss/oxide']

// The two shapes a missing platform binary takes: lightningcss's loader fails
// to require its `<name>.<platform>-<arch>-<libc>.node`; napi-rs loaders
// (oxide) collect their attempts into "Cannot find native binding". A missing
// *JavaScript* dependency is a broken install and stays fatal.
function isMissingPlatformBinary(error) {
  const message = String(error?.message ?? '')
  if (/^Cannot find native binding\b/.test(message)) return true
  return error?.code === 'MODULE_NOT_FOUND' && /\.node'/.test(message.split('\n')[0])
}

function manifest(dir) {
  return JSON.parse(readFileSync(path.join(dir, 'package.json'), 'utf8'))
}

// The directory Node's resolution finds package `name` in from `dir`: the
// nearest node_modules/<name> up the tree, symlinks resolved. A directory, not
// an entry: a package's "exports" can hide both its manifest and its main.
function packageDir(dir, name) {
  for (let at = dir; ; at = path.dirname(at)) {
    const candidate = path.join(at, 'node_modules', name)
    if (existsSync(path.join(candidate, 'package.json'))) return realpathSync(candidate)
    if (at === path.dirname(at)) return null
  }
}

// Every installed copy of a WEB_NATIVE_MODULES package in the dashboard's
// dependency closure. Resolving the names from web/ is not enough: pnpm links
// only direct dependencies there (lightningcss arrives through vite and
// @tailwindcss/vite), and vite can carry its own lightningcss at another
// version than the one Tailwind loads.
function nativeCopies(web) {
  const root = manifest(web)
  const seen = new Set()
  const copies = []
  const queue = [[web, { ...root.devDependencies, ...root.dependencies }]]
  while (queue.length) {
    const [dir, deps] = queue.shift()
    for (const name of Object.keys(deps)) {
      const found = packageDir(dir, name)
      if (found === null || seen.has(found)) continue // optional or peer dependency not installed
      seen.add(found)
      if (WEB_NATIVE_MODULES.includes(name)) copies.push({ name, dir: found })
      const m = manifest(found)
      queue.push([found, { ...m.peerDependencies, ...m.optionalDependencies, ...m.dependencies }])
    }
  }
  return copies
}

export function unloadableWebNatives(source) {
  const missing = []
  for (const { name, dir } of nativeCopies(path.join(path.resolve(source), 'web'))) {
    try {
      createRequire(path.join(dir, 'package.json'))(dir)
    } catch (error) {
      if (!isMissingPlatformBinary(error)) throw error
      const copy = `${name}@${manifest(dir).version}`
      if (!missing.includes(copy)) missing.push(copy)
    }
  }
  return missing
}

if (isMain(import.meta.url)) {
  const { values } = parseArgs({ options: { source: { type: 'string' } } })
  if (!values.source) throw new Error('--source is required')
  for (const entry of unloadableWebNatives(values.source)) console.log(entry)
}
