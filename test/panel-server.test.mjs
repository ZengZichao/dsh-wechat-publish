// Panel Host 路由的端到端测试：用 mock 的 webServer / req / res 直接驱动
// lib/server.js 的处理器，验证 status / settings / article / preview / publish /
// saveSettings / image 六条路径。
//
// 运行：node test/panel-server.test.mjs
// 需要插件 venv 里的 Python（preview 会真实渲染并抓取主题 CSS）。
import assert from 'node:assert/strict'
import { Readable } from 'node:stream'
import { mkdtempSync, writeFileSync, rmSync, existsSync, mkdirSync, readFileSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import {
  createPanelRoutes,
  readPanelSettings,
  validatePanelSettings,
  effectivePython,
  effectiveMaxContentBytes,
  writePanelSettings,
  panelHome,
  PanelJobs,
} from '../lib/server.js'

const DSH_HOME = mkdtempSync(path.join(tmpdir(), 'wxpanel-test-'))
const FIXTURE = path.resolve('test/fixtures/article.md')

function mockReq({ method = 'GET', url, body, headers = {} }) {
  const req = new Readable({ read() {} })
  req.method = method
  req.url = url
  req.headers = { host: 'localhost', ...headers }
  if (body !== undefined) req.push(JSON.stringify(body))
  req.push(null)
  return req
}

function mockRes() {
  const res = {
    statusCode: 200,
    headers: {},
    chunks: [],
    raw: Buffer.alloc(0),
    body: '',
    writeHead(code, headers) { this.statusCode = code; this.headers = headers || {}; return this },
    setHeader(name, value) { this.headers[name] = value },
    write(chunk) {
      this.chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)))
      return true
    },
    end(chunk) {
      if (chunk != null) this.chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)))
      this.raw = Buffer.concat(this.chunks)
      this.body = this.raw.toString('utf8')
      return this
    },
  }
  return res
}

async function call(route, options) {
  const res = mockRes()
  await route.handler(mockReq(options), res)
  let payload = null
  try { payload = JSON.parse(res.body) } catch { payload = res.body }
  return { status: res.statusCode, headers: res.headers, body: res.body, raw: res.raw, payload }
}

function buildRoutes() {
  const jobs = new PanelJobs({ env: { ...process.env, DSH_HOME } })
  const routes = createPanelRoutes({ dshHome: DSH_HOME, jobs, extraRoots: [tmpdir()] })
  const byPath = Object.fromEntries(routes.map((r) => [r.path, r]))
  return { jobs, byPath }
}

// ---------------------------------------------------------------- settings ----
assert.deepEqual(readPanelSettings(DSH_HOME), { maxContentBytes: 0, pythonBin: '', themeCacheHours: 24 })

assert.throws(() => validatePanelSettings({ maxContentBytes: 10 }), /maxContentBytes/)
assert.throws(() => validatePanelSettings({ pythonBin: 'relative/path' }), /绝对路径/)
assert.deepEqual(
  validatePanelSettings({ maxContentBytes: 1048576, pythonBin: '/usr/bin/python3', themeCacheHours: 0 }),
  { maxContentBytes: 1048576, pythonBin: '/usr/bin/python3', themeCacheHours: 0 },
)

const saved = writePanelSettings(DSH_HOME, { maxContentBytes: 1048576 })
assert.equal(saved.maxContentBytes, 1048576)
assert.equal(readPanelSettings(DSH_HOME).maxContentBytes, 1048576)
assert.ok(existsSync(path.join(panelHome(DSH_HOME), 'settings.json')))

assert.deepEqual(
  effectiveMaxContentBytes({ maxContentBytes: 0 }, {}),
  { bytes: 524288, source: 'default' },
)
assert.deepEqual(
  effectiveMaxContentBytes({ maxContentBytes: 777 }, { WECHAT_MAX_CONTENT_BYTES: '999' }),
  { bytes: 999, source: 'env' },
)
assert.equal(effectivePython({ pythonBin: '/x/python' }, {}).bin, '/x/python')
assert.equal(effectivePython({ pythonBin: '' }, { GZH_PYTHON: '/env/python' }).bin, '/env/python')

