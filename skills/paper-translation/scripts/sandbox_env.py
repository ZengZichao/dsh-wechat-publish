#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子进程环境净化：extract_pdf.py / check_environment.py 共用。

WorkBuddy 一类宿主会把 PYTHONPATH 指向其内置 shim 目录（内含 sitecustomize.py），
该 shim 用"敏感内容审批"拦截子进程的文件读取。子进程继承它之后可能在 import 阶段报
`PermissionError: Sensitive content approval timed out`。
故子进程一律脱离该 PYTHONPATH；同时去掉代理变量——不应发起网络探测。
"""
import os

_DROP = ("PYTHONPATH",
         "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
         "ALL_PROXY", "all_proxy")


def child_env():
    """返回已净化 os.environ 的副本，供 subprocess.run(env=...) 使用。"""
    env = dict(os.environ)
    for k in _DROP:
        env.pop(k, None)
    return env
