// dsh-wechat-publish 的 skill 提供方（适配 DeepSeek Harness 0.2.x 的 ctx.skills 契约）。
//
// 从插件自带的 skills/<name>/SKILL.md 发现并加载 skill，注册进 DSH 的 skill
// 注册表（ctx.skills）。用户自己在 ~/.dsh/skills 或项目里装了同名 skill 时，
// 那一份优先：本提供方按「随包提供」的 rank 600 排在最后。
//
// 与 0.2.2 契约对齐的几点：
//   * candidate 携带 whenToUse（模型据此判断何时取用）与 metadata（frontmatter
//     里的自定义字段），description 之外的路由信息不再丢失；
//   * invocation 读 frontmatter 的 disable-model-invocation / user-invocable；
//   * 注册工厂接收 SkillProviderControl：SKILL.md 变更时调用 control.invalidate()，
//     注册表没有 TTL，不主动失效就会一直用旧目录；
//   * frontmatter 解析支持 YAML 的引号、块标量与一层嵌套映射（metadata:），
//     不再用逐行正则硬套。
//
// 加载正文时做两件事：
//   1. 把 <SKILL_ROOT> / <PLUGIN_ROOT> 占位符换成实际目录，使 skill 正文里的
//      「技能目录的绝对路径」在任何安装位置都成立；
//   2. 在末尾追加「在 dsh-wechat-publish 插件里使用」小节，说明插件环境下的
//      依赖 bootstrap 与路径约定。
import { existsSync, readFileSync, readdirSync, statSync, watch } from 'node:fs'
import { dirname, basename, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const PLUGIN_ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const SKILL_DIRS = [join(PLUGIN_ROOT, 'skills')]
const PROVIDER = 'dsh-wechat-publish'
/** 与本地 bundled skill 根相同的 rank，用户自己的同名 skill 优先。 */
const RANK = 600
const WATCH_DEBOUNCE_MS = 200
/** frontmatter 里由注册表消费、不再放进 metadata 的字段。 */
const RESERVED_FIELDS = new Set([
  'name',
  'description',
  'whenToUse',
  'disable-model-invocation',
  'user-invocable',
  'metadata',
])

// --------------------------------------------------------------------------- #
// frontmatter
// --------------------------------------------------------------------------- #

/** 去掉行尾注释（引号内的 # 不算注释）。 */
function stripComment(value) {
  let quote = ''
  for (let i = 0; i < value.length; i++) {
    const ch = value[i]
    if (quote) {
      if (ch === quote) quote = ''
      continue
    }
    if (ch === '"' || ch === "'") { quote = ch; continue }
    if (ch === '#' && (i === 0 || /\s/.test(value[i - 1]))) return value.slice(0, i).trimEnd()
  }
  return value
}

/** 解析标量：去引号、布尔与数字保持字符串/布尔语义由调用方决定。 */
function parseScalar(raw) {
  const value = stripComment(raw.trim())
  if (!value) return ''
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    const body = value.slice(1, -1)
    return value[0] === '"' ? body.replace(/\\n/g, '\n').replace(/\\"/g, '"') : body.replace(/''/g, "'")
  }
  if (value === 'true') return true
  if (value === 'false') return false
  return value
}

/** 折叠块（>）：相邻非空行用空格连接，空行保留为换行。 */
function foldBlock(lines) {
  const out = []
  let paragraph = []
  const flush = () => {
    if (paragraph.length) { out.push(paragraph.join(' ')); paragraph = [] }
  }
  for (const line of lines) {
    if (!line.trim()) { flush(); out.push('') } else paragraph.push(line.trim())
  }
  flush()
  return out.join('\n')
}

function minIndent(lines) {
  let min = Infinity
  for (const line of lines) {
    if (!line.trim()) continue
    min = Math.min(min, /^\s*/.exec(line)[0].length)
  }
  return min === Infinity ? 0 : min
}

/**
 * 解析 SKILL.md 的 YAML frontmatter。
 * 支持 `key: value`、引号、`|` / `>` 块标量，以及 `meta:` 下的一层嵌套映射。
 * @param {string} text - 整个 SKILL.md 文本。
 * @returns {{ data: Record<string, unknown>, body: string } | null}
 */
export function parseFrontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(text)
  if (!match) return null
  const raw = match[1]
  const data = {}
  const lines = raw.split(/\r?\n/)
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim() || line.trimStart().startsWith('#')) { i++; continue }
    const keyMatch = /^([A-Za-z0-9_.-]+)\s*:(.*)$/.exec(line)
    if (!keyMatch) { i++; continue }
    const key = keyMatch[1]
    const rest = keyMatch[2].trim()
    if (rest.startsWith('|') || rest.startsWith('>')) {
      const style = rest[0]
      const chomp = rest.slice(1).trim()
      i++
      const block = []
      while (i < lines.length && (!lines[i].trim() || /^\s+/.test(lines[i]))) block.push(lines[i++])
      const indent = minIndent(block)
      const body = block.map((l) => l.slice(indent)).join('\n')
      const text = style === '|' ? body : foldBlock(body.split('\n'))
      data[key] = chomp === '-' ? text.replace(/\n$/, '') : chomp === '+' ? text + '\n' : text.replace(/\n$/, '') + '\n'
      continue
    }
    if (!rest) {
      // 可能是一层嵌套映射（metadata:）或空值
      i++
      const block = []
      while (i < lines.length && (!lines[i].trim() || /^\s+/.test(lines[i]))) block.push(lines[i++])
      const child = {}
      for (const entry of block) {
        if (!entry.trim()) continue
        const m = /^\s+([A-Za-z0-9_.-]+)\s*:(.*)$/.exec(entry)
        if (m) child[m[1]] = parseScalar(m[2])
      }
      data[key] = Object.keys(child).length ? child : ''
      continue
    }
    data[key] = parseScalar(rest)
    i++
  }
  return { data, body: text.slice(match[0].length) }
}