// -------------------------------------------------------------------- api ----
const { jobs, byPath } = buildRoutes()
const api = byPath['/dsh-wechat-publish/api']
const image = byPath['/dsh-wechat-publish/image']
assert.ok(api && image, '两条路由都已注册')

// status
{
  const { status, payload } = await call(api, { url: '/dsh-wechat-publish/api?action=status' })
  assert.equal(status, 200)
  assert.equal(payload.ok, true)
  assert.equal(payload.ok, true)
  assert.ok(payload.python.deps.markdown, 'markdown 依赖可见')
  assert.equal(typeof payload.credentials.appIdSet, 'boolean')
}

// article
{
  const { status, payload } = await call(api, { url: `/dsh-wechat-publish/api?action=article&path=${encodeURIComponent(FIXTURE)}` })
  assert.equal(status, 200)
  assert.equal(payload.ok, true)
  assert.equal(payload.meta.title, '插件自测文章')
  assert.equal(payload.formulaCount, 2)
  // 归一化属于面板内部动作，不再往界面上堆提示
  assert.ok(!payload.warnings.some((w) => w.includes('cover')), 'cover 缺失不再提示')
  assert.ok(!payload.warnings.some((w) => w.includes('frontmatter')), 'frontmatter 缺失不再提示')
  assert.ok(!payload.warnings.some((w) => w.includes('归一化')), '归一化副本不再提示')
}

// article: 相对路径被拒
{
  const { status } = await call(api, { url: '/dsh-wechat-publish/api?action=article&path=relative.md' })
  assert.equal(status, 400)
}

// preview: 渲染成功且图片 src 被改写为面板路由
{
  const { status, payload } = await call(api, { url: `/dsh-wechat-publish/api?action=preview&path=${encodeURIComponent(FIXTURE)}` })
  assert.equal(status, 200)
  assert.equal(payload.ok, true, payload.error)
  assert.ok(payload.html.startsWith('<section'), '预览返回 section 片段')
  assert.equal(payload.stats.svg, 2)
  assert.equal(payload.stats.mathFallback, 0)
  assert.equal(payload.stats.styleResidue, 0)
}

// preview: 带图文章的图片改写
{
  const dir = mkdtempSync(path.join(tmpdir(), 'wxpanel-img-'))
  // 1x1 PNG
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64',
  )
  const imgPath = path.join(dir, 'fig1.png')
  writeFileSync(imgPath, png)
  const md = path.join(dir, 'article.md')
  writeFileSync(md, `---\ntitle: 图片自测\ncover: ${imgPath}\n---\n\n## 摘要\n\n![图1](${imgPath})\n`)
  const { payload } = await call(api, { url: `/dsh-wechat-publish/api?action=preview&path=${encodeURIComponent(md)}` })
  assert.equal(payload.ok, true, payload.error)
  assert.equal(payload.images.length, 1)
  assert.equal(payload.images[0].exists, true)
  assert.ok(payload.html.includes('/dsh-wechat-publish/image?path='), '图片已改写为面板路由')

  const encoded = encodeURIComponent(imgPath)
  const got = await call(image, { url: `/dsh-wechat-publish/image?path=${encoded}` })
  assert.equal(got.status, 200)
  assert.equal(got.headers['content-type'], 'image/png')
  assert.deepEqual([...got.raw.slice(0, 8)], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
}

// image: 越界路径被拒
{
  const { status } = await call(image, { url: `/dsh-wechat-publish/image?path=${encodeURIComponent('/etc/hosts')}` })
  assert.equal(status, 403)
}

// settings: 合并面板偏好与生效值
{
  const { status, payload } = await call(api, { url: '/dsh-wechat-publish/api?action=settings' })
  assert.equal(status, 200)
  assert.equal(payload.ok, true, payload.error)
  assert.equal(payload.effective.maxContentBytes, 1048576)
  const item = payload.groups.flatMap((g) => g.items).find((i) => i.id === 'maxContentBytes')
  assert.equal(item.source, 'panel')
  assert.ok(payload.groups.some((g) => g.id === 'translate'), '翻译设置组存在')
  assert.ok(payload.groups.some((g) => g.id === 'render'), '渲染设置组存在')
}

