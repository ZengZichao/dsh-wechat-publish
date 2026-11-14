// dsh-wechat-publish · Host 半边的服务层。
//
// 面板（client.js）不直接碰文件系统：它通过同源 HTTP 路由调用这里，
// 这里再用子进程驱动 skills/wechat-publish/scripts 下的 Python 脚本。
//
// 路由：
//   GET  /dsh-wechat-publish/api?action=status|settings|article|preview|job|drafts
//   POST /dsh-wechat-publish/api  { action: 'publish' | 'saveSettings', ... }
//   GET  /dsh-wechat-publish/image?path=<绝对路径>   预览用的本地图床
//
// 面板自己的偏好（体积上限、解释器固定、主题缓存时长）存在
// $DSH_HOME/dsh-wechat-publish/settings.json：这是插件自有数据，不是 profile
// 的 cordis.patch.yml，也不依赖插件 Config（本地 link 安装的插件无法解析
// profile 的 node_modules，因此本插件不 import 任何 npm 包）。
import { spawn } from 'node:child_process'
import { createReadStream, existsSync, readdirSync, readFileSync, realpathSync, statSync, writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(path.dirname(fileURLToPath(import.meta.url)))

export const PLUGIN_ROOT = HERE
export const SKILL_DIR = path.join(HERE, 'skills', 'wechat-publish')
export const PANEL_API = path.join(SKILL_DIR, 'scripts', 'panel_api.py')
export const PUBLISH_SH = path.join(SKILL_DIR, 'scripts', 'publish.sh')
export const IMAGE_ROUTE = '/dsh-wechat-publish/image'
export const API_ROUTE = '/dsh-wechat-publish/api'

const MAX_BODY_BYTES = 1024 * 1024
const MAX_IMAGE_BYTES = 20 * 1024 * 1024
const MAX_OUTPUT_CHARS = 200000
const PYTHON_TIMEOUT_MS = 240000
// 发布任务超时：图片多、网络慢时给足时间，但不能无限等
const PUBLISH_TIMEOUT_MS = 10 * 60 * 1000
const DEFAULT_MAX_CONTENT_BYTES = 512 * 1024
/** 面板可覆盖的文章字段，与 panel_api.py 的 --title/--author/... 一一对应。 */
const OVERRIDE_KEYS = new Set(['title', 'author', 'digest', 'cover', 'literature'])

const SETTING_LIMITS = {
  // 0 是「用默认值」的哨兵，其余取值必须落在真实区间内。
  maxContentBytes: { min: 65536, max: 8388608 },
  themeCacheHours: { min: 0, max: 720, def: 24 },
}

// --------------------------------------------------------------------------- #
// 面板偏好（$DSH_HOME/dsh-wechat-publish/settings.json）
// --------------------------------------------------------------------------- #
export function panelHome(dshHome) {
  const home = dshHome || process.env.DSH_HOME || path.join(process.env.HOME || '', '.dsh')
  return path.join(home, 'dsh-wechat-publish')
}

export function defaultPanelSettings() {
  return { maxContentBytes: 0, pythonBin: '', themeCacheHours: 24 }
}

export function readPanelSettings(dshHome) {
  const file = path.join(panelHome(dshHome), 'settings.json')
  const base = defaultPanelSettings()
  try {
    const raw = JSON.parse(readFileSync(file, 'utf8'))
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return base
    if (Number.isFinite(raw.maxContentBytes)) base.maxContentBytes = Math.trunc(raw.maxContentBytes)
    if (typeof raw.pythonBin === 'string') base.pythonBin = raw.pythonBin
    if (Number.isFinite(raw.themeCacheHours)) base.themeCacheHours = raw.themeCacheHours
    return base
  } catch {
    return base
  }
}

export function validatePanelSettings(next) {
  const fail = (message) => {
    const error = new Error(message)
    error.status = 400
    throw error
  }
  const merged = { ...defaultPanelSettings(), ...(next && typeof next === 'object' ? next : {}) }
  for (const [key, limit] of Object.entries(SETTING_LIMITS)) {
    const value = merged[key]
    if (!Number.isFinite(value)) fail(`${key} 必须是数字`)
    if (key === 'maxContentBytes' && value === 0) {
      // 0 = 使用默认上限，合法。
    } else if (value < limit.min || value > limit.max) {
      fail(`${key} 必须是 0 或 ${limit.min}–${limit.max} 之间`)
    }
    merged[key] = Math.trunc(value)
  }
  if (typeof merged.pythonBin !== 'string') fail('pythonBin 必须是字符串')
  merged.pythonBin = merged.pythonBin.trim()
  if (merged.pythonBin && !path.isAbsolute(merged.pythonBin)) {
    fail('pythonBin 必须是绝对路径')
  }
  return merged
}

export function writePanelSettings(dshHome, next) {
  const merged = validatePanelSettings(next)
  const dir = panelHome(dshHome)
  mkdirSync(dir, { recursive: true })
  writeFileSync(path.join(dir, 'settings.json'), JSON.stringify(merged, null, 2) + '\n', 'utf8')
  return merged
}

/** 在某个目录锚点上找 DSH 运行时 Python（桌面安装的 Resources 与解包运行时两种布局）。 */
function runtimePythonAt(base) {
  const layouts = [
    // 解包后的运行时目录：<base>/runtime/primary-runtime/...
    path.join(base, 'runtime', 'primary-runtime', 'dependencies', 'python', 'bin', 'python3'),
    // macOS 应用包：<base>/Contents/Resources/runtime/primary-runtime/...
    path.join(base, 'Contents', 'Resources', 'runtime', 'primary-runtime', 'dependencies', 'python', 'bin', 'python3'),
    // 直接是 Contents：<base>/Resources/runtime/primary-runtime/...
    path.join(base, 'Resources', 'runtime', 'primary-runtime', 'dependencies', 'python', 'bin', 'python3'),
  ]
  return layouts
}

/** DSH 0.2.x 自带的 Python（桌面安装的 primary-runtime payload 或 $DSH_HOME/dsh-runtimes）。 */
export function bundledPython(env = process.env) {
  const candidates = []
  if (env.DSH_PYTHON) candidates.push(env.DSH_PYTHON)
  if (env.DSH_RUNTIME_DIR) candidates.push(...runtimePythonAt(env.DSH_RUNTIME_DIR))
  // app-boot 会把运行时同步到 $DSH_HOME/dsh-runtimes，优先级低于显式配置。
  if (env.DSH_HOME || env.HOME) {
    const home = env.DSH_HOME || path.join(env.HOME, '.dsh')
    candidates.push(path.join(home, 'dsh-runtimes', 'dsh-primary-runtime', 'dependencies', 'python', 'bin', 'python3'))
  }
  // Electron 主进程可直接拿到 Resources 目录。
  const resources = env.DSH_RESOURCES_PATH || process.resourcesPath
  if (resources) candidates.push(...runtimePythonAt(resources))
  // 从当前 node/Electron 可执行文件逐级向上找安装包内的运行时。
  const exec = env.DSH_NODE_BIN || process.execPath
  if (exec) {
    let dir = path.dirname(exec)
    for (let i = 0; i < 8; i += 1) {
      candidates.push(...runtimePythonAt(dir))
      const parent = path.dirname(dir)
      if (parent === dir) break
      dir = parent
    }
  }
  for (const candidate of candidates) {
    try {
      if (candidate && existsSync(candidate)) return path.resolve(candidate)
    } catch { /* 忽略不可达候选 */ }
  }
  return undefined
}

/** 生效的解释器：环境变量优先，其次是面板固定值，然后是插件 venv、DSH 自带 Python、PATH。 */
export function effectivePython(settings, env = process.env) {
  if (env.GZH_PYTHON) return { bin: env.GZH_PYTHON, source: 'env' }
  if (settings.pythonBin) return { bin: settings.pythonBin, source: 'panel' }
  const venv = path.join(PLUGIN_ROOT, '.venv', 'bin', 'python')
  if (existsSync(venv)) return { bin: venv, source: 'venv' }
  const bundled = bundledPython(env)
  if (bundled) return { bin: bundled, source: 'bundled' }
  return { bin: 'python3', source: 'path' }
}

export function effectiveMaxContentBytes(settings, env = process.env) {
  const raw = env.WECHAT_MAX_CONTENT_BYTES
  if (raw) {
    const n = Number(raw)
    if (Number.isFinite(n) && n > 0) return { bytes: Math.trunc(n), source: 'env' }
  }
  if (settings.maxContentBytes) {
    return { bytes: settings.maxContentBytes, source: 'panel' }
  }
  return { bytes: DEFAULT_MAX_CONTENT_BYTES, source: 'default' }
}

// --------------------------------------------------------------------------- #
// 子进程
// --------------------------------------------------------------------------- #
function readJsonBody(request) {
  return new Promise((resolve, reject) => {
    let raw = ''
    request.setEncoding('utf8')
    request.on('data', (chunk) => {
      raw += chunk
      if (raw.length > MAX_BODY_BYTES) reject(new Error('request body too large'))
    })
    request.on('end', () => {
      if (!raw) return resolve({})
      try { resolve(JSON.parse(raw)) } catch { reject(new Error('invalid JSON')) }
    })
    request.on('error', reject)
  })
}

function sendJson(response, status, payload) {
  response.writeHead(status, {
    'cache-control': 'no-store',
    'content-type': 'application/json; charset=utf-8',
  })
  response.end(JSON.stringify(payload))
}

function sendText(response, status, body, headers = {}) {
  response.writeHead(status, { 'cache-control': 'no-store', ...headers })
  response.end(body)
}

/** 接受桌面文档源、真实同源请求或非浏览器调用方。 */
function isTrustedRequest(request) {
  const origin = request.headers ? request.headers.origin : undefined
  if (origin === undefined) return true
  if (origin === 'dsh-app://app') return true
  const host = request.headers ? request.headers.host : undefined
  if (host === undefined) return false
  try { return new URL(origin).host === host } catch { return false }
}

function tail(text, max = 4000) {
  if (!text) return ''
  return text.length > max ? `…\n${text.slice(-max)}` : text
}

/** 运行 panel_api.py 并解析 JSON 输出。 */
export function runPanelApi(args, { env = process.env, timeoutMs = PYTHON_TIMEOUT_MS } = {}) {
  const py = effectivePython(readPanelSettings(env.DSH_HOME), env).bin
  return new Promise((resolve) => {
    const child = spawn(py, [PANEL_API, ...args], { env, stdio: ['ignore', 'pipe', 'pipe'] })
    let stdout = ''
    let stderr = ''
    let settled = false
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      try { child.kill('SIGKILL') } catch { /* already gone */ }
      resolve({ code: null, stdout, stderr: `${stderr}\n[面板] 超时 ${timeoutMs / 1000}s`.trim() })
    }, timeoutMs)
    child.stdout.on('data', (chunk) => { stdout += chunk })
    child.stderr.on('data', (chunk) => { stderr += chunk })
    child.on('error', (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ code: null, stdout, stderr: `${stderr}\n${error.message}`.trim() })
    })
    child.on('close', (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ code, stdout, stderr })
    })
  })
}

