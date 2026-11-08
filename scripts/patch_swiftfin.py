#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 Swiftfin 打 Emby 适配补丁。
用法： python3 patch_swiftfin.py <swiftfin_repo_root>

必需项失败 → 退出码 1（宁可不编译，也不出半截包）
可选项失败 → 警告，继续
"""

import os
import shutil
import sys

G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; N = "\033[0m"
def ok(m):   print(f"{G}[+]{N} {m}")
def warn(m): print(f"{Y}[!]{N} {m}")
def err(m):  print(f"{R}[x]{N} {m}")

EMBYCOMPAT_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EmbyCompat.swift")
EMBYCOMPAT_DST_REL = "Shared/Extensions/JellyfinAPI/EmbyCompat.swift"

# (名称, 相对路径, 原文, 替换, 是否必需)
RULES = [
    (
        "ConnectToServerViewModel：/emby 前缀探测",
        "Shared/ViewModels/ConnectToServerViewModel.swift",
        """        let url = parsedURL.normalizedServerConnectionURL ?? parsedURL

        guard url.host != nil else {
            throw ErrorMessage(L10n.invalidURL)
        }
""",
        """        let inputURL = parsedURL.normalizedServerConnectionURL ?? parsedURL

        guard inputURL.host != nil else {
            throw ErrorMessage(L10n.invalidURL)
        }

        // MARK: EMBY PATCH - 自动探测 Emby 的 /emby 路径前缀
        let embyProbe = try await EmbyCompat.resolve(baseURL: inputURL)
        let url = embyProbe.url
""",
        True,
    ),
    (
        "BaseItemDto+Images：图片走 ApiKey，修 Emby 封面 401",
        "Shared/Extensions/JellyfinAPI/BaseItemDto/BaseItemDto+Images.swift",
        """        guard let url = client.url(with: request) else { return nil }
""",
        """        // MARK: EMBY PATCH - 图片改走 query ApiKey，Emby / Jellyfin 都认
        guard let url = client.url(with: request, queryAPIKey: true) else { return nil }
""",
        False,
    ),
    (
        "ServerConnectionManager：放宽 server id 校验",
        "Shared/Services/ServerConnectionManager.swift",
        """        if publicInfo.id != serverID {
            throw ErrorMessage(L10n.connectionServerMismatch)
        }
""",
        """        // MARK: EMBY PATCH - Emby 重装会换 server id，降级为告警避免锁死账号
        if let remoteID = publicInfo.id, remoteID != serverID {
            Logger.swiftfin().warning(
                "Server id mismatch, continue anyway",
                metadata: [
                    "expected": .string(serverID),
                    "actual": .string(remoteID),
                ]
            )
        }
""",
        False,
    ),
]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: patch_swiftfin.py <swiftfin_repo_root>")
        return 2

    root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(os.path.join(root, "Shared")):
        err(f"{root} 不是 Swiftfin 仓库根目录（缺 Shared/）")
        return 1

    hard_fail = False

    # ---- 新增 EmbyCompat.swift
    dst = os.path.join(root, EMBYCOMPAT_DST_REL)
    if os.path.isfile(dst):
        ok("EmbyCompat.swift 已存在，跳过")
    elif not os.path.isfile(EMBYCOMPAT_SRC):
        err(f"补丁包缺少 {EMBYCOMPAT_SRC}")
        hard_fail = True
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(EMBYCOMPAT_SRC, dst)
        ok(f"新增 {EMBYCOMPAT_DST_REL}")

    # ---- 文本替换
    for name, rel, old, new, required in RULES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            (err if required else warn)(f"{name} → 文件不存在，跳过：{rel}")
            if required:
                hard_fail = True
            continue

        src = open(path, encoding="utf-8").read()

        if "EMBY PATCH" in src:
            ok(f"{name}（已打过）")
            continue

        if old not in src:
            (err if required else warn)(f"{name} → 原文不匹配，跳过：{rel}")
            if required:
                hard_fail = True
            continue

        shutil.copyfile(path, path + ".bak")
        open(path, "w", encoding="utf-8").write(src.replace(old, new, 1))
        ok(name)

    if hard_fail:
        err("必需补丁未全部应用，终止")
        return 1

    print("\n补丁完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())