// saveSettings: 校验并落盘
{
  const bad = await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'saveSettings', settings: { maxContentBytes: 5 } },
  })
  assert.equal(bad.status, 400)

  const good = await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'saveSettings', settings: { maxContentBytes: 2097152, themeCacheHours: 12 } },
  })
  assert.equal(good.status, 200)
  assert.equal(good.payload.settings.maxContentBytes, 2097152)
  assert.equal(readPanelSettings(DSH_HOME).themeCacheHours, 12)
}

// publish: 只在参数校验层验证，不真的发布（会往草稿箱写草稿）
{
  const relative = await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'publish', path: 'relative.md' },
  })
  assert.equal(relative.status, 400)

  const missing = await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'publish', path: '/nonexistent/article.md' },
  })
  assert.equal(missing.status, 404)
}

// -------------------------------------------------------------------- tree ----
const treeDir = mkdtempSync(path.join(tmpdir(), 'wxpanel-tree-'))
writeFileSync(path.join(treeDir, 'a.md'), '# A\n')
writeFileSync(path.join(treeDir, 'b.txt'), 'plain\n')
writeFileSync(path.join(treeDir, '.hidden.md'), '# hidden\n')
mkdirSync(path.join(treeDir, 'sub'))
writeFileSync(path.join(treeDir, 'sub', 'c.markdown'), '# C\n')

// 写回 frontmatter 只对临时副本做，绝不改仓库里的夹具。
// 放在 tree 断言之后，避免 editable.md 混进目录树的期望列表。
{
  const { status, payload } = await call(api, {
    url: `/dsh-wechat-publish/api?action=tree&path=${encodeURIComponent(treeDir)}`,
  })
  assert.equal(status, 200)
  assert.equal(payload.ok, true, payload.error)
  assert.equal(payload.path, realpathSync(treeDir))
  assert.equal(payload.parent, path.dirname(realpathSync(treeDir)))
  // 目录在前，隐藏文件被跳过
  assert.deepEqual(payload.entries.map((e) => e.name), ['sub', 'a.md', 'b.txt'])
  assert.equal(payload.entries.find((e) => e.name === 'a.md').markdown, true)
  assert.equal(payload.entries.find((e) => e.name === 'b.txt').markdown, false)

  const hidden = await call(api, {
    url: `/dsh-wechat-publish/api?action=tree&path=${encodeURIComponent(treeDir)}&hidden=1`,
  })
  assert.ok(hidden.payload.entries.some((e) => e.name === '.hidden.md'))

  const missing = await call(api, {
    url: '/dsh-wechat-publish/api?action=tree&path=%2Fnonexistent-dir-xyz',
  })
  assert.equal(missing.status, 404)

  // 列目录本身不限根（只枚举名字），并会记为允许读取的根
  const etc = await call(api, { url: '/dsh-wechat-publish/api?action=tree&path=%2Fetc' })
  assert.equal(etc.status, 200)
  assert.ok(Array.isArray(etc.payload.entries))
  const rootsAfter = await call(api, { url: '/dsh-wechat-publish/api?action=roots' })
  assert.ok(rootsAfter.payload.roots.includes(realpathSync('/etc')))
}

// 写回 frontmatter 只对临时副本做，绝不改仓库里的夹具。
// 放在 tree 断言之后，避免 editable.md 混进目录树的期望列表。
{
  const editable = path.join(treeDir, 'editable.md')
  writeFileSync(editable, '# 原文标题\n\n正文。\n')
  const save = await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'saveFrontmatter', path: editable, title: '面板改的标题', digest: '摘要' },
  })
  assert.equal(save.status, 200)
  assert.equal(save.payload.ok, true, save.payload.error)
  assert.match(readFileSync(editable, 'utf8'), /^---\ntitle: 面板改的标题\ndigest: 摘要\n---\n\n# 原文标题/)
  assert.ok(existsSync(`${editable}.wxpanel.bak`), '写回应留备份')

  const empty = await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'saveFrontmatter', path: editable },
  })
  assert.equal(empty.status, 400, '空字段应被拒绝')
}

