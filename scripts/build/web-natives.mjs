#!/usr/bin/env node
// Report web-toolchain native modules that cannot load on this host.
//
// Tailwind v4 compiles CSS through Rust addons (lightningcss, @tailwindcss/oxide)
// that publish prebuilds for a fixed set of platforms. npm installs the JS
// package everywhere and silently skips the missing platform binary, so the
// dashboard build later dies inside Vite's config load. Loading each one from
// the web workspace, exactly as the build would, separates "this host has no
// build of X" from an ordinary build failure.
//
// Prints one "<name>@<version>" per unloadable module; exit 0 either way.
import { existsSync, readFileSync } from 'node:fs'
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

// A package's own manifest, found from its resolved entry: `<name>/package.json`
// is not resolvable when the package's "exports" map omits it (lightningcss).
function manifestVersion(entry, name) {
  for (let dir = path.dirname(entry); dir !== path.dirname(dir); dir = path.dirname(dir)) {
    const candidate = path.join(dir, 'package.json')
    if (!existsSync(candidate)) continue
    const manifest = JSON.parse(readFileSync(candidate, 'utf8'))
    if (manifest.name === name) return manifest.version
  }
  return 'unknown'
}

export function unloadableWebNatives(source) {
  const require = createRequire(path.join(path.resolve(source), 'web', 'package.json'))
  const missing = []
  for (const name of WEB_NATIVE_MODULES) {
    let entry
    try {
      entry = require.resolve(name)
    } catch {
      continue // not a dependency of this checkout's dashboard
    }
    try {
      require(name)
    } catch (error) {
      if (!isMissingPlatformBinary(error)) throw error
      missing.push(`${name}@${manifestVersion(entry, name)}`)
    }
  }
  return missing
}

if (isMain(import.meta.url)) {
  const { values } = parseArgs({ options: { source: { type: 'string' } } })
  if (!values.source) throw new Error('--source is required')
  for (const entry of unloadableWebNatives(values.source)) console.log(entry)
}