function frontmatterBoolean(data, key) {
  const value = data[key]
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1') return true
  if (value === 0 || value === '0') return false
  if (typeof value === 'string') {
    const normalized = value.toLowerCase()
    if (normalized === 'true' || normalized === 'yes' || normalized === 'on') return true
    if (normalized === 'false' || normalized === 'no' || normalized === 'off') return false
  }
  return undefined
}

function invocationOf(data) {
  // 0.2.x 的规范字段；旧字段（modelInvocable 等）不再出现在新写法里。
  const disableModel = frontmatterBoolean(data, 'disable-model-invocation')
  const userInvocable = frontmatterBoolean(data, 'user-invocable')
  return {
    modelInvocable: disableModel !== true,
    userInvocable: userInvocable !== false,
  }
}

function metadataOf(data) {
  const explicit = data.metadata
  if (explicit && typeof explicit === 'object' && !Array.isArray(explicit)) return explicit
  const extra = {}
  for (const [key, value] of Object.entries(data)) {
    if (RESERVED_FIELDS.has(key)) continue
    if (value === undefined || value === '') continue
    extra[key] = value
  }
  return Object.keys(extra).length ? extra : undefined
}

// --------------------------------------------------------------------------- #
// skill 读取
// --------------------------------------------------------------------------- #

function statStamp(file) {
  try {
    const stat = statSync(file)
    return `${stat.mtimeMs}:${stat.size}`
  } catch {
    return 'missing'
  }
}

function readSkill(dir) {
  const file = join(dir, 'SKILL.md')
  let text
  try {
    text = readFileSync(file, 'utf8')
  } catch {
    return null
  }
  const parsed = parseFrontmatter(text)
  if (!parsed) return null
  const name = typeof parsed.data.name === 'string' ? parsed.data.name.trim() : ''
  const description = typeof parsed.data.description === 'string' ? parsed.data.description.trim() : ''
  if (!name || !description) return null
  const whenToUse = typeof parsed.data.whenToUse === 'string' ? parsed.data.whenToUse.trim() : ''
  const metadata = metadataOf(parsed.data)
  return {
    dir,
    file,
    name,
    description,
    ...(whenToUse ? { whenToUse } : {}),
    invocation: invocationOf(parsed.data),
    ...(metadata ? { metadata } : {}),
    body: parsed.body,
    stamp: statStamp(file),
  }
}

function readSkills(dirs) {
  return dirs.flatMap((dir) => {
    if (!existsSync(dir)) return []
    return readdirSync(dir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && existsSync(join(dir, entry.name, 'SKILL.md')))
      .map((entry) => readSkill(join(dir, entry.name)))
      .filter(Boolean)
  })
}

function candidate(skill) {
  return {
    name: skill.name,
    description: skill.description,
    ...(skill.whenToUse ? { whenToUse: skill.whenToUse } : {}),
    path: skill.file,
    invocation: skill.invocation,
    ...(skill.metadata ? { metadata: skill.metadata } : {}),
    source: 'bundled',
    provider: PROVIDER,
    rank: RANK,
    locator: skill.dir,
    resourceBase: { kind: 'directory', path: skill.dir },
  }
}

