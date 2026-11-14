/**
 * dsh-wechat-publish — browser half.
 *
 * 注册两个槽位：
 *   sidebar.panellist → 侧栏图标（id = wechat-publish）
 *   main              → 主面板，key = wechat-publish
 *
 * 面板三个标签页：
 *   预览   —— 渲染与草稿箱完全一致的 HTML（主题已内联、公式已转 SVG）
 *   草稿箱 —— 只读清点公众号草稿箱
 *   设置   —— 查看渲染 / 翻译 / 凭据 / 环境四组生效设置，可改面板偏好
 *
 * 数据一律来自 Host 半边（lib/server.js）的同源路由，浏览器不直接读文件。
 */

window.__ModuleLoader__.load({
  id: 'dsh-wechat-publish',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })

    const React = require('react')
    const h = React.createElement
    const { useState, useEffect, useRef, useMemo, useCallback } = React

    const API = '/dsh-wechat-publish/api'
    const PANEL_ID = 'wechat-publish'
    const LOCALE_NS = 'dsh-wechat-publish'
    const STORAGE_KEY = 'dsh-wechat-publish:last-path'
    const TREE_STORAGE_KEY = 'dsh-wechat-publish:tree-path'

    // ---------------------------------------------------------------- i18n ----
    const LOCALES = {
      zh: {
        'nav': '公众号发布',
        'panel.title': '公众号发布',
        'tab.preview': '预览',
        'tab.drafts': '草稿箱',
        'tab.settings': '设置',
        'path.label': 'Markdown 文件路径',
        'path.placeholder': '粘贴 .md 路径，回车打开',
        'path.load': '打开',
        'preview.refresh': '刷新',
        'preview.empty': '选择一篇 Markdown 开始',
        'preview.loading': '正在渲染',
        'publish.button': '发布',
        'publish.arm': '确认发布',
        'publish.running': '发布中',
        'publish.success': '已创建草稿',
        'publish.failed': '发布失败',
        'publish.openDraft': '公众号后台',
        'publish.cancel': '取消',
        'publish.timedOut': '超时终止',
        'publish.cancelled': '已取消',
        'publish.duplicate': '仍然发布',
        'publish.duplicateWarn': '该文件本次已发布，继续会再建一篇草稿。',
        'publish.verify': '发布自检',
        'publish.verify.pass': '自检通过',
        'publish.verify.fail': '自检未通过',
        'publish.verify.running': '正在回读草稿',
        'publish.trimDrop': '超出上限，将裁剪 {dropped} 节、保留 {kept} 节',
        'publish.stats': '产物',
        'publish.images': '图片',
        'publish.imageMissing': '缺失',
        'publish.table': '表格',
        'settings.title': '偏好',
        'settings.save': '保存',
        'settings.saved': '已保存',
        'settings.saving': '保存中',
        'settings.field.maxContentBytes': '正文体积上限（字节）',
        'settings.field.pythonBin': 'Python 解释器',
        'settings.field.themeCacheHours': '主题缓存（小时）',
        'settings.help.maxContentBytes': '留 0 使用默认 512 KB',
        'settings.help.pythonBin': '留空自动选择',
        'settings.envOverride': '环境变量已覆盖',
        'settings.group.render': '渲染',
        'settings.group.translate': '翻译',
        'settings.group.credentials': '凭据',
        'settings.group.environment': '环境',
        'settings.source.fixed': '固定',
        'settings.source.env': '环境变量',
        'settings.source.panel': '面板',
        'settings.source.default': '默认',
        'settings.source.auto': '自动',
        'settings.source.cache': '缓存',
        'settings.source.missing': '缺失',
        'settings.source.manual': '手动',
        'settings.credMissing': '凭据不完整，暂不能发布',
        'settings.readonly': '只读',
        'drafts.empty': '还没有草稿',
        'drafts.refresh': '刷新',
        'drafts.total': '{n} 篇',
        'drafts.title': '标题',
        'drafts.time': '更新时间',
        'drafts.id': 'media_id',
        'common.error': '错误',
        'common.retry': '重试',
        'common.close': '关闭',
        'common.idle': '',
        'tree.toggle': '文件',
        'tree.title': '文件',
        'tree.up': '上一级',
        'tree.refresh': '刷新',
        'tree.markdownOnly': '只看 .md',
        'tree.empty': '空目录',
        'tree.recent': '最近打开',
        'tree.error': '目录读取失败',
        'tree.truncated': '仅显示前 2000 项',
        'tree.search': '筛选当前目录',
        'tree.new': '新建 Markdown',
        'tree.emptyMatch': '没有匹配项',
        'meta.toggle': '文章信息',
        'meta.title': '标题',
        'meta.author': '作者',
        'meta.digest': '摘要',
        'meta.cover': '封面图路径',
        'meta.literature': '学术译文模式',
        'meta.apply': '预览效果',
        'meta.save': '保存到文件',
        'meta.saving': '保存中',
        'meta.saved': '已保存',
        'meta.unsaved': '未保存',
        'meta.literatureWarn': '开启后会移除正文全部表格，只留表题。继续？',
        'editor.body': '正文',
        'editor.open': '编辑 Markdown',
        'editor.close': '收起',
        'editor.save': '保存',
        'editor.saving': '保存中',
        'editor.saved': '已保存',
        'editor.chars': '{n} 字符',
      },
      en: {
        'nav': 'WeChat publishing',
        'panel.title': 'WeChat publishing',
        'tab.preview': 'Preview',
        'tab.drafts': 'Drafts',
        'tab.settings': 'Settings',
        'path.label': 'Markdown file path',
        'path.placeholder': 'Paste a .md path and press Enter',
        'path.load': 'Open',
        'preview.refresh': 'Refresh',
        'preview.empty': 'Choose a Markdown file to start',
        'preview.loading': 'Rendering',
        'publish.button': 'Publish',
        'publish.arm': 'Confirm publish',
        'publish.running': 'Publishing',
        'publish.success': 'Draft created',
        'publish.failed': 'Publish failed',
        'publish.openDraft': 'WeChat console',
        'publish.cancel': 'Cancel',
        'publish.timedOut': 'Timed out',
        'publish.cancelled': 'Cancelled',
        'publish.duplicate': 'Publish anyway',
        'publish.duplicateWarn': 'This file was published in this session; continuing creates another draft.',
        'publish.verify': 'Draft check',
        'publish.verify.pass': 'Check passed',
        'publish.verify.fail': 'Check failed',
        'publish.verify.running': 'Reading the draft back',
        'publish.trimDrop': 'Over the limit: {dropped} sections trimmed, {kept} kept',
        'publish.stats': 'Output',
        'publish.images': 'images',
        'publish.imageMissing': 'missing',
        'publish.table': 'tables',
        'settings.title': 'Preferences',
        'settings.save': 'Save',
        'settings.saved': 'Saved',
        'settings.saving': 'Saving',
        'settings.field.maxContentBytes': 'Content size limit (bytes)',
        'settings.field.pythonBin': 'Python interpreter',
        'settings.field.themeCacheHours': 'Theme cache (hours)',
        'settings.help.maxContentBytes': '0 uses the 512 KB default',
        'settings.help.pythonBin': 'Blank picks automatically',
        'settings.envOverride': 'Set by environment',
        'settings.group.render': 'Rendering',
        'settings.group.translate': 'Translation',
        'settings.group.credentials': 'Credentials',
        'settings.group.environment': 'Environment',
        'settings.source.fixed': 'Fixed',
        'settings.source.env': 'Environment',
        'settings.source.panel': 'Panel',
        'settings.source.default': 'Default',
        'settings.source.auto': 'Auto',
        'settings.source.cache': 'Cache',
        'settings.source.missing': 'Missing',
        'settings.source.manual': 'Manual',
        'settings.credMissing': 'Credentials incomplete; publishing is unavailable',
        'settings.readonly': 'read-only',
        'drafts.empty': 'No drafts yet',
        'drafts.refresh': 'Refresh',
        'drafts.total': '{n}',
        'drafts.title': 'Title',
        'drafts.time': 'Updated',
        'drafts.id': 'media_id',
        'common.error': 'Error',
        'common.retry': 'Retry',
        'common.close': 'Close',
        'common.idle': '',
        'tree.toggle': 'Files',
        'tree.title': 'Files',
        'tree.up': 'Up one level',
        'tree.refresh': 'Refresh',
        'tree.markdownOnly': 'Markdown only',
        'tree.empty': 'Empty directory',
        'tree.recent': 'Recent',
        'tree.error': 'Could not read the directory',
        'tree.truncated': 'Showing the first 2000 entries',
        'tree.search': 'Filter this directory',
        'tree.new': 'New Markdown',
        'tree.emptyMatch': 'No matches',
        'meta.toggle': 'Article info',
        'meta.title': 'Title',
        'meta.author': 'Author',
        'meta.digest': 'Digest',
        'meta.cover': 'Cover image path',
        'meta.literature': 'Academic translation mode',
        'meta.apply': 'Preview changes',
        'meta.save': 'Save to file',
        'meta.saving': 'Saving',
        'meta.saved': 'Saved',
        'meta.unsaved': 'Unsaved',
        'meta.literatureWarn': 'This removes every table from the body and keeps the captions. Continue?',
        'editor.body': 'Body',
        'editor.open': 'Edit Markdown',
        'editor.close': 'Collapse',
        'editor.save': 'Save',
        'editor.saving': 'Saving',
        'editor.saved': 'Saved',
        'editor.chars': '{n} chars',
      },
    }

    let activeLang = 'zh'
    try {
      const nav = (typeof navigator !== 'undefined' && navigator.language) || 'en'
      activeLang = String(nav).toLowerCase().startsWith('zh') ? 'zh' : 'en'
    } catch { /* keep the default */ }

    function t(key, vars) {
      const table = LOCALES[activeLang] || LOCALES.zh
      let text = table[key] || LOCALES.zh[key] || LOCALES.en[key] || key
      if (vars) {
        for (const [name, value] of Object.entries(vars)) {
          text = text.replaceAll(`{${name}}`, String(value))
        }
      }
      return text
    }

    /** 同 t()，但缺键时退回调用方给的原文（用于 Host 端已本地化的分组名）。 */
    function tOr(key, fallback) {
      const table = LOCALES[activeLang] || LOCALES.zh
      return table[key] || LOCALES.zh[key] || LOCALES.en[key] || fallback || key
    }

    /**
     * 探测宿主当前是亮色还是暗色主题。
     * 面板自己不引入主题状态（插槽没有注入 theme 服务），改为读取宿主写在根节点上的
     * --dsw-alias-bg-base 令牌并判断亮度：无论用户选的是亮色、暗色还是跟随系统都成立。
     */
    function hostIsDark() {
      try {
        const value = getComputedStyle(document.documentElement)
          .getPropertyValue('--dsw-alias-bg-base').trim()
        if (!value) return false
        const match = value.match(/#([0-9a-f]{3}|[0-9a-f]{6})/i)
        if (!match) return false
        let hex = match[1]
        if (hex.length === 3) hex = hex.split('').map((c) => c + c).join('')
        const r = parseInt(hex.slice(0, 2), 16) / 255
        const g = parseInt(hex.slice(2, 4), 16) / 255
        const b = parseInt(hex.slice(4, 6), 16) / 255
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 0.5
      } catch { return false }
    }

    // ----------------------------------------------------------------- CSS ----
    const CSS = [
      '/* ---------------------------------------------------------------------------',
      ' * Radix UI Colors：light / dark 全阶',
      ' * 用法：1 页面底，2 次级底，3 选中底，4 悬停，6 细线，7 控件描边',
      ' *       8 悬停描边，9 实心，10 实心悬停，11 次级文字，12 正文文字',
      ' * 排版：12 / 13 / 15 三档，控件高 26px，线条 0.5px，过渡一概不加。',
      ' * ------------------------------------------------------------------------ */',
      '.wx-panel {',
      '  --wx-gray-1: #fcfcfc;', '  --wx-gray-2: #f9f9f9;', '  --wx-gray-3: #f0f0f0;',
      '  --wx-gray-4: #e8e8e8;', '  --wx-gray-5: #e0e0e0;', '  --wx-gray-6: #d9d9d9;',
      '  --wx-gray-7: #cecece;', '  --wx-gray-8: #bbbbbb;', '  --wx-gray-9: #8d8d8d;',
      '  --wx-gray-10: #838383;', '  --wx-gray-11: #646464;', '  --wx-gray-12: #202020;',
      '  --wx-indigo-1: #fdfdfe;', '  --wx-indigo-2: #f7f9ff;', '  --wx-indigo-3: #edf2fe;',
      '  --wx-indigo-4: #e1e9ff;', '  --wx-indigo-5: #d2deff;', '  --wx-indigo-6: #c1d0ff;',
      '  --wx-indigo-7: #abbdf9;', '  --wx-indigo-8: #8da4ef;', '  --wx-indigo-9: #3e63dd;',
      '  --wx-indigo-10: #3358d4;', '  --wx-indigo-11: #3a5bc7;', '  --wx-indigo-12: #1f2d5c;',
      '  --wx-red-1: #fffcfc;', '  --wx-red-2: #fff7f7;', '  --wx-red-3: #feebec;',
      '  --wx-red-6: #fdbdbe;', '  --wx-red-9: #e5484d;', '  --wx-red-10: #dc3e42;',
      '  --wx-red-11: #ce2c31;', '  --wx-red-12: #641723;',
      '  --wx-green-1: #fbfefc;', '  --wx-green-2: #f4fbf6;', '  --wx-green-3: #e6f6eb;',
      '  --wx-green-6: #adddc0;', '  --wx-green-9: #30a46c;', '  --wx-green-11: #218358;',
      '  --wx-green-12: #193b2d;',
      '  --wx-amber-1: #fefdfb;', '  --wx-amber-2: #fefbe9;', '  --wx-amber-3: #fff7c2;',
      '  --wx-amber-6: #f3d673;', '  --wx-amber-9: #ffc53d;', '  --wx-amber-11: #ab6400;',
      '  --wx-amber-12: #4f3422;',
      '  --wx-bg: var(--wx-gray-1);',
      '  --wx-bg-subtle: var(--wx-gray-2);',
      '  --wx-bg-hover: var(--wx-gray-4);',
      '  --wx-bg-select: var(--wx-indigo-3);',
      '  --wx-line-subtle: var(--wx-gray-6);',
      '  --wx-line: var(--wx-gray-7);',
      '  --wx-line-strong: var(--wx-gray-8);',
      '  --wx-text: var(--wx-gray-12);',
      '  --wx-text-2: var(--wx-gray-11);',
      '  --wx-solid: var(--wx-indigo-9);',
      '  --wx-solid-hover: var(--wx-indigo-10);',
      '  --wx-accent-text: var(--wx-indigo-11);',
      '  --wx-accent-line: var(--wx-indigo-6);',
      '  --wx-danger: var(--wx-red-9);', '  --wx-danger-hover: var(--wx-red-10);',
      '  --wx-danger-text: var(--wx-red-12);', '  --wx-danger-bg: var(--wx-red-3);',
      '  --wx-danger-line: var(--wx-red-6);',
      '  --wx-success: var(--wx-green-9);', '  --wx-success-text: var(--wx-green-12);',
      '  --wx-success-bg: var(--wx-green-3);', '  --wx-success-line: var(--wx-green-6);',
      '  --wx-warn: var(--wx-amber-9);', '  --wx-warn-text: var(--wx-amber-12);',
      '  --wx-warn-bg: var(--wx-amber-3);', '  --wx-warn-line: var(--wx-amber-6);',
      '  --wx-paper: #ffffff;',
      '  --wx-paper-text: #202020;',
      '  --wx-on-solid: #ffffff;',
      '  --wx-fs-1: 12px;', '  --wx-fs-2: 13px;', '  --wx-fs-3: 15px;',
      '  --wx-r: 4px;',
      '  --wx-control: 26px;',
      '  --wx-mono: ui-monospace, SFMono-Regular, Menlo, monospace;',
      '}',
      '',
      '.wx-panel.wx-dark {',
      '  --wx-gray-1: #111111;', '  --wx-gray-2: #191919;', '  --wx-gray-3: #222222;',
      '  --wx-gray-4: #2a2a2a;', '  --wx-gray-5: #313131;', '  --wx-gray-6: #3a3a3a;',
      '  --wx-gray-7: #484848;', '  --wx-gray-8: #606060;', '  --wx-gray-9: #6e6e6e;',
      '  --wx-gray-10: #7b7b7b;', '  --wx-gray-11: #b4b4b4;', '  --wx-gray-12: #eeeeee;',
      '  --wx-indigo-1: #11131f;', '  --wx-indigo-2: #141726;', '  --wx-indigo-3: #182449;',
      '  --wx-indigo-4: #1d2e62;', '  --wx-indigo-5: #253974;', '  --wx-indigo-6: #304384;',
      '  --wx-indigo-7: #3a4f97;', '  --wx-indigo-8: #435db1;', '  --wx-indigo-9: #3e63dd;',
      '  --wx-indigo-10: #5472e4;', '  --wx-indigo-11: #9eb1ff;', '  --wx-indigo-12: #d6e1ff;',
      '  --wx-red-1: #191111;', '  --wx-red-2: #201314;', '  --wx-red-3: #3b1219;',
      '  --wx-red-6: #72232d;', '  --wx-red-9: #e5484d;', '  --wx-red-10: #ec5d5e;',
      '  --wx-red-11: #ff9592;', '  --wx-red-12: #ffd1d9;',
      '  --wx-green-1: #0e1512;', '  --wx-green-2: #121b17;', '  --wx-green-3: #132d21;',
      '  --wx-green-6: #20573e;', '  --wx-green-9: #30a46c;', '  --wx-green-11: #3dd68c;',
      '  --wx-green-12: #b1f1cb;',
      '  --wx-amber-1: #16120c;', '  --wx-amber-2: #1d180f;', '  --wx-amber-3: #302008;',
      '  --wx-amber-6: #5c3d05;', '  --wx-amber-9: #ffc53d;', '  --wx-amber-11: #ffca16;',
      '  --wx-amber-12: #ffe7b3;',
      '}',
      '',
      '/* ---------------------------------------------------------------- 骨架 -- */',
      '.wx-panel {',
      '  display: flex;',
      '  flex-direction: column;',
      '  height: 100%;',
      '  min-height: 0;',
      '  background: var(--wx-bg);',
      '  color: var(--wx-text);',
      '  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;',
      '  font-size: var(--wx-fs-2);',
      '  line-height: 1.5;',
      '  -webkit-font-smoothing: antialiased;',
      '}',
      '',
      '.wx-head {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 8px;',
      '  padding: 12px;',
      '  border-bottom: 0.5px solid var(--wx-line-subtle);',
      '}',
      '',
      '.wx-head-top {',
      '  display: flex;',
      '  align-items: center;',
      '  gap: 8px;',
      '}',
      '',
      '.wx-title {',
      '  flex: 1;',
      '  min-width: 0;',
      '  margin: 0;',
      '  font-size: var(--wx-fs-3);',
      '  font-weight: 600;',
      '  letter-spacing: -0.01em;',
      '  overflow: hidden;',
      '  text-overflow: ellipsis;',
      '  white-space: nowrap;',
      '}',
      '',
      '.wx-source {',
      '  display: flex;',
      '  align-items: center;',
      '  gap: 4px;',
      '}',
      '',
      '.wx-source .wx-input {',
      '  flex: 1;',
      '  min-width: 0;',
      '}',
      '',
      '/* -------------------------------------------------------------- 控件 ---- */',
      '.wx-input {',
      '  box-sizing: border-box;',
      '  height: var(--wx-control);',
      '  min-width: 0;',
      '  padding: 0 8px;',
      '  color: var(--wx-text);',
      '  background: var(--wx-bg);',
      '  border: 0.5px solid var(--wx-line);',
      '  border-radius: var(--wx-r);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  outline: none;',
      '}',
      '',
      '.wx-input::placeholder {',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-input:hover {',
      '  border-color: var(--wx-line-strong);',
      '}',
      '',
      '.wx-input:focus-visible {',
      '  border-color: var(--wx-line-strong);',
      '  outline: 2px solid var(--wx-solid);',
      '  outline-offset: 1px;',
      '}',
      '',
      '.wx-btn {',
      '  box-sizing: border-box;',
      '  display: inline-flex;',
      '  align-items: center;',
      '  justify-content: center;',
      '  gap: 4px;',
      '  height: var(--wx-control);',
      '  padding: 0 10px;',
      '  border: 0.5px solid var(--wx-line);',
      '  border-radius: var(--wx-r);',
      '  background: var(--wx-bg);',
      '  color: var(--wx-text);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  white-space: nowrap;',
      '  cursor: pointer;',
      '}',
      '',
      '.wx-btn:hover {',
      '  background: var(--wx-bg-hover);',
      '}',
      '',
      '.wx-btn:focus-visible {',
      '  outline: 2px solid var(--wx-solid);',
      '  outline-offset: 1px;',
      '}',
      '',
      '.wx-btn:disabled {',
      '  opacity: 0.45;',
      '  cursor: default;',
      '  background: var(--wx-bg);',
      '}',
      '',
      '.wx-btn-primary {',
      '  min-width: 84px;',
      '  font-weight: 500;',
      '  background: var(--wx-solid);',
      '  border-color: var(--wx-solid);',
      '  color: var(--wx-on-solid);',
      '}',
      '',
      '.wx-btn-primary:hover {',
      '  background: var(--wx-solid-hover);',
      '  border-color: var(--wx-solid-hover);',
      '}',
      '',
      '.wx-btn-primary:disabled {',
      '  background: var(--wx-gray-4);',
      '  border-color: var(--wx-gray-4);',
      '  color: var(--wx-gray-11);',
      '  opacity: 1;',
      '}',
      '',
      '.wx-btn-danger {',
      '  font-weight: 500;',
      '  background: var(--wx-danger);',
      '  border-color: var(--wx-danger);',
      '  color: var(--wx-on-solid);',
      '}',
      '',
      '.wx-btn-danger:hover {',
      '  background: var(--wx-danger-hover);',
      '  border-color: var(--wx-danger-hover);',
      '}',
      '',
      '.wx-btn-quiet {',
      '  border-color: transparent;',
      '  background: transparent;',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-btn-quiet:hover {',
      '  background: var(--wx-bg-hover);',
      '  color: var(--wx-text);',
      '}',
      '',
      '.wx-btn[aria-pressed="true"] {',
      '  background: var(--wx-bg-select);',
      '  border-color: var(--wx-accent-line);',
      '  color: var(--wx-accent-text);',
      '}',
      '',
      '.wx-icon-btn {',
      '  box-sizing: border-box;',
      '  display: inline-flex;',
      '  align-items: center;',
      '  justify-content: center;',
      '  flex: 0 0 auto;',
      '  width: var(--wx-control);',
      '  height: var(--wx-control);',
      '  padding: 0;',
      '  border: 0.5px solid transparent;',
      '  border-radius: var(--wx-r);',
      '  background: transparent;',
      '  color: var(--wx-text-2);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  cursor: pointer;',
      '}',
      '',
      '.wx-icon-btn:hover {',
      '  background: var(--wx-bg-hover);',
      '  color: var(--wx-text);',
      '}',
      '',
      '.wx-icon-btn[aria-pressed="true"] {',
      '  background: var(--wx-bg-select);',
      '  color: var(--wx-accent-text);',
      '}',
      '',
      '.wx-icon-btn:focus-visible {',
      '  outline: 2px solid var(--wx-solid);',
      '  outline-offset: 1px;',
      '}',
      '',
      '.wx-tool-btn {',
      '  box-sizing: border-box;',
      '  display: inline-flex;',
      '  align-items: center;',
      '  justify-content: center;',
      '  flex: 0 0 auto;',
      '  height: var(--wx-control);',
      '  padding: 0 6px;',
      '  border: 0.5px solid transparent;',
      '  border-radius: var(--wx-r);',
      '  background: transparent;',
      '  color: var(--wx-text-2);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  cursor: pointer;',
      '}',
      '',
      '.wx-tool-btn:hover {',
      '  background: var(--wx-bg-hover);',
      '  color: var(--wx-text);',
      '}',
      '',
      '.wx-tool-btn[aria-pressed="true"] {',
      '  background: var(--wx-bg-select);',
      '  color: var(--wx-accent-text);',
      '}',
      '',
      '.wx-tool-btn:focus-visible {',
      '  outline: 2px solid var(--wx-solid);',
      '  outline-offset: 1px;',
      '}',
      '',
      '.wx-kbd {',
      '  font-family: var(--wx-mono);',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-linkbtn {',
      '  padding: 0;',
      '  border: none;',
      '  background: none;',
      '  color: var(--wx-accent-text);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  cursor: pointer;',
      '}',
      '',
      '.wx-linkbtn:hover {',
      '  text-decoration: underline;',
      '  text-underline-offset: 2px;',
      '}',
      '',
      '/* -------------------------------------------------------------- 标签页 -- */',
      '.wx-tabs {',
      '  display: flex;',
      '  gap: 16px;',
      '  padding: 0 12px;',
      '  border-bottom: 0.5px solid var(--wx-line-subtle);',
      '}',
      '',
      '.wx-tab {',
      '  height: 34px;',
      '  padding: 0;',
      '  border: none;',
      '  background: none;',
      '  color: var(--wx-text-2);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  cursor: pointer;',
      '}',
      '',
      '.wx-tab:hover {',
      '  color: var(--wx-text);',
      '}',
      '',
      '.wx-tab-on {',
      '  color: var(--wx-text);',
      '  font-weight: 600;',
      '}',
      '',
      '.wx-tab:focus-visible {',
      '  outline: 2px solid var(--wx-solid);',
      '  outline-offset: 1px;',
      '}',
      '',
      '/* -------------------------------------------------------------- 文件树 -- */',
      '.wx-tree {',
      '  display: flex;',
      '  flex-direction: column;',
      '  flex: 0 0 auto;',
      '  max-height: 46%;',
      '  min-height: 0;',
      '  border-bottom: 0.5px solid var(--wx-line-subtle);',
      '  background: var(--wx-bg-subtle);',
      '}',
      '',
      '.wx-tree-head {',
      '  display: flex;',
      '  align-items: center;',
      '  gap: 4px;',
      '  padding: 6px 4px 6px 8px;',
      '  border-bottom: 0.5px solid var(--wx-line-subtle);',
      '}',
      '',
      '.wx-tree-head > span {',
      '  flex: 1;',
      '  min-width: 0;',
      '  font-family: var(--wx-mono);',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '  overflow: hidden;',
      '  text-overflow: ellipsis;',
      '  white-space: nowrap;',
      '}',
      '',
      '.wx-tree-tools {',
      '  display: flex;',
      '  align-items: center;',
      '  gap: 2px;',
      '  flex: 0 0 auto;',
      '}',
      '',
      '.wx-tree-search {',
      '  padding: 6px 8px;',
      '  border-bottom: 0.5px solid var(--wx-line-subtle);',
      '}',
      '',
      '.wx-tree-search .wx-input {',
      '  width: 100%;',
      '  flex: none;',
      '}',
      '',
      '.wx-tree-new {',
      '  display: flex;',
      '  align-items: center;',
      '  border-bottom: 0.5px solid var(--wx-line-subtle);',
      '  padding: 0 8px;',
      '  height: 30px;',
      '}',
      '',
      '.wx-tree-new button {',
      '  padding: 0;',
      '  border: none;',
      '  background: none;',
      '  color: var(--wx-text-2);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  cursor: pointer;',
      '}',
      '',
      '.wx-tree-new button:hover {',
      '  color: var(--wx-text);',
      '}',
      '',
      '.wx-tree-body {',
      '  flex: 1 1 auto;',
      '  min-height: 0;',
      '  overflow: auto;',
      '  padding: 4px 0;',
      '}',
      '',
      '.wx-tree-row {',
      '  display: flex;',
      '  align-items: center;',
      '  gap: 8px;',
      '  width: 100%;',
      '  height: 26px;',
      '  padding: 0 8px;',
      '  border: none;',
      '  background: none;',
      '  color: var(--wx-text);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  text-align: left;',
      '  cursor: pointer;',
      '  overflow: hidden;',
      '}',
      '',
      '.wx-tree-row:hover {',
      '  background: var(--wx-bg-hover);',
      '}',
      '',
      '.wx-tree-row[aria-current="true"] {',
      '  background: var(--wx-bg-select);',
      '  color: var(--wx-accent-text);',
      '}',
      '',
      '.wx-tree-row:focus-visible {',
      '  outline: 2px solid var(--wx-solid);',
      '  outline-offset: -2px;',
      '}',
      '',
      '.wx-tree-name {',
      '  flex: 1;',
      '  min-width: 0;',
      '  overflow: hidden;',
      '  text-overflow: ellipsis;',
      '  white-space: nowrap;',
      '}',
      '',
      '.wx-tree-ext {',
      '  flex: 0 0 auto;',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '  font-variant-numeric: tabular-nums;',
      '}',
      '',
      '.wx-tree-dir {',
      '  flex: 0 0 auto;',
      '  width: 10px;',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-tree-recent {',
      '  padding: 8px;',
      '  border-top: 0.5px solid var(--wx-line-subtle);',
      '}',
      '',
      '.wx-tree-recent h4 {',
      '  margin: 0 0 4px;',
      '  font-size: var(--wx-fs-1);',
      '  font-weight: 500;',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-recent-row {',
      '  display: block;',
      '  width: 100%;',
      '  height: 24px;',
      '  padding: 0 4px;',
      '  border: none;',
      '  border-radius: var(--wx-r);',
      '  background: none;',
      '  color: var(--wx-text);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  text-align: left;',
      '  white-space: nowrap;',
      '  overflow: hidden;',
      '  text-overflow: ellipsis;',
      '  cursor: pointer;',
      '}',
      '',
      '.wx-recent-row:hover {',
      '  background: var(--wx-bg-hover);',
      '}',
      '',
      '.wx-tree-empty {',
      '  padding: 16px 8px;',
      '  text-align: center;',
      '  color: var(--wx-text-2);',
      '  font-size: var(--wx-fs-1);',
      '}',
      '',
      '/* -------------------------------------------------------------- 内容区 -- */',
      '.wx-main {',
      '  display: flex;',
      '  flex-direction: column;',
      '  flex: 1 1 auto;',
      '  min-height: 0;',
      '}',
      '',
      '.wx-body {',
      '  flex: 1 1 auto;',
      '  min-width: 0;',
      '  min-height: 0;',
      '  overflow: auto;',
      '  padding: 12px;',
      '}',
      '',
      '.wx-empty {',
      '  padding: 32px 12px;',
      '  text-align: center;',
      '  color: var(--wx-text-2);',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.7;',
      '}',
      '',
      '/* -------------------------------------------------------------- 摘要行 -- */',
      '.wx-summary {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 4px;',
      '  margin: 0 0 8px;',
      '}',
      '',
      '.wx-summary-title {',
      '  margin: 0;',
      '  font-size: var(--wx-fs-3);',
      '  font-weight: 500;',
      '  line-height: 1.4;',
      '  color: var(--wx-text);',
      '  overflow: hidden;',
      '  display: -webkit-box;',
      '  -webkit-line-clamp: 2;',
      '  -webkit-box-orient: vertical;',
      '}',
      '',
      '.wx-summary-meta {',
      '  display: flex;',
      '  flex-wrap: wrap;',
      '  align-items: baseline;',
      '  gap: 12px;',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '  font-variant-numeric: tabular-nums;',
      '}',
      '',
      '/* -------------------------------------------------------------- 提示条 -- */',
      '.wx-alert {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 2px;',
      '  margin: 0 0 8px;',
      '  padding: 8px 10px;',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.6;',
      '  border: 0.5px solid var(--wx-line);',
      '  border-radius: 0;',
      '  background: var(--wx-bg-subtle);',
      '  color: var(--wx-text);',
      '}',
      '',
      '.wx-alert-warn {',
      '  background: var(--wx-warn-bg);',
      '  border-color: var(--wx-warn-line);',
      '  color: var(--wx-warn-text);',
      '}',
      '',
      '.wx-alert-bad {',
      '  background: var(--wx-danger-bg);',
      '  border-color: var(--wx-danger-line);',
      '  color: var(--wx-danger-text);',
      '}',
      '',
      '.wx-alert-ok {',
      '  background: var(--wx-success-bg);',
      '  border-color: var(--wx-success-line);',
      '  color: var(--wx-success-text);',
      '}',
      '',
      '.wx-warn {',
      '  margin: 0 0 8px;',
      '  padding: 8px 10px;',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.6;',
      '  background: var(--wx-warn-bg);',
      '  border: 0.5px solid var(--wx-warn-line);',
      '  color: var(--wx-warn-text);',
      '}',
      '',
      '.wx-err {',
      '  margin: 0 0 8px;',
      '  padding: 8px 10px;',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.6;',
      '  background: var(--wx-danger-bg);',
      '  border: 0.5px solid var(--wx-danger-line);',
      '  color: var(--wx-danger-text);',
      '}',
      '',
      '/* -------------------------------------------------------------- 预览 ---- */',
      '.wx-screen {',
      '  width: 100%;',
      '  margin: 0;',
      '}',
      '',
      '.wx-article {',
      '  max-width: 677px;',
      '  margin: 0 auto;',
      '  padding: 16px 16px 24px;',
      '  background: var(--wx-paper);',
      '  border: 0.5px solid var(--wx-line-subtle);',
      '  word-wrap: break-word;',
      '  overflow-wrap: anywhere;',
      '  color: var(--wx-paper-text);',
      '  content-visibility: auto;',
      '  contain-intrinsic-size: auto 600px;',
      '}',
      '',
      '/* -------------------------------------------------------------- 发布 ---- */',
      '.wx-job {',
      '  margin: 12px 0 0;',
      '  padding: 8px 10px;',
      '  border: 0.5px solid var(--wx-line-subtle);',
      '  background: var(--wx-bg-subtle);',
      '}',
      '',
      '.wx-job-head {',
      '  display: flex;',
      '  align-items: baseline;',
      '  gap: 8px;',
      '  font-size: var(--wx-fs-1);',
      '}',
      '',
      '.wx-job-head > span:first-child {',
      '  font-weight: 500;',
      '}',
      '',
      '.wx-job-ok {',
      '  color: var(--wx-success-text);',
      '}',
      '',
      '.wx-job-bad {',
      '  color: var(--wx-danger-text);',
      '}',
      '',
      '.wx-job-run {',
      '  color: var(--wx-warn-text);',
      '}',
      '',
      '.wx-job pre {',
      '  margin: 6px 0 0;',
      '  max-height: 200px;',
      '  overflow: auto;',
      '  padding: 8px;',
      '  background: var(--wx-bg);',
      '  border: 0.5px solid var(--wx-line-subtle);',
      '  font-family: var(--wx-mono);',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.6;',
      '  white-space: pre-wrap;',
      '  word-break: break-all;',
      '}',
      '',
      '/* -------------------------------------------------------------- 自检 ---- */',
      '.wx-verify {',
      '  margin: 8px 0 0;',
      '  padding: 8px 10px;',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.6;',
      '  border: 0.5px solid var(--wx-line);',
      '}',
      '',
      '.wx-verify-ok {',
      '  background: var(--wx-success-bg);',
      '  border-color: var(--wx-success-line);',
      '  color: var(--wx-success-text);',
      '}',
      '',
      '.wx-verify-bad {',
      '  background: var(--wx-danger-bg);',
      '  border-color: var(--wx-danger-line);',
      '  color: var(--wx-danger-text);',
      '}',
      '',
      '.wx-verify ul {',
      '  margin: 4px 0 0;',
      '  padding-left: 16px;',
      '}',
      '',
      '/* -------------------------------------------------------------- 折叠区 -- */',
      '.wx-section {',
      '  margin: 12px 0 0;',
      '  border-top: 0.5px solid var(--wx-line-subtle);',
      '}',
      '',
      '.wx-section-head {',
      '  display: flex;',
      '  align-items: center;',
      '  justify-content: space-between;',
      '  gap: 8px;',
      '  width: 100%;',
      '  height: 36px;',
      '  padding: 0;',
      '  border: none;',
      '  background: none;',
      '  color: var(--wx-text);',
      '  font: inherit;',
      '  font-size: var(--wx-fs-1);',
      '  text-align: left;',
      '  cursor: pointer;',
      '}',
      '',
      '.wx-section-head:focus-visible {',
      '  outline: 2px solid var(--wx-solid);',
      '  outline-offset: 1px;',
      '}',
      '',
      '.wx-section-body {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 8px;',
      '  padding: 0 0 12px;',
      '}',
      '',
      '.wx-meta-grid {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 8px;',
      '}',
      '',
      '.wx-meta-field {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 2px;',
      '}',
      '',
      '.wx-meta-field label {',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-meta-actions {',
      '  display: flex;',
      '  align-items: center;',
      '  flex-wrap: wrap;',
      '  gap: 8px;',
      '  padding: 0;',
      '}',
      '',
      '.wx-hint {',
      '  margin: 0;',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.6;',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-editor {',
      '  margin: 0 0 8px;',
      '  border: 0.5px solid var(--wx-line-subtle);',
      '  background: var(--wx-bg);',
      '}',
      '',
      '.wx-editor-head {',
      '  display: flex;',
      '  align-items: center;',
      '  justify-content: space-between;',
      '  gap: 8px;',
      '  padding: 4px 4px 4px 10px;',
      '  border-bottom: 0.5px solid var(--wx-line-subtle);',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-editor textarea {',
      '  width: 100%;',
      '  box-sizing: border-box;',
      '  min-height: 260px;',
      '  padding: 8px 10px;',
      '  border: none;',
      '  outline: none;',
      '  resize: vertical;',
      '  background: transparent;',
      '  color: var(--wx-text);',
      '  font-family: var(--wx-mono);',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.7;',
      '}',
      '',
      '.wx-editor-body {',
      '  padding: 0 10px 8px;',
      '}',
      '',
      '/* -------------------------------------------------------------- 事实表 -- */',
      '.wx-facts {',
      '  margin: 4px 0 0;',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 2px;',
      '}',
      '',
      '.wx-facts > div {',
      '  display: flex;',
      '  gap: 8px;',
      '  font-size: var(--wx-fs-1);',
      '}',
      '',
      '.wx-facts dt {',
      '  flex: 0 0 auto;',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-facts dd {',
      '  margin: 0;',
      '  color: var(--wx-text);',
      '}',
      '',
      '.wx-list {',
      '  margin: 0 0 8px;',
      '  padding: 8px 10px 8px 24px;',
      '  font-size: var(--wx-fs-1);',
      '  line-height: 1.6;',
      '}',
      '',
      '.wx-list li + li {',
      '  margin-top: 2px;',
      '}',
      '',
      '.wx-list-warn {',
      '  background: var(--wx-warn-bg);',
      '  border: 0.5px solid var(--wx-warn-line);',
      '  color: var(--wx-warn-text);',
      '}',
      '',
      '/* -------------------------------------------------------------- 设置 ---- */',
      '.wx-settings {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 16px;',
      '  max-width: 720px;',
      '}',
      '',
      '.wx-group {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 2px;',
      '  padding-top: 8px;',
      '  border-top: 0.5px solid var(--wx-line-subtle);',
      '}',
      '',
      '.wx-group h3 {',
      '  margin: 0 0 4px;',
      '  font-size: var(--wx-fs-1);',
      '  font-weight: 500;',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-row {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 4px;',
      '  padding: 6px 0;',
      '}',
      '',
      '.wx-row-top {',
      '  display: flex;',
      '  align-items: baseline;',
      '  justify-content: space-between;',
      '  gap: 12px;',
      '}',
      '',
      '.wx-row label {',
      '  flex: 0 0 auto;',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-val {',
      '  min-width: 0;',
      '  text-align: right;',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text);',
      '  word-break: break-all;',
      '}',
      '',
      '.wx-src {',
      '  display: inline-block;',
      '  margin-left: 6px;',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-ro {',
      '  margin-left: 6px;',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '.wx-field {',
      '  display: flex;',
      '  flex-direction: column;',
      '  gap: 4px;',
      '  max-width: 420px;',
      '}',
      '',
      '.wx-field label {',
      '  font-size: var(--wx-fs-1);',
      '  color: var(--wx-text-2);',
      '}',
      '',
      '/* -------------------------------------------------------------- 草稿箱 -- */',
      '.wx-drafts {',
      '  display: flex;',
      '  flex-direction: column;',
      '}',
      '',
      '.wx-table {',
      '  width: 100%;',
      '  border-collapse: collapse;',
      '  font-size: var(--wx-fs-1);',
      '}',
      '',
      '.wx-table th,',
      '.wx-table td {',
      '  padding: 8px 8px 8px 0;',
      '  text-align: left;',
      '  vertical-align: baseline;',
      '  border-bottom: 0.5px solid var(--wx-line-subtle);',
      '}',
      '',
      '.wx-table th {',
      '  font-weight: 500;',
      '  color: var(--wx-text-2);',
      '  white-space: nowrap;',
      '}',
      '',
      '.wx-table td {',
      '  color: var(--wx-text);',
      '}',
      '',
      '.wx-mono {',
      '  font-family: var(--wx-mono);',
      '}',
      '',
      '@media (max-width: 720px) {',
      '  .wx-tree {',
      '    max-height: 40%;',
      '  }',
      '}',
    ].join('')

    // ------------------------------------------------------------------ api ----
    async function apiGet(action, params) {
      // 相对 URL：桌面端的 origin 可能是 dsh-app://app，new URL() 在 opaque origin 下会抛错。
      const query = new URLSearchParams()
      query.set('action', action)
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          if (v !== undefined && v !== null) query.set(k, String(v))
        }
      }
      const response = await fetch(`${API}?${query.toString()}`, { credentials: 'same-origin' })
      const body = await response.json().catch(() => null)
      if (!response.ok || !body || body.ok !== true) {
        const error = new Error((body && body.error) || `HTTP ${response.status}`)
        error.status = response.status
        error.code = body && body.code
        error.payload = body
        throw error
      }
      return body
    }

    async function apiPost(payload) {
      const response = await fetch(API, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok || !body || body.ok !== true) {
        const error = new Error((body && body.error) || `HTTP ${response.status}`)
        error.status = response.status
        error.code = body && body.code
        error.payload = body
        throw error
      }
      return body
    }

    // ------------------------------------------------------------ components ----
    function SidebarIcon(props) {
      const size = (props && props.size) || 18
      return h('svg', {
        width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
        stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round',
        'aria-hidden': true,
      },
        h('path', { d: 'M21 11.5a8.4 8.4 0 0 1-8.5 8.4 8.9 8.9 0 0 1-3.8-.85L3 20l1-4.4A8.3 8.3 0 0 1 3.5 11.5 8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z' }),
        h('path', { d: 'M8.5 10.5h7M8.5 13.5h4' }),
      )
    }

    function PreviewTab(props) {
      const {
        article, preview, job, busy,
        onApplyOverrides, onSaveOverrides, savingMeta, savedMeta, metaError,
        onRefreshPreview, onSaveBody, bodySaving, bodySaved, bodyError,
        verifyResult, verifyRunning,
      } = props
      if (!article) {
        return h('div', { className: 'wx-empty' }, t('preview.empty'))
      }
      const meta = (preview && preview.meta) || article.effective || article.meta || {}
      const stats = preview ? preview.stats : null
      const warnings = [...(article.warnings || []), ...((preview && preview.warnings) || [])]
      const images = preview ? preview.images || [] : []
      const missing = images.filter((img) => !img.exists)
      const sizeCheck = preview ? preview.sizeCheck : null
      return h('div', null,
        h('div', { className: 'wx-summary' },
          h('h3', { className: 'wx-summary-title' }, meta.title || '—'),
          h('div', { className: 'wx-summary-meta' },
            h('span', null, stats ? `${stats.bytes.toLocaleString()} B` : '—'),
            h('span', null,
              `${images.length} ${t('publish.images')}`
              + (missing.length ? `（${missing.length} ${t('publish.imageMissing')}）` : '')),
            stats ? h('span', null, `SVG ${stats.svg}`) : null,
            stats ? h('span', null, `${t('publish.table')} ${stats.table}`) : null,
            h('button', {
              className: 'wx-linkbtn', onClick: onRefreshPreview, disabled: busy === 'preview',
            }, t('preview.refresh')),
          ),
        ),
        warnings.length
          ? h('ul', { className: 'wx-list wx-list-warn' },
              warnings.map((w, i) => h('li', { key: i }, w)))
          : null,
        sizeCheck && sizeCheck.overLimit
          ? h('div', { className: 'wx-warn' },
              h('div', null, `${sizeCheck.contentBytes} B / ${sizeCheck.limitBytes} B`),
              sizeCheck.trim
                ? h('div', { className: 'wx-hint' },
                    t('publish.trimDrop', {
                      kept: sizeCheck.trim.kept.length,
                      dropped: sizeCheck.trim.dropped.length,
                    }))
                : null)
          : null,
        preview && stats && (stats.mathFallback || stats.styleResidue || stats.anchorHref)
          ? h('div', { className: 'wx-err' },
              `${t('common.error')}: svg ${stats.svg}, fallback ${stats.mathFallback}, `
              + `style ${stats.styleResidue}, anchor ${stats.anchorHref}`)
          : null,
        job
          ? h('div', { className: 'wx-job' },
              h('div', { className: 'wx-job-head' },
                h('span', {
                  className: job.status === 'succeeded' ? 'wx-job-ok'
                    : (job.status === 'failed' || job.status === 'cancelled') ? 'wx-job-bad' : 'wx-job-run',
                }, job.status === 'succeeded' ? t('publish.success')
                  : job.status === 'failed' ? (job.timedOut ? t('publish.timedOut') : t('publish.failed'))
                    : job.status === 'cancelled' ? t('publish.cancelled')
                      : t('publish.running')),
                job.mediaId ? h('span', { className: 'wx-mono' }, job.mediaId) : null,
                job.status === 'succeeded'
                  ? h('a', { className: 'wx-linkbtn', href: 'https://mp.weixin.qq.com/', target: '_blank', rel: 'noreferrer' }, t('publish.openDraft'))
                  : null,
              ),
              job.status === 'succeeded' ? null : h('pre', null, job.output || ''),
            )
          : null,
        verifyRunning
          ? h('div', { className: 'wx-hint', style: { padding: '6px 0' } }, t('publish.verify.running'))
          : null,
        !verifyRunning ? h(VerifyCard, { result: verifyResult }) : null,
        h(MetaEditor, {
          article, preview,
          onApply: onApplyOverrides, onSave: onSaveOverrides,
          saving: savingMeta, saved: savedMeta, saveError: metaError,
        }),
        h(BodyEditor, {
          article, onSave: onSaveBody,
          saving: bodySaving, saved: bodySaved, error: bodyError,
        }),
        preview
          ? h('div', { className: 'wx-screen' },
              h('div', {
                className: 'wx-article',
                dangerouslySetInnerHTML: { __html: preview.html },
              }),
            )
          : h('div', { className: 'wx-empty' }, busy === 'preview' ? t('preview.loading') : t('preview.empty')),
      )
    }

    function SettingsTab(props) {
      const { settings, status, draftError } = props
      const [form, setForm] = useState(null)
      const [saving, setSaving] = useState(false)
      const [saved, setSaved] = useState(false)
      const [error, setError] = useState('')

      useEffect(() => {
        if (settings && !form) {
          setForm({
            maxContentBytes: settings.panelSettings.maxContentBytes,
            pythonBin: settings.panelSettings.pythonBin,
            themeCacheHours: settings.panelSettings.themeCacheHours,
          })
        }
      }, [settings])

      if (!settings || !form) return h('div', { className: 'wx-empty' }, t('common.idle'))

      const effective = settings.effective || {}
      const envMax = effective.maxContentBytes && settings.groups
        ? (settings.groups.flatMap((g) => g.items).find((i) => i.id === 'maxContentBytes') || {}).source === 'env'
        : false
      const envPy = effective.pythonSource === 'env'
      const credMissing = !!status && !(status.credentials.appIdSet && status.credentials.appSecretSet)

      const save = async () => {
        setSaving(true); setError(''); setSaved(false)
        try {
          await apiPost({
            action: 'saveSettings',
            settings: {
              maxContentBytes: Number(form.maxContentBytes) || 0,
              pythonBin: form.pythonBin,
              themeCacheHours: Number(form.themeCacheHours),
            },
          })
          setSaved(true)
          const next = await apiGet('settings')
          props.onSettings(next)
          setForm({
            maxContentBytes: next.panelSettings.maxContentBytes,
            pythonBin: next.panelSettings.pythonBin,
            themeCacheHours: next.panelSettings.themeCacheHours,
          })
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setSaving(false)
        }
      }

      const groups = settings.groups || []
      const sourceNote = (item) => {
        if (item.source === 'env') return t('settings.envOverride')
        if (item.source === 'missing') return t('settings.source.missing')
        return ''
      }
      return h('div', { className: 'wx-settings' },
        credMissing ? h('div', { className: 'wx-alert wx-alert-warn' }, t('settings.credMissing')) : null,
        draftError ? h('div', { className: 'wx-alert wx-alert-bad' }, draftError) : null,
        h('div', { className: 'wx-group' },
          h('h3', null, t('settings.title')),
          h('div', { className: 'wx-row' },
            h('div', { className: 'wx-field' },
              h('label', null, t('settings.field.maxContentBytes')),
              h('input', {
                className: 'wx-input', type: 'number', value: form.maxContentBytes,
                onChange: (e) => setForm({ ...form, maxContentBytes: e.target.value }),
              }),
              h('p', { className: 'wx-hint' },
                t('settings.help.maxContentBytes'),
                envMax ? h('span', { className: 'wx-ro' }, t('settings.envOverride')) : null),
            ),
          ),
          h('div', { className: 'wx-row' },
            h('div', { className: 'wx-field' },
              h('label', null, t('settings.field.pythonBin')),
              h('input', {
                className: 'wx-input', type: 'text', value: form.pythonBin,
                placeholder: effective.pythonBin || '',
                onChange: (e) => setForm({ ...form, pythonBin: e.target.value }),
              }),
              h('p', { className: 'wx-hint' },
                t('settings.help.pythonBin'),
                envPy ? h('span', { className: 'wx-ro' }, t('settings.envOverride')) : null),
            ),
          ),
          h('div', { className: 'wx-row' },
            h('div', { className: 'wx-field' },
              h('label', null, t('settings.field.themeCacheHours')),
              h('input', {
                className: 'wx-input', type: 'number', value: form.themeCacheHours,
                onChange: (e) => setForm({ ...form, themeCacheHours: e.target.value }),
              }),
            ),
          ),
          h('div', { className: 'wx-row' },
            h('div', { className: 'wx-meta-actions' },
              h('button', { className: 'wx-btn', disabled: saving, onClick: save },
                saving ? t('settings.saving') : saved ? t('settings.saved') : t('settings.save')),
              error ? h('span', { className: 'wx-hint', style: { color: 'var(--wx-danger-text)' } }, error) : null,
            ),
          ),
        ),
        groups.map((group) => h('div', { className: 'wx-group', key: group.id },
          h('h3', null, tOr(`settings.group.${group.id}`, group.label)),
          group.items.map((item) => h('div', { className: 'wx-row', key: item.id },
            h('div', { className: 'wx-row-top' },
              h('label', null, item.label),
              h('span', { className: 'wx-val' }, item.value,
                sourceNote(item) ? h('span', { className: 'wx-ro' }, sourceNote(item)) : null),
            ),
          )),
        )),
      )
    }

    function DraftsTab(props) {
      const { drafts, onRefresh, busy } = props
      if (!drafts) return h('div', { className: 'wx-empty' }, busy ? '…' : t('drafts.empty'))
      return h('div', { className: 'wx-drafts' },
        h('div', { className: 'wx-summary-meta', style: { marginBottom: 4 } },
          h('span', null, t('drafts.total', { n: drafts.total })),
          h('button', { className: 'wx-linkbtn', onClick: onRefresh }, t('drafts.refresh')),
        ),
        drafts.items && drafts.items.length
          ? h('table', { className: 'wx-table' },
              h('thead', null, h('tr', null,
                h('th', null, t('drafts.title')), h('th', null, t('drafts.time')), h('th', null, t('drafts.id')))),
              h('tbody', null, drafts.items.map((item) => h('tr', { key: item.mediaId },
                h('td', null, item.title),
                h('td', { className: 'wx-mono' }, item.updateTime ? new Date(item.updateTime * 1000).toLocaleString() : '—'),
                h('td', { className: 'wx-mono' }, item.mediaId),
              ))),
            )
          : h('div', { className: 'wx-empty' }, t('drafts.empty')),
      )
    }

    function TreePane(props) {
      const {
        treePath, tree, error, loading, markdownOnly, recent, selectedPath,
        search, onSearch, onNewFile, newFileBusy,
        onNavigate, onPick, onUp, onRefresh, onToggleMarkdown,
      } = props
      const needle = (search || '').trim().toLowerCase()
      const rows = ((tree && tree.entries) || []).filter((entry) => {
        if (markdownOnly && !(entry.kind === 'directory' || entry.markdown)) return false
        if (needle && !entry.name.toLowerCase().includes(needle)) return false
        return true
      })
      const tool = (label, title, onClick, pressed) =>
        h('button', {
          key: title, className: 'wx-tool-btn', title, 'aria-label': title,
          'aria-pressed': pressed || false, onClick,
        }, label)
      return h('div', { className: 'wx-tree' },
        h('div', { className: 'wx-tree-head' },
          h('span', { title: treePath }, treePath || '—'),
          h('div', { className: 'wx-tree-tools' },
            tool(t('tree.up'), t('tree.up'), onUp),
            tool(t('tree.refresh'), t('tree.refresh'), onRefresh),
            tool('.md', t('tree.markdownOnly'), onToggleMarkdown, markdownOnly),
          ),
        ),
        h('div', { className: 'wx-tree-search' },
          h('input', {
            className: 'wx-input', type: 'text', value: search || '',
            placeholder: t('tree.search'), 'aria-label': t('tree.search'),
            onChange: (e) => onSearch(e.target.value),
          }),
        ),
        h('div', { className: 'wx-tree-new' },
          h('button', { disabled: newFileBusy, onClick: onNewFile }, `＋ ${t('tree.new')}`),
        ),
        h('div', { className: 'wx-tree-body' },
          error
            ? h('div', { className: 'wx-tree-empty' }, `${t('tree.error')}: ${error}`)
            : !tree
              ? h('div', { className: 'wx-tree-empty' }, loading ? '…' : t('tree.empty'))
              : rows.length === 0
                ? h('div', { className: 'wx-tree-empty' },
                    needle ? t('tree.emptyMatch') : t('tree.empty'))
                : rows.map((entry) => h('button', {
                    key: entry.path,
                    className: 'wx-tree-row',
                    'aria-current': entry.path === selectedPath,
                    title: entry.path,
                    onClick: () => (entry.kind === 'directory' ? onNavigate(entry.path) : onPick(entry.path)),
                  },
                    h('span', { className: 'wx-tree-dir' }, entry.kind === 'directory' ? '▸' : ''),
                    h('span', { className: 'wx-tree-name' }, entry.name),
                    entry.kind === 'file' ? h('span', { className: 'wx-tree-ext' }, entry.ext) : null,
                  )),
          tree && tree.truncated ? h('div', { className: 'wx-tree-empty' }, t('tree.truncated')) : null,
        ),
        recent && recent.length
          ? h('div', { className: 'wx-tree-recent' },
              h('h4', null, t('tree.recent')),
              recent.slice(0, 6).map((item) => h('button', {
                key: item, className: 'wx-recent-row', title: item,
                onClick: () => onPick(item),
              }, item)))
          : null,
      )
    }

    function MetaEditor(props) {
      const { article, preview, onApply, onSave, saving, saved, saveError } = props
      const [open, setOpen] = useState(false)
      const effective = (preview && preview.meta) || (article && article.effective) || {}
      const [draft, setDraft] = useState({
        title: effective.title || '', author: effective.author || '',
        digest: effective.digest || '', cover: effective.cover || '',
        literature: String(effective.literature || 'false'),
      })

      // 换文章时用生效值重置编辑稿
      useEffect(() => {
        const src = article && article.effective
        if (!src) {
          setDraft({ title: '', author: '', digest: '', cover: '', literature: 'false' })
          return
        }
        setDraft({
          title: src.title || '', author: src.author || '', digest: src.digest || '',
          cover: src.cover || '', literature: String(src.literature || 'false'),
        })
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [article && article.path])

      const set = (key) => (event) => setDraft({ ...draft, [key]: event.target.value })
      const dirty = ['title', 'author', 'digest', 'cover', 'literature']
        .some((key) => String(draft[key] || '') !== String(effective[key] || ''))

      return h('div', { className: 'wx-section' },
        h('button', { className: 'wx-section-head', onClick: () => setOpen(!open), 'aria-expanded': open },
          h('span', null, t('meta.toggle')),
          h('span', { className: 'wx-tree-ext' }, dirty ? t('meta.unsaved') : open ? '▾' : '▸'),
        ),
        open ? h('div', { className: 'wx-section-body' },
          h('div', { className: 'wx-meta-grid' },
            h('div', { className: 'wx-meta-field' },
              h('label', null, t('meta.title')),
              h('input', { className: 'wx-input', type: 'text', value: draft.title, onChange: set('title') }),
            ),
            h('div', { className: 'wx-meta-field' },
              h('label', null, t('meta.author')),
              h('input', { className: 'wx-input', type: 'text', value: draft.author, onChange: set('author') }),
            ),
            h('div', { className: 'wx-meta-field' },
              h('label', null, t('meta.digest')),
              h('input', { className: 'wx-input', type: 'text', value: draft.digest, onChange: set('digest') }),
            ),
            h('div', { className: 'wx-meta-field' },
              h('label', null, t('meta.cover')),
              h('input', {
                className: 'wx-input', type: 'text', value: draft.cover, onChange: set('cover'),
                placeholder: '/abs/path/cover.jpg',
              }),
            ),
            h('div', { className: 'wx-meta-field' },
              h('label', null, t('meta.literature')),
              h('select', {
                className: 'wx-input', value: draft.literature,
                onChange: (e) => {
                  const next = e.target.value
                  const wasOn = String(effective.literature || 'false') === 'true'
                  // 打开 literature 会删掉正文里所有表格，必须确认
                  if (next === 'true' && !wasOn && !window.confirm(t('meta.literatureWarn'))) return
                  setDraft({ ...draft, literature: next })
                },
              },
                h('option', { value: 'false' }, 'false'),
                h('option', { value: 'true' }, 'true')),
            ),
          ),
          h('div', { className: 'wx-meta-actions' },
            h('button', {
              className: 'wx-btn', disabled: !dirty, onClick: () => onApply(draft),
            }, t('meta.apply')),
            h('button', {
              className: 'wx-btn wx-btn-primary', disabled: saving || !dirty,
              onClick: () => onSave(draft),
            }, saving ? t('meta.saving') : saved ? t('meta.saved') : t('meta.save')),
            saveError ? h('span', { className: 'wx-hint', style: { color: 'var(--wx-danger-text)' } }, saveError) : null,
          ),
        ) : null,
      )
    }

    function VerifyCard(props) {
      const { result } = props
      if (!result) return null
      const ok = result.passed
      const details = result.details || {}
      const got = details.got || {}
      const extras = details.extras || {}
      return h('div', { className: ok ? 'wx-verify wx-verify-ok' : 'wx-verify wx-verify-bad' },
        h('div', null, ok ? `✓ ${t('publish.verify.pass')}` : `✕ ${t('publish.verify.fail')}`),
        ok
          ? null
          : h('ul', null, (result.failures || []).map((f, i) => h('li', { key: i }, f))),
        h('dl', { className: 'wx-facts' },
          h('div', null, h('dt', null, t('drafts.title')), h('dd', null, details.title || '—')),
          h('div', null, h('dt', null, t('publish.stats')), h('dd', null,
            `${details.contentBytes || 0} B, h2 ${got.h2 || 0}, svg ${extras['<svg'] || 0}, img ${got.img || 0}`)),
        ),
      )
    }

    function BodyEditor(props) {
      const { article, onSave, saving, saved, error } = props
      const [open, setOpen] = useState(false)
      const [text, setText] = useState(null)
      const [loading, setLoading] = useState(false)
      const [loadError, setLoadError] = useState('')

      const openEditor = async () => {
        setOpen(true)
        setLoadError('')
        if (text !== null) return
        setLoading(true)
        try {
          const payload = await apiGet('body', { path: article.path })
          setText(payload.body)
        } catch (err) {
          setLoadError(String(err.message || err))
        } finally {
          setLoading(false)
        }
      }

      if (!open) {
        return h('div', { className: 'wx-section' },
          h('button', { className: 'wx-section-head', onClick: openEditor },
            h('span', null, t('editor.open')),
            h('span', { className: 'wx-tree-ext' }, '▸'))
        )
      }

      return h('div', { className: 'wx-section' },
        h('div', { className: 'wx-section-head' },
          h('span', null, t('editor.body')),
          h('button', { className: 'wx-icon-btn', onClick: () => setOpen(false) }, '✕'),
        ),
        h('div', { className: 'wx-section-body' },
          h('div', { className: 'wx-meta-actions' },
            h('button', {
              className: 'wx-btn wx-btn-primary', disabled: saving,
              onClick: () => onSave(text),
            }, saving ? t('editor.saving') : saved ? t('editor.saved') : t('editor.save')),
            h('span', { className: 'wx-kbd' }, t('editor.chars', { n: (text || '').length })),
            error ? h('span', { className: 'wx-hint', style: { color: 'var(--wx-danger-text)' } }, error) : null,
          ),
          h('div', { className: 'wx-editor' },
            loading
              ? h('div', { className: 'wx-tree-empty' }, '…')
              : h('textarea', {
                  value: text || '',
                  spellCheck: false,
                  placeholder: '',
                  onChange: (e) => setText(e.target.value),
                }),
          ),
          loadError ? h('p', { className: 'wx-hint' }, loadError) : null,
        ),
      )
    }

    function Panel() {
      const [tab, setTab] = useState('preview')
      const [path, setPath] = useState(() => {
        try { return window.localStorage.getItem(STORAGE_KEY) || '' } catch { return '' }
      })
      const [article, setArticle] = useState(null)
      const [preview, setPreview] = useState(null)
      const [settings, setSettings] = useState(null)
      const [status, setStatus] = useState(null)
      const [drafts, setDrafts] = useState(null)
      const [job, setJob] = useState(null)
      const [busy, setBusy] = useState('')
      const [error, setError] = useState('')
      const [arm, setArm] = useState(false)
      // 内容覆盖：面板不提任何内容要求，缺什么就补什么
      const [overrides, setOverrides] = useState({})
      const [savingMeta, setSavingMeta] = useState(false)
      const [savedMeta, setSavedMeta] = useState(false)
      const [metaError, setMetaError] = useState('')
      // 文件树
      const [showTree, setShowTree] = useState(true)
      const [treeRoots, setTreeRoots] = useState([])
      const [treeDefault, setTreeDefault] = useState('')
      const [home, setHome] = useState('')
      const [treePath, setTreePath] = useState('')
      const [tree, setTree] = useState(null)
      const [treeError, setTreeError] = useState('')
      const [treeLoading, setTreeLoading] = useState(false)
      const [treeHidden, setTreeHidden] = useState(false)
      const [treeMarkdownOnly, setTreeMarkdownOnly] = useState(true)
      const [treeSearch, setTreeSearch] = useState('')
      const [newFileBusy, setNewFileBusy] = useState(false)
      const [recent, setRecent] = useState([])
      // 发布后自检 / 重复草稿 / 正文编辑
      const [verifyResult, setVerifyResult] = useState(null)
      const [verifyRunning, setVerifyRunning] = useState(false)
      const [duplicateAsk, setDuplicateAsk] = useState(false)
      const [forceDuplicate, setForceDuplicate] = useState(false)
      const [bodySaving, setBodySaving] = useState(false)
      const [bodySaved, setBodySaved] = useState(false)
      const [bodyError, setBodyError] = useState('')
      const [dark, setDark] = useState(hostIsDark)

      // 跟随宿主主题切换亮/暗色（宿主改令牌时重新探测）
      useEffect(() => {
        const probe = () => setDark(hostIsDark())
        const media = window.matchMedia('(prefers-color-scheme: dark)')
        const onMedia = () => probe()
        const onVisible = () => { if (!document.hidden) probe() }
        if (media.addEventListener) media.addEventListener('change', onMedia)
        document.addEventListener('visibilitychange', onVisible)
        const timer = setInterval(probe, 2000)
        return () => {
          if (media.removeEventListener) media.removeEventListener('change', onMedia)
          document.removeEventListener('visibilitychange', onVisible)
          clearInterval(timer)
        }
      }, [])
      const armTimer = useRef(null)
      const pollTimer = useRef(null)

      const loadSettings = useCallback(async () => {
        try {
          const [settingPayload, statusPayload, rootsPayload, recentPayload] = await Promise.all([
            apiGet('settings'),
            apiGet('status'),
            apiGet('roots'),
            apiGet('recent'),
          ])
          setSettings(settingPayload)
          setStatus(statusPayload)
          setTreeRoots(rootsPayload.roots || [])
          setTreeDefault(rootsPayload.default || (rootsPayload.roots || [])[0] || '')
          setHome(rootsPayload.home || '')
          setRecent(recentPayload.recent || [])
        } catch (err) {
          setError(String(err.message || err))
        }
      }, [])

      const openTreeDir = useCallback(async (dir, hiddenOverride) => {
        const target = dir || treeDefault
        if (!target) return
        const showHidden = hiddenOverride === undefined ? treeHidden : hiddenOverride
        setTreeLoading(true); setTreeError('')
        try {
          const payload = await apiGet('tree', { path: target, hidden: showHidden ? '1' : '' })
          setTree(payload)
          setTreePath(payload.path)
          try { window.localStorage.setItem(TREE_STORAGE_KEY, payload.path) } catch { /* private mode */ }
        } catch (err) {
          setTreeError(String(err.message || err))
        } finally {
          setTreeLoading(false)
        }
      }, [treeDefault, treeHidden])

      useEffect(() => {
        loadSettings()
        return () => {
          if (armTimer.current) clearTimeout(armTimer.current)
          if (pollTimer.current) clearInterval(pollTimer.current)
        }
      }, [loadSettings])

      // 文件树定时刷新：外部新建/改名能自动出现
      useEffect(() => {
        if (!showTree || !treePath) return undefined
        const timer = setInterval(() => {
          if (!document.hidden) openTreeDir(treePath, treeHidden).catch(() => {})
        }, 30000)
        return () => clearInterval(timer)
      }, [showTree, treePath, treeHidden, openTreeDir])

      // 首次打开文件树：上次浏览的位置 → 当前文章所在目录 → 用户主目录 → 允许的根
      useEffect(() => {
        if (treePath || !treeDefault) return
        let initial = treeDefault
        try {
          const last = window.localStorage.getItem(TREE_STORAGE_KEY)
          if (last) initial = last
        } catch { /* private mode */ }
        if (!initial && article && article.path) initial = article.path.replace(/\/[^/]*$/, '')
        if (!initial && home) initial = home
        if (initial) openTreeDir(initial)
      }, [treeDefault, treePath, article, home, openTreeDir])

      const stopPoll = useCallback(() => {
        if (pollTimer.current) { clearInterval(pollTimer.current); pollTimer.current = null }
      }, [])

      const load = useCallback(async (target) => {
        const file = target || path
        if (!file) return
        setBusy('article'); setError(''); setMetaError(''); setSavedMeta(false)
        setVerifyResult(null); setVerifyRunning(false)
        setDuplicateAsk(false); setForceDuplicate(false)
        setBodySaved(false); setBodyError('')
        try {
          const params = { path: file }
          for (const [key, value] of Object.entries(overrides)) {
            if (value !== undefined && value !== null && String(value).trim()) params[key] = value
          }
          const [articlePayload, previewPayload] = await Promise.all([
            apiGet('article', params),
            apiGet('preview', params),
          ])
          setArticle(articlePayload)
          setPreview(previewPayload)
          setJob(null)
          try { window.localStorage.setItem(STORAGE_KEY, file) } catch { /* private mode */ }
          const recentPayload = await apiGet('recent')
          setRecent(recentPayload.recent || [])
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy('')
        }
      }, [path, overrides])

      const refreshPreview = useCallback(async () => {
        if (!article) return
        setBusy('preview'); setError('')
        try {
          const params = { path: article.path }
          for (const [key, value] of Object.entries(overrides)) {
            if (value !== undefined && value !== null && String(value).trim()) params[key] = value
          }
          setPreview(await apiGet('preview', params))
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy('')
        }
      }, [article, overrides])

      const loadDrafts = useCallback(async () => {
        setBusy('drafts'); setError('')
        try {
          setDrafts(await apiGet('drafts'))
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy('')
        }
      }, [])

      useEffect(() => {
        if (tab === 'drafts') loadDrafts()
      }, [tab, loadDrafts])

      const applyOverrides = useCallback(async (draft) => {
        const next = {
          title: draft.title || '', author: draft.author || '', digest: draft.digest || '',
          cover: draft.cover || '', literature: draft.literature || 'false',
        }
        setOverrides(next)
        setSavedMeta(false)
        if (!article) return
        setBusy('preview'); setError('')
        try {
          const params = { path: article.path }
          for (const [key, value] of Object.entries(next)) {
            if (value !== undefined && value !== null && String(value).trim()) params[key] = value
          }
          setPreview(await apiGet('preview', params))
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy('')
        }
      }, [article])

      const saveOverrides = useCallback(async (draft) => {
        if (!article) return
        setSavingMeta(true); setMetaError(''); setSavedMeta(false)
        try {
          await apiPost({
            action: 'saveFrontmatter',
            path: article.path,
            title: draft.title || '', author: draft.author || '', digest: draft.digest || '',
            cover: draft.cover || '', literature: draft.literature || 'false',
          })
          setSavedMeta(true)
          await load(article.path)
          // 字段已落盘，之后的预览重新以源文件为准
          setOverrides({})
        } catch (err) {
          setMetaError(String(err.message || err))
        } finally {
          setSavingMeta(false)
        }
      }, [article, load])

      const runVerify = useCallback(async (mediaId) => {
        if (!mediaId || !article) return
        setVerifyRunning(true)
        try {
          const params = { mediaId, path: article.path }
          for (const [key, value] of Object.entries(overrides)) {
            if (value !== undefined && value !== null && String(value).trim()) params[key] = value
          }
          const payload = await apiGet('verify', params)
          setVerifyResult(payload)
        } catch (err) {
          setVerifyResult({ passed: false, failures: [String(err.message || err)], details: {} })
        } finally {
          setVerifyRunning(false)
        }
      }, [article, overrides])

      const cancelJob = useCallback(async () => {
        if (!job || job.status === 'running') {
          try {
            await apiGet('cancelJob', { id: job.id })
          } catch { /* 任务可能刚好结束 */ }
          stopPoll()
          setBusy('')
        }
      }, [job, stopPoll])

      const publish = useCallback(async () => {
        if (!article) return
        if (duplicateAsk) {
          // 已经确认过重复发布，带上标记再发一次
        } else if (!arm) {
          // 第一次点击只是上膛，5 秒内再点一次才真的推送
          setArm(true)
          armTimer.current = setTimeout(() => setArm(false), 5000)
          return
        }
        setArm(false)
        if (armTimer.current) clearTimeout(armTimer.current)
        setError(''); setJob(null); setBusy('publish'); setVerifyResult(null)
        try {
          const payload = await apiPost({
            action: 'publish', path: article.path, ...overrides,
            allowDuplicate: duplicateAsk || forceDuplicate,
          })
          const started = payload.job
          setJob(started)
          stopPoll()
          pollTimer.current = setInterval(async () => {
            try {
              const latest = await apiGet('job', { id: started.id })
              setJob(latest.job)
              if (latest.job.status !== 'running') {
                stopPoll()
                setBusy('')
                if (latest.job.status === 'succeeded') {
                  loadDrafts()
                  const match = /"mediaId"\s*:\s*"([^"]+)"/.exec(latest.job.output || '')
                  await runVerify(match ? match[1] : null)
                }
              }
            } catch (err) {
              stopPoll()
              setBusy('')
              setError(String(err.message || err))
            }
          }, 1000)
        } catch (err) {
          setBusy('')
          if (err.code === 'duplicate_draft') {
            setDuplicateAsk(true)
            setError(String(err.message || err))
            return
          }
          setError(String(err.message || err))
        }
      }, [article, arm, overrides, duplicateAsk, forceDuplicate, loadDrafts, stopPoll, runVerify])

      const saveBody = useCallback(async (text) => {
        if (!article) return
        setBodySaving(true); setBodyError(''); setBodySaved(false)
        try {
          await apiPost({ action: 'saveBody', path: article.path, body: text })
          setBodySaved(true)
          await load(article.path)
        } catch (err) {
          setBodyError(String(err.message || err))
        } finally {
          setBodySaving(false)
        }
      }, [article, load])

      const createFile = useCallback(async () => {
        setNewFileBusy(true); setError('')
        try {
          // 不询问文件名：由服务端生成不冲突的「未命名.md」
          const payload = await apiGet('createFile', { dir: treePath || treeDefault, name: '' })
          const dir = payload.path.replace(/\/[^/]*$/, '')
          setTreePath(dir)
          await openTreeDir(dir)
          await load(payload.path)
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setNewFileBusy(false)
        }
      }, [treePath, treeDefault, openTreeDir, load])

      // 面板会补全标题与兜底封面，因此唯一的硬性门槛是凭据齐备。
      const canPublish = !!article && !!status && status.credentials.appIdSet && status.credentials.appSecretSet

      return h('div', { className: dark ? 'wx-panel wx-dark' : 'wx-panel' },
        h('div', { className: 'wx-head' },
          h('div', { className: 'wx-head-top' },
            h('h2', { className: 'wx-title' }, t('panel.title')),
            job && job.status === 'running'
              ? h('button', { className: 'wx-btn wx-btn-quiet', onClick: cancelJob }, t('publish.cancel'))
              : null,
            h('button', {
              className: duplicateAsk || arm ? 'wx-btn wx-btn-danger' : 'wx-btn wx-btn-primary',
              disabled: !canPublish || busy === 'publish',
              onClick: publish,
            }, busy === 'publish'
              ? t('publish.running')
              : duplicateAsk ? t('publish.duplicate')
                : arm ? t('publish.arm') : t('publish.button')),
          ),
          h('div', { className: 'wx-source' },
            h('input', {
              className: 'wx-input', type: 'text', value: path,
              placeholder: t('path.placeholder'),
              'aria-label': t('path.label'),
              onChange: (e) => setPath(e.target.value),
              onKeyDown: (e) => { if (e.key === 'Enter') load() },
            }),
            h('button', {
              className: 'wx-btn wx-btn-quiet',
              disabled: busy === 'article' || !path,
              onClick: () => load(),
            }, t('path.load')),
            tab === 'preview'
              ? h('button', {
                  className: 'wx-btn wx-btn-quiet', 'aria-pressed': showTree,
                  onClick: () => setShowTree(!showTree),
                }, t('tree.toggle'))
              : null,
          ),
          error && !duplicateAsk ? h('div', { className: 'wx-err' }, error) : null,
          duplicateAsk ? h('div', { className: 'wx-warn' }, t('publish.duplicateWarn')) : null,
        ),
        h('div', { className: 'wx-tabs' },
          [['preview', t('tab.preview')], ['drafts', t('tab.drafts')], ['settings', t('tab.settings')]]
            .map(([id, label]) =>
              h('button', {
                key: id, className: id === tab ? 'wx-tab wx-tab-on' : 'wx-tab',
                onClick: () => setTab(id),
              }, label)),
        ),
        h('div', { className: 'wx-main' },
          showTree && tab === 'preview'
            ? h(TreePane, {
                treePath, tree, error: treeError, loading: treeLoading,
                hidden: treeHidden, markdownOnly: treeMarkdownOnly,
                recent, selectedPath: article && article.path,
                search: treeSearch, onSearch: setTreeSearch,
                onNewFile: createFile, newFileBusy,
                onNavigate: openTreeDir,
                onPick: (p) => { setPath(p); load(p) },
                onUp: () => { if (tree && tree.parent) openTreeDir(tree.parent) },
                onRefresh: () => openTreeDir(treePath || treeDefault),
                onToggleMarkdown: () => setTreeMarkdownOnly(!treeMarkdownOnly),
              })
            : null,
          h('div', { className: 'wx-body' },
            tab === 'preview'
              ? h(PreviewTab, {
                  article, preview, busy, job,
                  onApplyOverrides: applyOverrides,
                  onSaveOverrides: saveOverrides,
                  savingMeta, savedMeta, metaError,
                  onRefreshPreview: refreshPreview,
                  onSaveBody: saveBody,
                  bodySaving: bodySaving, bodySaved: bodySaved, bodyError: bodyError,
                  verifyResult, verifyRunning,
                })
              : null,
            tab === 'settings'
              ? h(SettingsTab, { settings, status, draftError: error, onSettings: setSettings })
              : null,
            tab === 'drafts'
              ? h(DraftsTab, { drafts, busy: busy === 'drafts', onRefresh: loadDrafts })
              : null,
          ),
        ),
      )
    }

    // ------------------------------------------------------------ exports ------
    exports.name = 'dsh-wechat-publish'
    exports.inject = ['slots', 'locale']
    exports.apply = function apply(ctx) {
      ctx.effect(() => {
        const tag = document.createElement('style')
        tag.dataset.plugin = 'dsh-wechat-publish'
        tag.textContent = CSS
        document.head.appendChild(tag)
        return () => { tag.remove() }
      }, 'dsh-wechat-publish: styles')

      ctx.inject(['locale'], (scope) => {
        try { scope.locale.register(LOCALE_NS, LOCALES) } catch { /* 缺字典不是致命错误 */ }
        try {
          const snapshot = scope.locale.getSnapshot && scope.locale.getSnapshot()
          const active = snapshot && snapshot.active
          if (active) activeLang = String(active).toLowerCase().startsWith('zh') ? 'zh' : 'en'
        } catch { /* 保留浏览器语言 */ }
        try {
          return scope.on('locale/change', (next) => {
            const active = next && next.active
            if (active) activeLang = String(active).toLowerCase().startsWith('zh') ? 'zh' : 'en'
          })
        } catch { return undefined }
      })

      ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
        name: 'sidebar.panellist', id: PANEL_ID, order: 9, label: () => t('nav'),
      }, SidebarIcon))

      ctx.slots.inject('main', () => ctx.slots.register({
        name: 'main', key: PANEL_ID,
      }, Panel))
    }

    return module.exports
  },
})
