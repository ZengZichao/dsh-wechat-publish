#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布全链路测试（网络全部打桩，不产生任何真实草稿/素材）。

为什么需要它：`panel_api.py publish` 是面板最关键的路径，但真实执行会往公众号
草稿箱写草稿，所以端到端从未跑过。这里把 get_token / upload_inline_image /
upload_cover / add_draft 换成桩，其余（归一化、兜底封面、渲染、内联 CSS、
图片改写、payload 组装、字段上限）全部走真实代码。

运行：插件 venv 的 python 执行本文件。
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_SCRIPTS = os.path.join(HERE, "..", "skills", "wechat-publish", "scripts")
sys.path.insert(0, os.path.abspath(SKILL_SCRIPTS))

import panel_api as A  # noqa: E402
import publish as P  # noqa: E402

WORK = tempfile.mkdtemp(prefix="wxpublish-test-")
ARTICLE = os.path.join(WORK, "plain.md")
IMAGE = os.path.join(WORK, "fig.png")

FAKE_TOKEN = "fake-access-token"
UPLOADED = []
DRAFTS = []


def _make_image():
    from PIL import Image

    Image.new("RGB", (120, 60), (20, 40, 80)).save(IMAGE)


def _make_article():
    # 故意：没有 frontmatter、没有 cover、用相对路径引用图片、超长中文标题
    title = "地热微生物群落沿环境梯度的谱系特异性代谢转录机制及其与碳氮硫循环耦合关系的多组学解析" * 2
    body = [
        f"# {title}",
        "",
        "## 摘要",
        "",
        "行内公式 $E=mc^2$。",
        "",
        "![图1](fig.png)",
        "",
        "## 结论",
        "",
        "结束。",
        "",
    ]
    with open(ARTICLE, "w", encoding="utf-8") as handle:
        handle.write("\n".join(body))


def _stub_network():
    P.get_token = lambda: FAKE_TOKEN

    def fake_upload_image(token, src):
        UPLOADED.append(("img", src))
        return "https://mmbiz.qpic.cn/fake-image"

    def fake_upload_cover(token, cover):
        UPLOADED.append(("cover", cover))
        return "fake-thumb-media-id"

    def fake_add_draft(token, article):
        DRAFTS.append(article)
        return {"media_id": "fake-draft-media-id"}

    P.upload_inline_image = fake_upload_image
    P.upload_cover = fake_upload_cover
    P.add_draft = fake_add_draft


def run_publish(extra_args=None):
    argv = ["panel_api.py", "publish", ARTICLE] + list(extra_args or [])
    sys.argv = argv
    captured = {}
    _stub_network()
    try:
        A.cmd_publish(A.argparse.Namespace(
            path=ARTICLE, title=None, author=None, digest=None, cover=None,
            literature=None, theme_cache_hours=24.0,
        ))
    except SystemExit as exc:
        captured["code"] = exc.code
    return captured


def main():
    _make_image()
    _make_article()
    source_before = open(ARTICLE, encoding="utf-8").read()

    # 主题 CSS 走磁盘缓存，避免联网
    A._install_theme_cache(24.0)

    run_publish()

    # 从 stdout 里拿 JSON（_out 直接打印）
    assert len(DRAFTS) == 1, f"add_draft 应被调用一次，实际 {len(DRAFTS)}"
    article = DRAFTS[0]

    # 1. 字段上限（R02）
    assert len(article["title"]) == 64, f"title 应为 64 字符，实际 {len(article['title'])}"
    assert len(article["author"].encode("utf-8")) <= 8, "author 超过 8 字节"
    assert len(article["digest"].encode("utf-8")) <= 120, "digest 超过 120 字节"

    # 2. 图片全部换成图床直链，且本地路径无残留
    assert article["content"].count("<img") == 1
    assert article["content"].count("mmbiz.qpic.cn") == 1
    assert WORK not in article["content"], "正文里残留本地路径"
    assert "thumb_media_id" in article and article["thumb_media_id"] == "fake-thumb-media-id"

    # 3. 兜底封面：源文件没有 cover，必须生成并上传
    covers = [src for kind, src in UPLOADED if kind == "cover"]
    assert len(covers) == 1, f"应上传一张兜底封面，实际 {covers}"
    assert os.path.isfile(covers[0]), "兜底封面文件不存在"
    assert covers[0].lower().endswith((".jpg", ".jpeg", ".png")), covers[0]

    # 4. 正文样式必须内联（R01），无 <style> 残留
    assert article["content"].count('style="') > 0, "正文没有内联样式"
    assert "<style" not in article["content"], "正文残留 <style>"

    # 5. 公式保持 SVG
    assert "<svg" in article["content"], "公式 SVG 丢失"

    # 6. 源文件未被修改
    assert open(ARTICLE, encoding="utf-8").read() == source_before, "源文件被改动了"

    print(json.dumps({
        "ok": True,
        "title_chars": len(article["title"]),
        "author_bytes": len(article["author"].encode("utf-8")),
        "digest_bytes": len(article["digest"].encode("utf-8")),
        "images": len([1 for kind, _ in UPLOADED if kind == "img"]),
        "cover": os.path.basename(covers[0]),
        "svg": article["content"].count("<svg"),
        "inline_styles": article['content'].count('style="'),
    }, ensure_ascii=False))
    print("publish pipeline test ok")


if __name__ == "__main__":
    main()
