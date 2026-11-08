#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 Swiftfin 打 Emby 适配补丁。
用法： python3 patch_swiftfin.py <swiftfin_repo_root>

必需项失败 -> 退出码 1（宁可不编译，也不出半截包）
可选项失败 -> 警告，继续
"""

import os
import shutil
import sys

G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; N = "\033[0m"
def ok(m):   print(f"{G}[+]{N} {m}")
def warn(m): print(f"{Y}[!]{N} {m}")
def err(m):  print(f"{R}[x]{N} {m}")

EMBYCOMPAT_DST_REL = "Shared/Extensions/JellyfinAPI/EmbyCompat.swift"

# 内联的 EmbyCompat.swift，外部文件缺失时用这份
EMBYCOMPAT_INLINE = r"""//
// EmbyCompat.swift
// 新增文件 —— 放在 Swiftfin 的 `Shared/Extensions/JellyfinAPI/` 目录下
// Swiftfin is subject to the terms of the Mozilla Public License, v2.0.
//

import Foundation
import JellyfinAPI
import Logging

/// 服务器类型。Emby 与 Jellyfin 在 `/System/Info/Public` 的 `ProductName` 上可区分。
enum EmbyServerKind: String, Codable, Sendable {
    case jellyfin
    case emby
}

struct EmbyServerProbe: Sendable {
    let url: URL
    let kind: EmbyServerKind
    let info: PublicSystemInfo
}

enum EmbyCompatError: LocalizedError {
    case unreachable
    case badResponse(Int)
    case decode

    var errorDescription: String? {
        switch self {
        case .unreachable: "无法连接服务器，请检查地址与端口（Emby 默认 8096）"
        case let .badResponse(code): "服务器返回异常状态码 \(code)"
        case .decode: "服务器响应无法解析，可能不是 Emby / Jellyfin 服务端"
        }
    }
}

/// Emby 兼容层。
///
/// Emby 与 Jellyfin 的 REST 路径基本一致，差异集中在三处：
/// 1. **路径前缀**：Emby 的 API 挂在 `/emby/` 下（根路径在多数版本也兼容，
///    但部分反代 / 旧版本只认 `/emby`）。
/// 2. **认证头**：Emby 用 `X-Emby-Authorization` + `X-Emby-Token`，
///    Jellyfin 用 `Authorization`。
/// 3. **图片鉴权**：Emby 的图片端点更依赖 query 里的 `ApiKey`，
///    裸 URL 走 header 鉴权容易 401。
///
/// 本文件负责第 1 点（前缀探测）；第 2 点在 SDK 侧补丁完成；
/// 第 3 点在 `BaseItemDto+Images.swift` 一行改动完成。
enum EmbyCompat {

    static let logger = Logger.swiftfin()

    /// Emby 默认端口
    static let defaultPort: Int = 8096

    /// 依次探测 `base` 与 `base/emby`，返回第一个可用的。
    static func resolve(
        baseURL: URL,
        accessToken: String? = nil,
        timeout: TimeInterval = 8
    ) async throws -> EmbyServerProbe {

        var candidates: [URL] = [baseURL]

        let trimmedPath = baseURL.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if trimmedPath.isEmpty {
            candidates.append(baseURL.appendingPathComponent("emby", isDirectory: false))
        } else if !trimmedPath.lowercased().hasSuffix("emby") {
            candidates.append(baseURL.appendingPathComponent("emby", isDirectory: false))
        }

        var lastError: Error = EmbyCompatError.unreachable

        for candidate in candidates {
            do {
                let info = try await fetchPublicInfo(
                    base: candidate,
                    accessToken: accessToken,
                    timeout: timeout
                )

                let productName = info.productName ?? ""
                let kind: EmbyServerKind = productName.range(of: "emby", options: .caseInsensitive) != nil
                    ? .emby
                    : .jellyfin

                logger.info(
                    "EmbyCompat resolved server",
                    metadata: [
                        "url": .string(candidate.absoluteString),
                        "kind": .string(kind.rawValue),
                        "product": .string(productName),
                        "version": .string(info.version ?? "-"),
                    ]
                )

                return EmbyServerProbe(url: candidate, kind: kind, info: info)
            } catch {
                lastError = error
                logger.debug(
                    "EmbyCompat probe failed",
                    metadata: [
                        "url": .string(candidate.absoluteString),
                        "error": .string(error.localizedDescription),
                    ]
                )
            }
        }

        throw lastError
    }

