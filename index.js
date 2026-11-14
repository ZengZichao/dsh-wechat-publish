// dsh-wechat-publish · DeepSeek Harness 插件的 Host 半边（适配 DSH 0.2.2）。
//
// 两件事：
//   1. 把插件自带的两个 skill（skills/paper-translation、skills/wechat-publish）
//      注册进 ctx.skills，模型与 /skill 命令都能发现和加载；
//   2. 注册面板路由（lib/server.js），给 client.js 的预览 / 发布 / 设置面板
//      提供同源 HTTP API 与本地图床。
//
// 本插件不 import 任何 npm 包：本地目录安装（link:）不会安装 dependencies，
// 从链接目录解析 @deepseek-ai/* 会失败。因此配置项存在
// $DSH_HOME/dsh-wechat-publish/settings.json，而不是插件 Config。
import { createSkillProvider } from './lib/skills.js'
import { createPanelRoutes, PanelJobs } from './lib/server.js'

/** Cordis 插件名。 */
export const name = 'dsh-wechat-publish'

/** 依赖的 DSH 服务。 */
export const inject = ['skills']

/** 额外允许预览读取图片的根目录（部署默认工作目录 + 进程启动目录）。 */
function extraImageRoots(ctx) {
  const roots = []
  try {
    // 0.2.x：workingDirectory 服务的 defaultDirectory 是「没有会话工作目录时的部署默认值」。
    const workingDirectory = typeof ctx.get === 'function' ? ctx.get('workingDirectory') : undefined
    const dir = workingDirectory && workingDirectory.defaultDirectory
    if (typeof dir === 'string' && dir) roots.push(dir)
  } catch { /* 服务缺失时不影响面板其余功能 */ }
  try {
    if (process.cwd()) roots.push(process.cwd())
  } catch { /* 进程目录不可读时忽略 */ }
  return roots
}

/** 注册随包 skill 提供方与面板路由。 */
export function apply(ctx) {
  // 0.2.x 的 registerProvider 会给工厂传入 SkillProviderControl：
  // SKILL.md 变更时用它触发目录失效；注册释放时 signal 中止 watcher。
  ctx.effect(() => ctx.skills.registerProvider((control) => createSkillProvider(control)), 'dsh-wechat-publish: skills')

  const jobs = new PanelJobs()
  ctx.effect(() => () => jobs.dispose(), 'dsh-wechat-publish: jobs')

  const roots = extraImageRoots(ctx)

  ctx.inject(['webServer'], (inner) => {
    const server = inner.webServer || (typeof inner.get === 'function' ? inner.get('webServer') : undefined)
    if (!server || typeof server.register !== 'function') return
    inner.effect(() => {
      const routes = createPanelRoutes({ dshHome: process.env.DSH_HOME, jobs, extraRoots: roots })
      const disposers = []
      for (const route of routes) {
        try { disposers.push(server.register(route)) } catch { /* 单条失败不影响其余 */ }
      }
      return () => disposers.forEach((dispose) => dispose())
    }, 'dsh-wechat-publish: panel routes')
  })
}