// 插件环境下对 skill 原文的补充：独立 skill 里「自己装依赖、自己找地方放产物」
// 的说明，在插件里换成插件的做法。
function addendum(skill) {
  const venv = join(PLUGIN_ROOT, '.venv', 'bin', 'python')
  const bootstrap = join(PLUGIN_ROOT, 'scripts', 'bootstrap-python.sh')
  const lines = [
    '',
    '---',
    '',
    '## 在 dsh-wechat-publish 插件里使用',
    '',
    `- 本 skill 的目录是 \`${skill.dir}\`；正文里的技能目录占位符已替换成该目录，\`references/\`、\`scripts/\` 都相对它。`,
    `- 插件根目录是 \`${PLUGIN_ROOT}\`；正文里的插件根占位符已替换成该目录。`,
  ]
  if (skill.name === 'wechat-publish') {
    lines.push(
      `- Python 依赖（markdown / requests / premailer / Pillow）首次使用运行 \`bash ${bootstrap}\` 创建插件自带 venv，之后用 \`${venv}\` 执行脚本；也可以设置 \`GZH_PYTHON\` 指向已有环境。`,
      '- Node 公式渲染依赖 mathjax-full，已随插件依赖安装；`scripts/publish.py` 会自动在插件目录、profile node_modules 与 DSH 运行时目录里找到它。',
      '- 发布凭据用环境变量 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`；缺失时 `publish.sh` 会明确报错，不要猜测或留空提交。',
    )
  }
  if (skill.name === 'paper-translation') {
    lines.push(
      `- PyMuPDF / pypdf 缺失时运行 \`bash ${bootstrap}\` 创建插件自带 venv，之后用 \`${venv}\` 执行下文的脚本；也可用 \`MICRO_PY_BIN\` 指定已有解释器。`,
      '- 本 skill 不自动 pip install；优先用插件 venv，其次 `MICRO_PY_BIN`，最后才提示用户安装。',
    )
  }
  return lines.join('\n') + '\n'
}

/**
 * 创建 skill 提供方。
 * @param {{ signal?: AbortSignal, invalidate?: () => void }} [control] - 注册表借出的
 *   生命周期与失效能力（0.2.x 的 SkillProviderControl）。缺省时退化成纯静态提供方。
 * @returns {{ name: string, list: Function, get: Function }}
 */
export function createSkillProvider(control) {
  let cache = null // { key: string, skills: ReturnType<typeof readSkills> }
  const watchers = new Map() // 根目录 + 每个 skill 目录，key 为目录路径
  let timer

  const keyOf = (dirs) => dirs.map((dir) => {
    if (!existsSync(dir)) return `${dir}:missing`
    let entries = ''
    try {
      entries = readdirSync(dir, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => `${entry.name}#${statStamp(join(dir, entry.name, 'SKILL.md'))}`)
        .join(',')
    } catch { /* 读不到就当作变化 */ }
    return `${dir}:${entries}`
  }).join('|')

  const load = () => {
    const key = keyOf(SKILL_DIRS)
    if (cache && cache.key === key) return cache.skills
    const skills = readSkills(SKILL_DIRS)
    cache = { key, skills }
    return skills
  }

  const invalidate = () => {
    cache = null
    try { control?.invalidate?.() } catch { /* 注册表已释放 */ }
  }

  const onFsEvent = () => {
    clearTimeout(timer)
    timer = setTimeout(() => {
      invalidate()
      // 目录项可能增删过，跟着重排 watcher。
      syncWatchers()
    }, WATCH_DEBOUNCE_MS)
  }

  const watchDir = (dir) => {
    if (watchers.has(dir)) return
    try {
      watchers.set(dir, watch(dir, { persistent: false }, onFsEvent))
    } catch { /* 受限环境（无 inotify 等）下退化为手动失效 */ }
  }

  // 目录 watch 不递归：根目录看 skill 增删，每个 skill 目录看 SKILL.md 改写。
  function syncWatchers() {
    const root = SKILL_DIRS[0]
    if (!existsSync(root)) return
    watchDir(root)
    let names = []
    try {
      names = readdirSync(root, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
    } catch { /* 读不到就下次再说 */ }
    for (const dir of [...watchers.keys()]) {
      if (dir !== root && !names.includes(basename(dir))) {
        try { watchers.get(dir).close() } catch { /* 已关闭 */ }
        watchers.delete(dir)
      }
    }
    for (const name of names) watchDir(join(root, name))
  }

  const startWatching = () => {
    if (!control || typeof control.invalidate !== 'function') return
    syncWatchers()
    control.signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      for (const watcher of watchers.values()) {
        try { watcher.close() } catch { /* 已关闭 */ }
      }
      watchers.clear()
    }, { once: true })
  }

  startWatching()

  return {
    name: PROVIDER,
    async list() {
      const skills = load()
      return { candidates: skills.map(candidate), complete: true }
    },
    async get(c) {
      const skills = load()
      let skill = skills.find((entry) => entry.name === c?.name && entry.dir === c?.locator)
      if (!skill && typeof c?.locator === 'string' && c.locator) {
        // 缓存失效后候选可能来自上一轮目录：按 locator 重新读一次。
        skill = existsSync(join(c.locator, 'SKILL.md')) ? readSkill(c.locator) : undefined
      }
      if (!skill) return undefined
      const body = skill.body
        .replaceAll('<SKILL_ROOT>', skill.dir)
        .replaceAll('<PLUGIN_ROOT>', PLUGIN_ROOT)
      const { rank, locator, ...summary } = candidate(skill)
      return { ...summary, content: body + addendum(skill) }
    },
  }
}
