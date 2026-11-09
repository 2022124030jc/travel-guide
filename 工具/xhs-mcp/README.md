# xiaohongshu-mcp（已下载，未登录）

- 来源：https://github.com/xpzouying/xiaohongshu-mcp
- 版本：v2.7.3（2026-11-09 最新 release），Apache-2.0
- 本机文件：`xiaohongshu-mcp`（16MB，MCP 服务）、`xiaohongshu-login`（12MB，扫码登录）
- 平台：darwin-arm64，已实测 `--help` 正常

## 它是什么

不是"绕过登录的爬虫"，而是**用一个浏览器替你操作小红书**：内置浏览器 + 登录态 cookie + 半自动点击。
能力包括搜索笔记、读正文/评论、发笔记、点赞收藏等（工具很多，默认全开，按需只读用）。

## 在本机跑起来的两个前置

1. **沙箱写不了 `~/Library/Caches`** → 启动时用 `HOME` 重定向到工作区：
   ```bash
   D="$PWD"; HOME="$D/.home" "$D/xiaohongshu-mcp" -headless -port :18060
   ```
2. **首次运行会下载内置浏览器**（约 148MB，来源 `https://cdn.one-world.ai/browsers/`），
   只下一次。下载完成前服务不会监听端口。

## 登录（需要你本人操作）

```bash
D="$PWD"; HOME="$D/.home" "$D/xiaohongshu-login"
```
会弹出浏览器窗口显示二维码，用小红书 App 扫码。登录态存在 `$HOME` 下，后续复用。

## 风险与边界（用之前先认）

- 用的是**你本人账号**的登录态，平台用户协议禁止自动化采集，主力号有被限流/风控的可能。
- 只做只读（搜索、看笔记、看评论），**不发帖、不点赞、不关注、不评论**。
- 单次任务控制在 10 篇以内、页间 ≥3 秒，不建库、不长期存全文。
- 小红书 robots.txt 对 `*` 全站 Disallow —— 这个工具属于"平台不欢迎"的范畴，自己承担风险。
