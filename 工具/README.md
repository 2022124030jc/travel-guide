# 工具

| 能力 | 状态 | 入口 | 需要登录？ |
|---|---|---|---|
| 抖音取材 | ✅ 就绪 | `.dsh/skills/travel-guide/scripts/douyin_pick.py` | 不需要 |
| 小红书取材 | ✅ 已登录 | `.dsh/skills/travel-guide/scripts/xhs_pick.py`（依赖 `工具/xhs-mcp/start.sh`） | 已完成（账号信息只存本机） |
| 高德 API | ⚪ 待 Key | `~/.dsh/amap/key` | 不需要登录，要申请 Key |
| OSRM 路网 | ✅ 就绪 | `amap_route.py --live` | 不需要 |

## 自检

```bash
python3 工具/doctor.py
```

会打印四条腿的实时状态（抖音连通、小红书服务、高德 Key、OSRM）。

## 小红书

```bash
工具/xhs-mcp/start.sh      # 起服务，默认 http://127.0.0.1:18060（日常只需这条）
工具/xhs-mcp/login.sh      # 仅当登录失效时：弹二维码重扫
```

取材用 `xhs_pick.py`：

```bash
python3 .dsh/skills/travel-guide/scripts/xhs_pick.py \
  --keyword "成都三日游" --limit 3 --comments -o 素材/xhs.json --md 素材/xhs.md
```

- 登录态与浏览器都存在 `工具/xhs-mcp/.home`（约 370MB），删掉这个目录等于退出登录。
- 用法边界：只读、单次 ≤10 篇、页间 ≥3 秒、不建库、不存全文。

## 高德 Key

1. 打开 <https://console.amap.com/dev/key/app>，新建 Key，服务平台选 **Web 服务**
2. 完成个人实名认证（不做认证 Key 没有接口权限）
3. 存到沙箱外：
```bash
mkdir -p ~/.dsh/amap && chmod 700 ~/.dsh/amap
printf '%s' '你的KEY' > ~/.dsh/amap/key && chmod 600 ~/.dsh/amap/key
```

配好后 `doctor.py` 的高德一行会变成 OK，`route_tools.py` 的 POI / 真实耗时 / 天气全部可用。