export async function callPanelApi(args, options) {
  const { code, stdout, stderr } = await runPanelApi(args, options)
  const text = (stdout || '').trim()
  let payload = null
  if (text) {
    try { payload = JSON.parse(text) } catch { /* fall through */ }
  }
  if (code === 0 && payload && payload.ok) return payload
  const reason = payload && payload.error
    ? payload.error
    : `panel_api ${args[0]} 失败 (exit ${code})${tail(stderr || text)}`
  const error = new Error(reason)
  // Python 侧通过 payload.status 声明 HTTP 语义（如参数校验 400），否则按网关错误处理。
  error.status = Number.isInteger(payload && payload.status) ? payload.status : 502
  throw error
}

// --------------------------------------------------------------------------- //
// 发布任务
// --------------------------------------------------------------------------- //
export class PanelJobs {
  constructor({ env = process.env } = {}) {
    this.env = env
    this.seq = 0
    this.jobs = new Map()
    /** 本会话内已成功发布的路径 -> { mediaId, at }，用于重复草稿防护 */
    this.published = new Map()
  }

  /** 该路径最近一次成功发布的结果（没有则 null）。 */
  lastPublish(path) {
    return (path && this.published.get(path)) || null
  }

  start(label, args, { env = {}, runner = 'publishSh', timeoutMs = PUBLISH_TIMEOUT_MS } = {}) {
    const id = `job-${Date.now()}-${++this.seq}`
    const settings = readPanelSettings(this.env.DSH_HOME)
    const py = effectivePython(settings, this.env).bin
    const childEnv = {
      ...this.env,
      ...env,
      // 面板固定值只在环境变量没有显式给出时生效（环境变量永远优先）。
      ...(this.env.WECHAT_MAX_CONTENT_BYTES
        ? {}
        : settings.maxContentBytes
          ? { WECHAT_MAX_CONTENT_BYTES: String(settings.maxContentBytes) }
          : {}),
      ...(this.env.GZH_PYTHON || !settings.pythonBin ? {} : { GZH_PYTHON: settings.pythonBin }),
      PANEL_PYTHON: py,
    }
    // panelApi：面板自己的发布入口（归一化 + 兜底封面 + publish.py）
    const child = runner === 'panelApi'
      ? spawn(py, [PANEL_API, ...args], { env: childEnv, stdio: ['ignore', 'pipe', 'pipe'] })
      : spawn('bash', [PUBLISH_SH, ...args], { env: childEnv, stdio: ['ignore', 'pipe', 'pipe'] })
    const job = {
      id, label, status: 'running', exitCode: null, startedAt: Date.now(), finishedAt: null,
      output: '', timedOut: false, path: label === 'publish' ? args[1] : null, _child: child,
    }
    this.jobs.set(id, job)
    const push = (chunk) => {
      job.output = (job.output + chunk).slice(-MAX_OUTPUT_CHARS)
    }
    child.stdout.on('data', push)
    child.stderr.on('data', push)
    const timer = setTimeout(() => {
      job.timedOut = true
      try { child.kill('SIGKILL') } catch { /* already gone */ }
    }, timeoutMs)
    child.on('error', (error) => {
      push(`\n${error.message}`)
      job.status = 'failed'
      job.finishedAt = Date.now()
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      job.exitCode = code
      job.status = code === 0 ? 'succeeded' : 'failed'
      job.finishedAt = Date.now()
      job._child = null
      // 记录成功发布，供重复草稿防护使用
      if (label === 'publish' && job.status === 'succeeded' && job.path) {
        const match = /"mediaId"\s*:\s*"([^"]+)"/.exec(job.output)
        this.published.set(job.path, { mediaId: match ? match[1] : null, at: Date.now() })
      }
    })
    return this.view(id)
  }

  /** 取消运行中的任务；返回最新状态或 null。 */
  cancel(id) {
    const job = this.jobs.get(id)
    if (!job || job.status !== 'running') return null
    try { job._child && job._child.kill('SIGKILL') } catch { /* already gone */ }
    job.status = 'cancelled'
    job.finishedAt = Date.now()
    return this.view(id)
  }

  view(id) {
    const job = this.jobs.get(id)
    if (!job) return null
    const { _child, ...rest } = job
    return rest
  }

  list() {
    return [...this.jobs.values()].map(({ _child, ...rest }) => rest)
      .sort((a, b) => b.startedAt - a.startedAt)
  }

  dispose() {
    for (const job of this.jobs.values()) {
      if (job._child) { try { job._child.kill('SIGKILL') } catch { /* already gone */ } }
    }
    this.jobs.clear()
  }
}

