// Smoke test for the dsh-wechat-publish skill provider (DSH 0.2.x contract).
// Mirrors the validation rules from @deepseek-ai/dsh-skill:
//   SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
//   candidate: name / description / invocation / source / provider / rank
//   definition: name / description / invocation / source / provider / content
//   optional: whenToUse (string), metadata (record), resourceBase
import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createSkillProvider, parseFrontmatter } from '../lib/skills.js'
import { bundledPython } from '../lib/server.js'

const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
const EXPECTED = ['paper-translation', 'wechat-publish']

const provider = createSkillProvider()
assert.equal(provider.name, 'dsh-wechat-publish')

const observation = await provider.list()
const list = Array.isArray(observation) ? observation : observation.candidates
assert.ok(Array.isArray(list), 'list() must expose candidates')
assert.equal(observation.complete, true)
const names = list.map((s) => s.name).sort()
assert.deepEqual(names, EXPECTED, `unexpected skill set: ${names}`)

for (const c of list) {
  assert.match(c.name, SKILL_NAME, `invalid skill name ${c.name}`)
  assert.ok(c.description && c.description.length > 0, `${c.name} needs a description`)
  assert.deepEqual(c.invocation, { modelInvocable: true, userInvocable: true })
  assert.equal(c.source, 'bundled')
  assert.equal(c.provider, 'dsh-wechat-publish')
  assert.equal(typeof c.rank, 'number')
  assert.equal(typeof c.whenToUse, 'string', `${c.name} should declare whenToUse for 0.2.x routing`)
  assert.ok(c.whenToUse.length > 0, `${c.name} whenToUse must not be empty`)
  assert.ok(c.resourceBase?.kind === 'directory' && c.resourceBase.path, `${c.name} needs a resource base`)
  if (c.metadata !== undefined) {
    assert.equal(typeof c.metadata, 'object', `${c.name} metadata must be a record`)
    assert.ok(!Array.isArray(c.metadata), `${c.name} metadata must not be an array`)
  }
}

for (const name of EXPECTED) {
  const candidate = list.find((s) => s.name === name)
  const def = await provider.get(candidate)
  assert.ok(def, `${name} did not load`)
  assert.equal(def.name, name)
  assert.ok(def.content && def.content.length > 0)
  assert.equal(def.provider, 'dsh-wechat-publish')
  assert.equal(def.source, 'bundled')
  assert.equal(def.whenToUse, candidate.whenToUse)
  assert.ok(def.resourceBase?.path, `${name} definition needs a resource base`)
  // placeholders must be substituted, not left for the model to guess
  assert.ok(!def.content.includes('<SKILL_ROOT>'), `${name} still has <SKILL_ROOT>`)
  assert.ok(!def.content.includes('<PLUGIN_ROOT>'), `${name} still has <PLUGIN_ROOT>`)
  assert.ok(def.content.includes('在 dsh-wechat-publish 插件里使用'), `${name} missing plugin addendum`)
  assert.ok(def.content.includes(candidate.resourceBase.path), `${name} content does not mention its own directory`)
  // frontmatter stays out of the body (0.2.x sends content verbatim)
  assert.ok(!def.content.startsWith('---'), `${name} body still starts with frontmatter`)
}

// A stale / unknown locator must resolve to undefined, not throw.
assert.equal(await provider.get({ locator: '/nonexistent', name: 'paper-translation' }), undefined)

// Frontmatter parsing follows the 0.2.x canonical fields and YAML block styles.
const block = parseFrontmatter(
  '---\nname: demo\ndescription: >-\n  folded text\n  second line\nwhenToUse: |\n  多行\n  用途\ndisable-model-invocation: true\nmetadata:\n  owner: lab\n---\nbody\n',
)
assert.ok(block, 'frontmatter should parse')
assert.equal(block.data.description, 'folded text second line')
assert.equal(block.data.whenToUse, '多行\n用途\n')
assert.equal(block.data['disable-model-invocation'], true)
assert.deepEqual(block.data.metadata, { owner: 'lab' })
assert.equal(block.body, 'body\n')

console.log(`smoke ok: ${names.join(', ')}`)

// DSH 0.2.x bundled Python：解包运行时布局、应用包 Resources 布局、找不到时返回 undefined。
const temp = mkdtempSync(join(tmpdir(), 'dsh-wp-py-'))
try {
  const rel = ['runtime', 'primary-runtime', 'dependencies', 'python', 'bin']
  mkdirSync(join(temp, ...rel), { recursive: true })
  writeFileSync(join(temp, ...rel, 'python3'), '')
  assert.equal(bundledPython({ DSH_RUNTIME_DIR: temp }), join(temp, ...rel, 'python3'))
  const res = join(temp, 'app', 'Contents', 'Resources')
  mkdirSync(join(res, ...rel), { recursive: true })
  writeFileSync(join(res, ...rel, 'python3'), '')
  assert.equal(bundledPython({ DSH_RESOURCES_PATH: res }), join(res, ...rel, 'python3'))
  assert.equal(
    bundledPython({ DSH_NODE_BIN: '/usr/bin/node', DSH_HOME: join(temp, 'nowhere'), DSH_RESOURCES_PATH: join(temp, 'missing') }),
    undefined,
  )
} finally {
  rmSync(temp, { recursive: true, force: true })
}
console.log('bundled python test ok')