// ------------------------------------------------------------------ recent ----
// 预览会顺带记住路径；已不存在的路径会被剪枝，所以用真实文件做断言
{
  const r1 = path.join(treeDir, 'r1.md')
  const r2 = path.join(treeDir, 'r2.md')
  writeFileSync(r1, '# r1\n')
  writeFileSync(r2, '# r2\n')

  // 先记一个不存在的路径，确认被剪枝
  await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'remember', path: '/tmp/definitely-dead-xyz.md' },
  })
  const pruned = await call(api, { url: '/dsh-wechat-publish/api?action=recent' })
  assert.ok(!pruned.payload.recent.includes('/tmp/definitely-dead-xyz.md'), '死路径应被剪枝')

  await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'remember', path: r1 },
  })
  await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'remember', path: r2 },
  })
  const list = await call(api, { url: '/dsh-wechat-publish/api?action=recent' })
  assert.equal(list.payload.recent[0], r2)
  assert.ok(list.payload.recent.includes(r1))
  assert.equal(new Set(list.payload.recent).size, list.payload.recent.length, '不应有重复')
  assert.ok(list.payload.recent.length <= 12)

  await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'remember', path: r2 },
  })
  const again = await call(api, { url: '/dsh-wechat-publish/api?action=recent' })
  assert.equal(again.payload.recent[0], r2)
  assert.equal(again.payload.recent.filter((x) => x === r2).length, 1, '重复路径应去重')
}

// --------------------------------------------------------- 新建 / 正文读写 ----
{
  const created = await call(api, {
    url: `/dsh-wechat-publish/api?action=createFile&dir=${encodeURIComponent(treeDir)}&name=new-note`,
  })
  assert.equal(created.status, 200)
  assert.equal(created.payload.ok, true, created.payload.error)
  const createdPath = created.payload.path
  assert.match(createdPath, /new-note\.md$/)
  const content = readFileSync(createdPath, 'utf8')
  assert.match(content, /^---\ntitle: /)

  // 显式命名时重名应被拒绝
  const dup = await call(api, {
    url: `/dsh-wechat-publish/api?action=createFile&dir=${encodeURIComponent(treeDir)}&name=new-note`,
  })
  assert.equal(dup.status, 400)

  // 不传文件名时自动生成不冲突的名字
  const auto1 = await call(api, {
    url: `/dsh-wechat-publish/api?action=createFile&dir=${encodeURIComponent(treeDir)}`,
  })
  assert.equal(auto1.status, 200, auto1.payload.error)
  assert.match(auto1.payload.path, /未命名\.md$/)
  const auto2 = await call(api, {
    url: `/dsh-wechat-publish/api?action=createFile&dir=${encodeURIComponent(treeDir)}`,
  })
  assert.equal(auto2.status, 200, auto2.payload.error)
  assert.match(auto2.payload.path, /未命名 2\.md$/)
  assert.notEqual(auto1.payload.path, auto2.payload.path)

  // 非法文件名
  const bad = await call(api, {
    url: `/dsh-wechat-publish/api?action=createFile&dir=${encodeURIComponent(treeDir)}&name=a%2Fb`,
  })
  assert.equal(bad.status, 400)

  // 按需拉正文
  const bodyPayload = await call(api, { url: `/dsh-wechat-publish/api?action=body&path=${encodeURIComponent(createdPath)}` })
  assert.equal(bodyPayload.status, 200)
  assert.equal(bodyPayload.payload.ok, true, bodyPayload.error)
  assert.equal(bodyPayload.payload.body, content.split(/^---$[\s\S]*?^---$/m).pop().trimStart())

  // 只改正文，frontmatter 不变
  const saveBody = await call(api, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'saveBody', path: createdPath, body: '# 新正文\n\n内容。\n' },
  })
  assert.equal(saveBody.status, 200)
  assert.equal(saveBody.payload.ok, true, saveBody.payload.error)
  const after = readFileSync(createdPath, 'utf8')
  assert.match(after, /^---\ntitle: /)
  assert.match(after, /# 新正文/)
  assert.ok(existsSync(`${createdPath}.wxpanel.bak`), '写回应留备份')

  // article 默认不再返回正文
  const articlePayload = await call(api, { url: `/dsh-wechat-publish/api?action=article&path=${encodeURIComponent(createdPath)}` })
  assert.equal(articlePayload.status, 200)
  assert.equal(articlePayload.payload.body, undefined, 'article 默认不应返回正文')
}

