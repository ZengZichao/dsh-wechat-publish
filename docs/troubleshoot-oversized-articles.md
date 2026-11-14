# 处理超出体积上限的文章

面板告警「超出上限，将裁剪 N 节、保留 M 节」，或发布后回读发现章节变少，都说明正文撞上了体积上限。默认上限 512 KB，检查点在渲染之后、上传图片之前。

## 先弄清它会做什么

超限时管线调用 `trim_body()`：按标题切段，只保留标题含「摘要 / 引言 / 结论 / 讨论 / 展望 / 总结」的章节；独立图片行无论在哪个章节都保留；第一个标题之前的前言保留。裁完仍超限，就删掉全部 `<img>`。整个过程不中断，`draft/add` 仍返回成功——所以章节被删是**静默**的。

1. 看到裁剪告警，先停手，不要发布。

2. 抬高上限，让全文通过。

   在 **设置** 把 **正文体积上限（字节）** 改成 `2097152`（2 MB），保存后重新发布。

   或者在命令行发布时临时抬高（`<插件根目录>` 指 `dsh-wechat-publish/` 的绝对路径）：

   ```bash
   cd <插件根目录>/skills/wechat-publish
   WECHAT_MAX_CONTENT_BYTES=2097152 ./scripts/publish.sh "/绝对路径/article.md"
   ```

   > 提示：512 KB 是 skill 自设的保守线，不是微信硬上限。实测约 640 KB（261 个公式 SVG 加 10 张图）能正常入库。失败的 `draft/add` 只报错、不产生草稿，可以安全试推。

3. 发布前先量一次体积，别靠猜。下文的 `<SKILL_ROOT>` 指 `skills/wechat-publish` 的绝对路径。

   ```python
   import os, sys
   os.environ["WECHAT_MAX_CONTENT_BYTES"] = "2097152"   # 必须在 import 之前设，上限在导入时读取
   sys.path.insert(0, "<SKILL_ROOT>/scripts")
   import publish as P

   meta, body = P.parse_frontmatter(open("article.md", encoding="utf-8").read())
   css = P.ROOT_OVERRIDE_CSS + P.build_theme_css() + P.TABLE_OVERRIDE_CSS
   lit = str(meta.get("literature", "")).lower() in ("true", "1", "yes")
   if lit:
       body = P.strip_markdown_tables(P.normalize_special_headings(body))
   body = P.strip_leading_title(body, meta["title"])
   if lit:
       body = f'{meta["title"]}\n\n{body}'
   content = P.wrap(css, P._render_html(body, css))
   print("预内联", len(content.encode("utf-8")), "vs LIMIT", P.LIMIT,
         "| svg", content.count("<svg"), "| fallback", content.count("math-fallback"))
   ```

   量的是 `wrap()` 之后、含主题 `<style>` 的字节；真正入库的是内联之后，实测还会再高 2%–11%，别卡在临界值上赌。脚本要用插件 `.venv` 的 python 跑。

4. 微信仍拒收时，拆成多篇发布，不要回头让 `trim_body` 砍章。

5. 发布后回读核对章节数。

   ```bash
   ./scripts/draft_tools.py verify <media_id> "/绝对路径/article.md"
   ```

   比对 `<h2>` / `<h3>` 数与源文一致，确认没被裁剪。

**结果：** 草稿里的章节数与源文一致；回读自检通过；没有出现「只剩引言和孤立图片」的残缺稿。

> 提示：不要把 `trim_body` 当安全兜底。它的保留词只有六个，教材章、技术章（「第 3 章 模拟」下的 3.1、3.2）全不匹配，一触发就只剩引言段。更麻烦的是关键词按每一级标题独立判定：被删章节里冒出一个 `### 主要结论` 会重新打开保留开关，产出没有父级的碎片章节，读起来像「没砍多少」。

## 相关文章

- [排查公众号发布报错](troubleshoot-publish-errors.md)
- [清点公众号草稿箱](check-drafts.md)
- [修改面板设置](change-panel-settings.md)
- [查阅发布规则速查表](reference-publish-rules.md)