// --------------------------------------------------------------------------- //
// 图片路由
// --------------------------------------------------------------------------- //
const IMAGE_MAGIC = [
  { bytes: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], type: 'image/png' },
  { bytes: [0xff, 0xd8, 0xff], type: 'image/jpeg' },
  { bytes: [0x47, 0x49, 0x46, 0x38, 0x37, 0x61], type: 'image/gif' },
  { bytes: [0x47, 0x49, 0x46, 0x38, 0x39, 0x61], type: 'image/gif' },
]

function sniffImage(head) {
  for (const magic of IMAGE_MAGIC) {
    if (head.length >= magic.bytes.length && magic.bytes.every((b, i) => head[i] === b)) {
      return magic.type
    }
  }
  // WebP: RIFF????WEBP
  if (head.length >= 12 && head[0] === 0x52 && head[1] === 0x49 && head[2] === 0x46 && head[3] === 0x46
    && head[8] === 0x57 && head[9] === 0x45 && head[10] === 0x42 && head[11] === 0x50) {
    return 'image/webp'
  }
  return null
}

function inside(root, candidate) {
  if (!root) return false
  const rel = path.relative(root, candidate)
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel))
}

/** 存在且是普通文件（目录不算）。 */
function isFile(target) {
  try { return statSync(target).isFile() } catch { return false }
}

