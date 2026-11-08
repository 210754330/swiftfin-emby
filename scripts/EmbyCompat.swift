//
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
}