    /// GET {base}/System/Info/Public
    static func fetchPublicInfo(
        base: URL,
        accessToken: String?,
        timeout: TimeInterval
    ) async throws -> PublicSystemInfo {

        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw EmbyCompatError.unreachable
        }

        var path = components.path
        while path.hasSuffix("/") { path.removeLast() }
        components.path = path + "/System/Info/Public"

        guard let url = components.url else { throw EmbyCompatError.unreachable }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("MediaBrowser Client=\"Swiftfin\", Emby", forHTTPHeaderField: "X-Emby-Authorization")

        if let accessToken {
            request.setValue(accessToken, forHTTPHeaderField: "X-Emby-Token")
        }

        let (data, response) = try await URLSession.shared.data(for: request)

        if let http = response as? HTTPURLResponse, !(200 ..< 300).contains(http.statusCode) {
            throw EmbyCompatError.badResponse(http.statusCode)
        }

        do {
            return try JSONDecoder().decode(PublicSystemInfo.self, from: data)
        } catch {
            throw EmbyCompatError.decode
        }
    }
}"""


def write_embycompat(root):
    """返回 True 表示就绪"""
    dst = os.path.join(root, EMBYCOMPAT_DST_REL)
    if os.path.isfile(dst):
        ok("EmbyCompat.swift 已存在")
        return True

    os.makedirs(os.path.dirname(dst), exist_ok=True)

    external = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EmbyCompat.swift")
    if os.path.isfile(external):
        shutil.copyfile(external, dst)
        ok(f"新增 {EMBYCOMPAT_DST_REL}（外部文件）")
    else:
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(EMBYCOMPAT_INLINE + "\n")
        ok(f"新增 {EMBYCOMPAT_DST_REL}（内联）")
    return True


# ------------------------------------------------------------------ 规则表
# (名称, 相对路径, 原文, 替换, 必需)
RULES = [
    (
        "ConnectToServerViewModel: /emby 前缀探测",
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
        "BaseItemDto+Images: 图片走 ApiKey [main/1.1.1 写法]",
        "Shared/Extensions/JellyfinAPI/BaseItemDto/BaseItemDto+Images.swift",
        """        guard let url = client.url(with: request) else { return nil }
""",
        """        // MARK: EMBY PATCH - 图片鉴权改走 query ApiKey
        guard let url = client.url(with: request, queryAPIKey: true) else { return nil }
""",
        False,
    ),
    (
        "BaseItemDto+Images: 图片走 ApiKey [1.6.x 写法]",
        "Shared/Extensions/JellyfinAPI/BaseItemDto/BaseItemDto+Images.swift",
        """        return client.url(with: request)
""",
        """        // MARK: EMBY PATCH - 图片鉴权改走 query ApiKey
        return client.url(with: request, queryAPIKey: true)
""",
        False,
    ),
    (
        "ServerConnectionManager: 放宽 server id 校验",
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
    write_embycompat(root)

    touched = set()

    for name, rel, old, new, required in RULES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            (err if required else warn)(f"{name} -> 文件不存在，跳过：{rel}")
            if required:
                hard_fail = True
            continue

        src = open(path, encoding="utf-8").read()

        if "EMBY PATCH" in src and old not in src:
            ok(f"{name}（已打过）")
            continue

        if old not in src:
            (err if required else warn)(f"{name} -> 原文不匹配，跳过")
            if required:
                hard_fail = True
            continue

        if path not in touched:
            shutil.copyfile(path, path + ".bak")
            touched.add(path)

        cur = open(path, encoding="utf-8").read()
        open(path, "w", encoding="utf-8").write(cur.replace(old, new, 1))
        ok(name)

    if hard_fail:
        err("必需补丁未全部应用，终止")
        return 1

    print("\n补丁完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