/** 生成不冲突的目标路径：name 为空时用「未命名.md」「未命名 2.md」…。 */
function uniquePath(dir, name) {
  const base = name ? (name.endsWith('.md') ? name : `${name}.md`) : '未命名.md'
  if (!/^[^\\/:*?"<>|]+$/.test(base)) return null
  let candidate = path.join(dir, base)
  if (!existsSync(candidate)) return candidate
  if (name) return null // 显式命名时重名直接报错
  const stem = '未命名'
  for (let index = 2; index < 1000; index += 1) {
    candidate = path.join(dir, `${stem} ${index}.md`)
    if (!existsSync(candidate)) return candidate
  }
  return null
}

// --------------------------------------------------------------------------- #
// 最近使用
// --------------------------------------------------------------------------- #
const RECENT_MAX = 12

function recentFile(dshHome) {
  return path.join(panelHome(dshHome), 'recent.json')
}

export function readRecent(dshHome) {
  try {
    const raw = JSON.parse(readFileSync(recentFile(dshHome), 'utf8'))
    // 剪枝：路径已经不存在的不再展示，避免点了就报错
    const alive = Array.isArray(raw)
      ? raw.filter((x) => typeof x === 'string' && existsSync(x))
      : []
    return alive.slice(0, RECENT_MAX)
  } catch { /* 尚未使用过时不存在 */ }
  return []
}

export function rememberRecent(dshHome, target) {
  if (typeof target !== 'string' || !target) return readRecent(dshHome)
  const list = [target, ...readRecent(dshHome).filter((x) => x !== target)].slice(0, RECENT_MAX)
  try {
    mkdirSync(panelHome(dshHome), { recursive: true })
    writeFileSync(recentFile(dshHome), JSON.stringify(list, null, 2) + '\n', 'utf8')
  } catch { /* 写不进去不影响主流程 */ }
  return list
}

// --------------------------------------------------------------------------- #
// 目录树
// --------------------------------------------------------------------------- #
const TREE_MAX_ENTRIES = 2000
const MARKDOWN_EXTENSIONS = new Set(['.md', '.markdown', '.mdown', '.mkd', '.mdx'])

function isMarkdownName(name) {
  return MARKDOWN_EXTENSIONS.has(path.extname(name).toLowerCase())
}

/** 列出一层目录。隐藏文件（`.` 开头）默认跳过。 */
export function listTree(dir, { showHidden = false } = {}) {
  const real = realpathSync(dir)
  const entries = readdirSync(real, { withFileTypes: true })
  const rows = []
  for (const entry of entries) {
    if (!showHidden && entry.name.startsWith('.')) continue
    const full = path.join(real, entry.name)
    let stat = null
    try { stat = statSync(full) } catch { /* 符号链接悬空等 */ }
    const isDir = entry.isDirectory()
    rows.push({
      name: entry.name,
      path: full,
      kind: isDir ? 'directory' : 'file',
      ext: isDir ? '' : path.extname(entry.name).toLowerCase(),
      markdown: !isDir && isMarkdownName(entry.name),
      size: stat && !isDir ? stat.size : 0,
      mtimeMs: stat ? stat.mtimeMs : 0,
    })
  }
  rows.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name, 'zh-Hans-CN') : a.kind === 'directory' ? -1 : 1))
  return {
    path: real,
    parent: path.dirname(real) === real ? null : path.dirname(real),
    truncated: rows.length > TREE_MAX_ENTRIES,
    entries: rows.slice(0, TREE_MAX_ENTRIES),
  }
}