// ------------------------------------------------------- 重复草稿防护 ----
{
  // 预先把夹具标记为「本会话已发布过」，验证第二次发布会被拦下（不真的发布）
  const seeded = new PanelJobs({ env: { ...process.env, DSH_HOME } })
  seeded.published.set(path.resolve(FIXTURE), { mediaId: 'prev-media-id', at: Date.now() })
  const routes = createPanelRoutes({ dshHome: DSH_HOME, jobs: seeded, extraRoots: [tmpdir()] })
  const seededApi = routes.find((r) => r.path === '/dsh-wechat-publish/api')

  const probe = await call(seededApi, { url: `/dsh-wechat-publish/api?action=lastPublish&path=${encodeURIComponent(FIXTURE)}` })
  assert.equal(probe.payload.last.mediaId, 'prev-media-id')

  const blocked = await call(seededApi, {
    method: 'POST', url: '/dsh-wechat-publish/api',
    body: { action: 'publish', path: FIXTURE },
  })
  assert.equal(blocked.status, 409, '重复发布应被拦下')
  assert.equal(blocked.payload.code, 'duplicate_draft')
  assert.equal(blocked.payload.mediaId, 'prev-media-id')
  assert.match(blocked.payload.error, /已经发布过/)
  seeded.dispose()
}

// ------------------------------------------------------- 任务取消 ----
{
  const nothing = await call(api, { url: '/dsh-wechat-publish/api?action=cancelJob&id=job-does-not-exist' })
  assert.equal(nothing.status, 404)
}

// 任意 markdown 都能预览：无 frontmatter、无 cover 的纯文本也要能渲染
{
  const plain = path.join(tmpdir(), `wxpanel-plain-${process.pid}.md`)
  writeFileSync(plain, '# 随便一段文字\n\n没有 frontmatter 的 markdown。\n\n## 第二节\n\n行内公式 $E=mc^2$。\n')
  const { status, payload } = await call(api, { url: `/dsh-wechat-publish/api?action=preview&path=${encodeURIComponent(plain)}` })
  assert.equal(status, 200)
  assert.equal(payload.ok, true, payload.error)
  assert.equal(payload.meta.title, '随便一段文字')
  assert.equal(payload.stats.svg, 1)
  assert.equal(payload.normalized, true)

  // 覆盖字段：不改源文件也能换标题
  const overridden = await call(api, {
    url: `/dsh-wechat-publish/api?action=preview&path=${encodeURIComponent(plain)}&title=${encodeURIComponent('面板指定的标题')}`,
  })
  assert.equal(overridden.payload.ok, true, overridden.payload.error)
  assert.equal(overridden.payload.meta.title, '面板指定的标题')
  rmSync(plain, { force: true })
}

// 未知 action
{
  const { status } = await call(api, { url: '/dsh-wechat-publish/api?action=nope' })
  assert.equal(status, 400)
}

// 非同源请求被拒
{
  const { status } = await call(api, {
    url: '/dsh-wechat-publish/api?action=status',
    headers: { origin: 'https://evil.example' },
  })
  assert.equal(status, 403)
}

jobs.dispose()
rmSync(DSH_HOME, { recursive: true, force: true })
console.log('panel server test ok')
