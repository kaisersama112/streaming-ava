#!/usr/bin/env python3

import os
import sys

# Windows 系统代理的 ProxyOverride 含 [::1]，会导致 httpx/fastrtc 本地回环请求走代理失败。
# 另外 httpx 会把 NO_PROXY 中的 IPv6 条目转成 all://[::1] 这类 URL 模式并解析崩溃
# （Invalid port: ':1]'），因此这里同时剔除 IPv6 条目，只保留回环主机名。
for _key in ("NO_PROXY", "no_proxy"):
    _existing = os.environ.get(_key, "")
    _hosts = {
        item.strip()
        for item in _existing.split(",")
        if item.strip() and ":" not in item
    }
    _hosts.update({"localhost", "127.0.0.1"})
    os.environ[_key] = ",".join(sorted(_hosts))

if sys.platform == "win32":
    import urllib.request

    # 注册表代理值畸形（如 [::1]）会让 httpx trust_env 客户端在构造时崩溃
    # （gradio/fastrtc 内部客户端无法显式传 trust_env=False）。
    # 只保留环境变量代理，忽略注册表代理。
    urllib.request.getproxies = urllib.request.getproxies_environment

import uvicorn
from configs import settings
from app import create_app

if __name__ == "__main__":
    host = settings.server.host
    port = settings.server.port
    uvicorn.run(create_app(), host=host, port=port)