// --------------------------------------------------------------------------- //
// 路由
// --------------------------------------------------------------------------- //
export function createPanelRoutes({ dshHome, jobs, extraRoots = [] }) {
  // treeDir：用户在文件树里浏览过的目录。列目录本身不做根限制（只枚举名字），
  // 但把它记进 roots，之后打开这里的 md / 图片就顺理成章。
  const state = { articleDir: null, treeDir: null }
  const roots = () => [
    PLUGIN_ROOT,
    ...(state.articleDir ? [state.articleDir] : []),
    ...(state.treeDir ? [state.treeDir] : []),
    ...extraRoots,
  ].filter(Boolean)

  /**
   * 解析并校验一个路径必须落在允许的根目录内。
   * allowMissing=true 时返回 null（目录树会优雅处理不存在的路径）。
   */
  const resolveWithinRoots = (raw, { allowMissing = false } = {}) => {
    if (!raw) throw Object.assign(new Error('path is required'), { status: 400 })
    const candidate = path.normalize(raw)
    if (!path.isAbsolute(candidate)) {
      throw Object.assign(new Error('只接受绝对路径'), { status: 400 })
    }
    let real
    try { real = realpathSync(candidate) } catch {
      if (allowMissing) return null
      return null
    }
    let allowed = false
    try {
      allowed = roots().some((root) => {
        let realRoot
        try { realRoot = realpathSync(root) } catch { realRoot = path.resolve(root) }
        return inside(realRoot, real)
      })
    } catch { allowed = false }
    if (!allowed) throw Object.assign(new Error('路径不在允许的范围内'), { status: 403 })
    return real
  }

  const resolveImage = (raw) => resolveWithinRoots(raw)

  const handleImage = async (request, response) => {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return sendJson(response, 405, { ok: false, error: 'method not allowed' })
    }
    if (!isTrustedRequest(request)) {
      return sendJson(response, 403, { ok: false, error: 'untrusted origin' })
    }
    const query = new URL(request.url, 'http://localhost').searchParams
    let file
    try {
      file = resolveImage(query.get('path'))
    } catch (error) {
      return sendJson(response, error.status || 400, { ok: false, error: error.message })
    }
    if (!file) return sendJson(response, 404, { ok: false, error: 'image not found' })
    let stat
    try { stat = statSync(file) } catch { return sendJson(response, 404, { ok: false, error: 'image not found' }) }
    if (!stat.isFile() || stat.size > MAX_IMAGE_BYTES) {
      return sendJson(response, 413, { ok: false, error: 'image too large' })
    }
    // 校验魔数：避免把 HTML/JSON 错误页当图片返回（规则 R10）。
    let head = Buffer.alloc(0)
    try {
      const { openSync, readSync, closeSync } = await import('node:fs')
      const fd = openSync(file, 'r')
      try {
        head = Buffer.alloc(12)
        readSync(fd, head, 0, 12, 0)
      } finally { closeSync(fd) }
    } catch { /* fall through: let the sniff fail */ }
    const type = sniffImage(head)
    if (!type) return sendJson(response, 415, { ok: false, error: 'not an image' })
    response.writeHead(200, {
      'content-type': type,
      'content-length': stat.size,
      'cache-control': 'no-store',
    })
    if (request.method === 'HEAD') return response.end()
    return new Promise((resolve) => {
      const stream = createReadStream(file)
      stream.on('data', (chunk) => { try { response.write(chunk) } catch { /* 连接已断开 */ } })
      stream.on('end', () => { try { response.end() } catch { /* 已结束 */ }; resolve() })
      stream.on('error', () => { try { response.end() } catch { /* 已结束 */ }; resolve() })
    })
  }

  const handleApi = async (request, response) => {
    if (!isTrustedRequest(request)) {
      return sendJson(response, 403, { ok: false, error: 'untrusted origin' })
    }
    const query = new URL(request.url, 'http://localhost').searchParams
    const settings = readPanelSettings(dshHome)
    const env = process.env

    if (request.method === 'GET') {
      const action = query.get('action') || 'status'
      try {
        switch (action) {
          case 'status':
            return sendJson(response, 200, await callPanelApi(['status'], { env }))
          case 'drafts':
            return sendJson(response, 200, await callPanelApi(['drafts'], { env }))
          case 'job': {
            const job = jobs.view(query.get('id') || '')
            if (!job) return sendJson(response, 404, { ok: false, error: 'job not found' })
            return sendJson(response, 200, { ok: true, job })
          }
          case 'cancelJob': {
            const job = jobs.cancel(query.get('id') || '')
            if (!job) return sendJson(response, 404, { ok: false, error: 'job not found or not running' })
            return sendJson(response, 200, { ok: true, job })
          }
          case 'lastPublish': {
            const target = query.get('path') || ''
            return sendJson(response, 200, {
              ok: true,
              last: target ? jobs.lastPublish(path.resolve(target)) : null,
            })
          }
          case 'jobs':
            return sendJson(response, 200, { ok: true, jobs: jobs.list() })
          case 'roots':
            return sendJson(response, 200, {
              ok: true,
              roots: roots(),
              default: roots().find((root) => root !== PLUGIN_ROOT) || roots()[0],
              home: homedir(),
            })
          case 'tree': {
            const requested = query.get('path') || roots().find((root) => root !== PLUGIN_ROOT) || roots()[0]
            if (!path.isAbsolute(requested)) {
              return sendJson(response, 400, { ok: false, error: '只接受绝对路径' })
            }
            let dir
            try { dir = realpathSync(requested) } catch { return sendJson(response, 404, { ok: false, error: '目录不存在' }) }
            if (!statSync(dir).isDirectory()) return sendJson(response, 400, { ok: false, error: '不是目录' })
            state.treeDir = dir
            return sendJson(response, 200, {
              ok: true,
              ...listTree(dir, { showHidden: query.get('hidden') === '1' }),
            })
          }
          case 'recent':
            return sendJson(response, 200, { ok: true, recent: readRecent(dshHome) })
          case 'body': {
            const target = query.get('path') || ''
            if (!target) return sendJson(response, 400, { ok: false, error: 'path is required' })
            if (!path.isAbsolute(target)) return sendJson(response, 400, { ok: false, error: '只接受绝对路径' })
            if (!isFile(target)) return sendJson(response, 404, { ok: false, error: '文件不存在' })
            return sendJson(response, 200, await callPanelApi(['body', target], { env }))
          }
          case 'createFile': {
            const dir = query.get('dir') || ''
            const name = (query.get('name') || '').trim()
            if (!dir) return sendJson(response, 400, { ok: false, error: 'dir 必填' })
            if (name && !/^[^\/:*?"<>|]+$/.test(name)) {
              return sendJson(response, 400, { ok: false, error: '文件名含非法字符' })
            }
            let realDir
            try { realDir = resolveWithinRoots(dir) } catch (error) {
              return sendJson(response, error.status || 400, { ok: false, error: error.message })
            }
            if (!realDir) return sendJson(response, 404, { ok: false, error: '目录不存在' })
            // 不弹文件名输入框：自动生成「未命名.md」「未命名 2.md」…
            const target = uniquePath(realDir, name)
            if (!target) return sendJson(response, 400, { ok: false, error: '文件名含非法字符' })
            writeFileSync(target, '---\ntitle: 未命名文章\n---\n\n# 未命名文章\n\n', 'utf8')
            state.treeDir = realDir
            return sendJson(response, 200, { ok: true, path: target })
          }
          case 'verify': {
            const target = query.get('path') || ''
            const mediaId = query.get('mediaId') || ''
            if (!target) return sendJson(response, 400, { ok: false, error: 'path is required' })
            if (!mediaId) return sendJson(response, 400, { ok: false, error: 'mediaId is required' })
            if (!path.isAbsolute(target)) return sendJson(response, 400, { ok: false, error: '只接受绝对路径' })
            if (!isFile(target)) return sendJson(response, 404, { ok: false, error: '文件不存在' })
            const args = ['verify', mediaId, target]
            for (const [key, value] of query.entries()) {
              if (OVERRIDE_KEYS.has(key) && value) args.push(`--${key}`, value)
            }
            return sendJson(response, 200, await callPanelApi(args, { env }))
          }
          case 'article':
          case 'preview': {
            const target = query.get('path') || ''
            if (!target) return sendJson(response, 400, { ok: false, error: 'path is required' })
            if (!path.isAbsolute(target)) return sendJson(response, 400, { ok: false, error: '只接受绝对路径' })
            if (!isFile(target)) return sendJson(response, 404, { ok: false, error: '文件不存在' })
            const args = action === 'preview'
              ? ['preview', target, '--theme-cache-hours', String(settings.themeCacheHours)]
              : ['article', target, '--no-body']
            // 内容覆盖字段：让面板可以在不改源文件的前提下预览任意 md
            for (const [key, value] of query.entries()) {
              if (OVERRIDE_KEYS.has(key) && value) args.push(`--${key}`, value)
            }
            const payload = await callPanelApi(args, { env })
            if (payload.ok) {
              state.articleDir = path.dirname(path.resolve(target))
              if (action === 'preview') rememberRecent(dshHome, path.resolve(target))
            }
            return sendJson(response, 200, payload)
          }
          case 'settings': {
            const payload = await callPanelApi(['settings'], { env })
            if (!payload.ok) return sendJson(response, 200, payload)
            const max = effectiveMaxContentBytes(settings, env)
            const py = effectivePython(settings, env)
            for (const group of payload.groups) {
              for (const item of group.items) {
                if (item.id === 'maxContentBytes') {
                  item.value = max.source === 'default'
                    ? `${max.bytes}（默认）`
                    : `${max.bytes}（${max.source === 'env' ? '环境变量' : '面板设置'}）`
                  item.source = max.source
                }
                if (item.id === 'pythonBin') {
                  item.value = py.bin
                  item.source = py.source
                }
                if (item.id === 'themeCache') {
                  item.value = `${settings.themeCacheHours} 小时`
                  item.source = 'panel'
                }
              }
            }
            payload.panelSettings = settings
            payload.effective = {
              maxContentBytes: max.bytes,
              pythonBin: py.bin,
              pythonSource: py.source,
              themeCacheHours: settings.themeCacheHours,
            }
            return sendJson(response, 200, payload)
          }
          default:
            return sendJson(response, 400, { ok: false, error: `unknown action: ${action}` })
        }
      } catch (error) {
        return sendJson(response, error.status || 502, {
          ok: false, error: String(error.message || error),
        })
      }
    }

    if (request.method !== 'POST') {
      return sendJson(response, 405, { ok: false, error: 'method not allowed' })
    }

    let body
    try { body = await readJsonBody(request) } catch (error) {
      return sendJson(response, 400, { ok: false, error: error.message })
    }
    const action = body && body.action

    try {
      if (action === 'publish') {
        const target = body.path
        if (!target || !path.isAbsolute(target)) {
          return sendJson(response, 400, { ok: false, error: 'path 必须是绝对路径' })
        }
        if (!isFile(target)) return sendJson(response, 404, { ok: false, error: '文件不存在' })
        // 重复草稿防护：本会话内同一文件已发布成功过，先拦下来让用户确认
        const previous = jobs.lastPublish(path.resolve(target))
        if (previous && !body.allowDuplicate) {
          return sendJson(response, 409, {
            ok: false,
            code: 'duplicate_draft',
            error: `这篇文件在本次会话里已经发布过（media_id: ${previous.mediaId || '未知'}）。`
              + '确认要再建一篇重复草稿的话，勾选「仍然重复发布」后重试。',
            mediaId: previous.mediaId,
          })
        }
        // 归一化 + 兜底封面都在 panel_api.py 内完成，因此这里直接跑 panel_api publish
        const args = ['publish', target]
        for (const key of OVERRIDE_KEYS) {
          if (body[key] !== undefined && body[key] !== null && String(body[key]).trim()) {
            args.push(`--${key}`, String(body[key]))
          }
        }
        state.articleDir = path.dirname(path.resolve(target))
        rememberRecent(dshHome, path.resolve(target))
        const job = jobs.start('publish', args, { runner: 'panelApi' })
        return sendJson(response, 200, { ok: true, job })
      }
      if (action === 'saveFrontmatter') {
        const target = body.path
        if (!target || !path.isAbsolute(target)) {
          return sendJson(response, 400, { ok: false, error: 'path 必须是绝对路径' })
        }
        if (!isFile(target)) return sendJson(response, 404, { ok: false, error: '文件不存在' })
        const args = ['saveFrontmatter', target]
        for (const key of OVERRIDE_KEYS) {
          if (body[key] !== undefined && body[key] !== null && String(body[key]).trim()) {
            args.push(`--${key}`, String(body[key]))
          }
        }
        try {
          const payload = await callPanelApi(args, { env })
          return sendJson(response, 200, payload)
        } catch (error) {
          return sendJson(response, error.status || 500, {
            ok: false, error: String(error.message || error),
          })
        }
      }
      if (action === 'saveBody') {
        const target = body.path
        if (!target || !path.isAbsolute(target)) {
          return sendJson(response, 400, { ok: false, error: 'path 必须是绝对路径' })
        }
        if (!isFile(target)) return sendJson(response, 404, { ok: false, error: '文件不存在' })
        if (typeof body.body !== 'string') {
          return sendJson(response, 400, { ok: false, error: 'body 必须是字符串' })
        }
        const tmp = path.join(tmpdir(), `wxpanel-body-${process.pid}-${Date.now()}.md`)
        writeFileSync(tmp, body.body, 'utf8')
        try {
          const payload = await callPanelApi(['saveBody', target, '--body-file', tmp], { env })
          return sendJson(response, 200, payload)
        } catch (error) {
          return sendJson(response, error.status || 500, {
            ok: false, error: String(error.message || error),
          })
        } finally {
          try { rmSync(tmp, { force: true }) } catch { /* 已删 */ }
        }
      }
      if (action === 'saveSettings') {
        const saved = writePanelSettings(dshHome, body.settings)
        return sendJson(response, 200, { ok: true, settings: saved })
      }
      if (action === 'remember') {
        return sendJson(response, 200, { ok: true, recent: rememberRecent(dshHome, body.path) })
      }
      return sendJson(response, 400, { ok: false, error: `unknown action: ${action}` })
    } catch (error) {
      return sendJson(response, error.status || 500, {
        ok: false, error: String(error.message || error),
      })
    }
  }

  return [
    { kind: 'exact', path: API_ROUTE, handler: (req, res) => handleApi(req, res) },
    { kind: 'exact', path: IMAGE_ROUTE, handler: (req, res) => handleImage(req, res) },
  ]
}
