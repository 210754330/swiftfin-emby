#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 jellyfin-sdk-swift 注入 Emby 认证头。
用法： python3 patch_sdk.py <sdk_source_root>

幂等：已打过直接跳过。
失败条件：找不到 PassthroughAPIClientDelegate.swift，或找不到注入锚点 → 退出码 1。
"""

import os
import re
import sys

ANCHOR = re.compile(
    r'^([ \t]*)request\.addValue\(headers, forHTTPHeaderField: "Authorization"\)[ \t]*$',
    re.MULTILINE,
)

INJECT = '''
{indent}// MARK: EMBY PATCH - Emby 4.x 依赖下面两个头，Jellyfin 会忽略它们
{indent}request.addValue(headers, forHTTPHeaderField: "X-Emby-Authorization")
{indent}if let token = jellyfinClient?.accessToken {{
{indent}    request.addValue(token, forHTTPHeaderField: "X-Emby-Token")
{indent}}}
'''


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: patch_sdk.py <sdk_source_root>")
        return 2

    root = os.path.abspath(sys.argv[1])
    target = os.path.join(root, "Sources", "PassthroughAPIClientDelegate.swift")

    if not os.path.isfile(target):
        print(f"[x] 找不到 {target}")
        print("    说明 SDK 版本不是 3.x 结构，无法自动打补丁。")
        return 1

    src = open(target, encoding="utf-8").read()

    if "X-Emby-Authorization" in src:
        print("[=] SDK 已打过补丁，跳过")
        return 0

    m = ANCHOR.search(src)
    if not m:
        print("[x] 找不到 Authorization 注入锚点，SDK 源码结构已变：")
        print(f"    {target}")
        return 1

    indent = m.group(1)
    # INJECT 以换行开头，保证锚点那行之后另起一行；结尾不留空行
    injected = INJECT.format(indent=indent).rstrip("\n")

    new = src[:m.end()] + injected + src[m.end():]

    open(target + ".orig", "w", encoding="utf-8").write(src)
    open(target, "w", encoding="utf-8").write(new)

    print("[+] SDK 补丁完成：X-Emby-Authorization + X-Emby-Token")
    return 0


if __name__ == "__main__":
    sys.exit(main())