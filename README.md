# Swiftfin + Emby → 直接出 .ipa（云端编译）

给你的是**一条流水线**，不是一段代码。你把它丢上 GitHub，它自己在免费的 macOS 机器上把 Swiftfin 编译成 `.ipa`，你下载、全能签签名、装手机。

全程你不用碰 Xcode。

---

## 0. 为什么不能直接给你一个 ipa

必须说清楚，不然你会以为我在推脱：

1. **`.ipa` 是编译产物**。里面是 ARM64 机器码，不是源码。Swift + SwiftUI + VLCKit 这套东西**只能在 macOS + Xcode 上编**。我这台是 Windows，装不了 Xcode。
2. **App Store 上扒下来的 ipa 不能签**。App Store 的包是 FairPlay 加密的，二进制被 Apple 的 DRM 锁住，你用全能签重签装上去，一启动就闪退。这也是为什么网上那些"Swiftfin ipa 下载"你可能都用不了。
3. **所以唯一正路**：找一台 macOS 编。GitHub Actions 给公开仓库**免费无限时长**的 macOS 机器 —— 这就是我给你的东西。

---

## 1. 三步出 ipa（网页操作，零工具）

### 第一步：建仓库 + 上传这几个文件

1. 打开 https://github.com/new
2. Repository name 随便写，比如 `swiftfin-emby`
3. 选 **Public**（公开仓库 Actions 免费无限；私有仓库每月只有 2000 分钟）
4. 点 **Create repository**
5. 在新页面点 **uploading an existing file**
6. 把这整个文件夹里的东西**拖进去**（注意：`.github` 这个隐藏文件夹也要拖，它是流水线本体）
7. 点 **Commit changes**

> 网页拖拽有时候会漏掉以 `.` 开头的文件夹。如果上传后发现仓库里没有 `.github/workflows/build-ipa.yml`，
> 就用第二种方法（gh CLI），或者手动新建：仓库页 → Add file → Create new file →
> 文件名输入 `.github/workflows/build-ipa.yml` → 把本文件内容粘进去。

### 第二步：跑流水线

1. 仓库页面点 **Actions** 标签
2. 左边选 **Build Emby IPA**
3. 右边点 **Run workflow** 按钮
4. `swiftfin_tag` 按你手机系统选（见下面第 4 节）
5. 点绿色 **Run workflow**

### 第三步：下载 ipa

1. 等 25~40 分钟（第一次要下 VLCKit，很慢；第二次有缓存约 10 分钟）
2. 点进那次运行记录，页面底下 **Artifacts** 里有个 `Swiftfin-Emby-ipa-x.x.x`
3. 下载下来是 zip，解压得到 `SwiftfinEmby-unsigned.ipa`
4. 传到手机，用全能签签名安装

---

## 2. 第二种上传方式（gh CLI，一条命令）

装了 [gh](https://cli.github.com/) 并且 `gh auth login` 过的话：

```bash
cd Swiftfin-Emby-IPA
gh repo create swiftfin-emby --public --source=. --remote=origin --push
```

推完自动触发（`push` 到 main 也会跑）。

---

## 3. 全能签签名要点

| 项目 | 说明 |
|---|---|
| 直接选 ipa | 全能签 → 导入 ipa → 选证书 → 签名 |
| Bundle ID | 可以随便改，比如 `com.你的名字.swiftfin`，**必须唯一**，别和已装的重名 |
| 证书类型 | 企业证书最省事（不会 7 天掉）；个人开发者证书 7 天过期 |
| 闪退检查 | 如果装完点开就退：多半是证书没覆盖所有内嵌 framework。全能签里勾上「重签所有 framework / 深度签名」再试 |
| 最低系统 | 装之前先看你手机版本够不够（第 4 节），不够直接装不上，报"此 App 需要更高版本" |

---

## 4. 版本怎么选（对号入座）

| 你手机的 iOS | 选这个 tag | 说明 |
|---|---|---|
| iOS 18 及以上 | `1.6.1`（默认） | 最新最稳，播放器/字幕/下载全齐 |
| iOS 17 | `1.3` 或 `1.4` | 1.6 要求 18，会装不上 |
| iOS 16 | `1.1.1` 或 `1.2` | |
| **iOS 15** | ⚠️ 本流水线不支持 | 只有 2022 年的 `v74` 分支是 iOS 15，代码结构完全不一样，补丁不兼容 |

不确定自己版本：设置 → 通用 → 关于本机 → 软件版本。

**iOS 15 的话直接跟我说**，我按 v74 那套 `SessionManager` 结构单独再出一条流水线，别硬套。

---

## 5. 装好之后连 Emby

1. 打开 App，如果是首次启动会进服务器连接页
2. 地址填：`http://你的内网IP:8096`
   - 不用自己加 `/emby`，代码里会自动探测
   - 外网就填域名，带 `https://`
3. 账号密码 → 登录

**验证三件事**：
- 首页媒体库有**封面图**（没图 = 图片补丁没生效）
- 点开一部片子能**起播**
- 暂停后杀掉 App 重开，首页有**继续观看**且进度对

---

## 6. 编译失败怎么办

流水线里已经做了容错（自动找 scheme、补丁幂等、失败留日志）。真失败的话：

1. 点进失败的那次运行，展开红色的那一步，看最后 30 行
2. 同时下载 `build-log-x.x.x` artifact，里面有完整 `xcodebuild` 日志
3. 把报错发我，我来定位

常见原因：

| 现象 | 原因 | 处理 |
|---|---|---|
| `原文不匹配` | 上游改了代码，锚点对不上 | 换一个 tag 重跑，或发我报错 |
| `No such module 'VLCKit'` | SPM 拉取超时 | 重跑一次，缓存会命中 |
| `Signing for "Swiftfin" requires a development team` | 无签名参数没生效 | 极少见，把 `DEVELOPMENT_TEAM=""` 那行前后日志发我 |
| `xcodebuild: error: Unable to find a destination` | Xcode 版本和 target 不匹配 | 换 tag |

---

## 7. 这套东西改了 Swiftfin 什么

| # | 文件 | 改动 |
|---|---|---|
| 1 | `jellyfin-sdk-swift/Sources/PassthroughAPIClientDelegate.swift` | 多发 `X-Emby-Authorization` + `X-Emby-Token` |
| 2 | `Swiftfin/Shared/Extensions/JellyfinAPI/EmbyCompat.swift` | **新增**：探测 `/emby` 前缀、识别 Emby/Jellyfin |
| 3 | `Swiftfin/Shared/ViewModels/ConnectToServerViewModel.swift` | 登录前调用探测 |
| 4 | `Swiftfin/Shared/Extensions/JellyfinAPI/BaseItemDto/BaseItemDto+Images.swift` | 图片 URL 带 `ApiKey` |
| 5 | `Swiftfin/Shared/Services/ServerConnectionManager.swift` | server id 不匹配降级为告警 |

播放器、字幕、多音轨、倍速、锁屏、后台播放、HDR、杜比视界、离线下载 —— **一行没动**。

许可证：Swiftfin 是 MPL-2.0，改动需以同协议开源。自己编自己用不涉及分发义务。

---

## 8. 文件清单

```
Swiftfin-Emby-IPA/
├── README.md                        ← 你正在看的
├── .github/workflows/build-ipa.yml  ← 流水线本体（在 GitHub 上跑）
└── scripts/
    ├── patch_swiftfin.py            ← 给 Swiftfin 打补丁（幂等，失败即停）
    ├── patch_sdk.py                 ← 给 SDK 打认证头补丁
    └── EmbyCompat.swift             ← 新增源码
```