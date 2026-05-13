# tasan-nexus

Nexus Mods 合集下载器 · Collection downloader

通过 GraphQL API 下载合集，免浏览器，全自动。
Download Nexus Mods collections via GraphQL API — no browser needed.

---

## 能干什么 · Features

- **登陆 · Login**：从浏览器自动读 cookie，不用手动 F12 / Auto-read cookies from Chrome, Firefox, Safari, Edge
- **安装合集 · Install**：备份 Mods → 下载 → 解压 → 配置路由，一条龙 / Backup → download → extract → config routing
- **更新合集 · Update**：逐个查最新版，删旧下新 / Check latest versions, replace outdated files
- **仅下载 · Download**：只要 zip，不解压，纯囤货 / Download zips only, no extraction
- **交互列表 · List**：`list` 显示已安装合集，输编号安装、`u+编号` 更新、`q` 退出 / Interactive picker: number=install, u+number=update, q=quit

### 一些细节 · Details

- **配置预设推迟路由 · Deferred config routing**：所有 mod 解压完才写 `config.json`，避免目录还没创建就写进去 / Wait until all mods extracted before writing configs
- **同一 mod 页面多文件共存 · Multi-file mod pages**：East Scarp 底下有 Remastered 和 Compatibility Fixes 两个文件，不会误删对方 / Same mod_id, different files: no accidental deletion
- **更新按文件名匹配 · Update by file name**：不会把 Frontier Farm 更新成 Immersive Farm，各自的版本各自查 / Match latest version by file name, not just mod_id
- **跨合集去重 · Cross-collection dedup**：两个合集有同一个 mod 同一版本，直接复制不重复下载 / Reuse already-downloaded files across collections
- **可选 mod 自动归档 · Optional mods**：Optional 文件存 `Optional/` 子目录 / Optional mods stored in Optional/ subdirectory
- **跳过解压 · Skip extract**：SMAPI 这种 mod 加载器没必要解压到 Mods 目录，`skip_extract` 配置一下就行 / Skip extraction for mods like SMAPI

---

## 安装 · Installation

```bash
git clone git@github.com:wongsaan/tasan-nexus.git
cd tasan-nexus
uv sync
```

需要 Python 3.14+ 和 [uv](https://docs.astral.sh/uv/)。
Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

---

## 登陆 · Login

先浏览器登 [nexusmods.com](https://www.nexusmods.com/)，然后：
Log in at nexusmods.com in your browser, then:

```bash
uv run tasan-nexus login
```

自动从 Chrome / Firefox / Safari / Edge 读 cookie，存 `nexus_cookies.json`。
Auto-reads cookies from your browser and saves them.

> 手动方式 · Manual：F12 → Application → Cookies，复制 `nexusmods_session`、`__cf_bm`、`cf_clearance` 三个值：
> Copy these 3 cookies and create `nexus_cookies.json`:
> ```json
> [
>   {"name": "nexusmods_session", "value": "..."},
>   {"name": "__cf_bm", "value": "..."},
>   {"name": "cf_clearance", "value": "..."}
> ]
> ```

---

## 用法 · Usage

```bash
# 登陆 · Login
uv run tasan-nexus login

# 安装合集（备份→下载→解压→配置路由）
# Install (backup → download → extract → config routing)
uv run tasan-nexus install https://www.nexusmods.com/games/stardewvalley/collections/tckf0m/mods

# 仅下载 zip · Download only
uv run tasan-nexus download https://www.nexusmods.com/games/stardewvalley/collections/tckf0m/mods

# 更新所有已安装合集 · Update all collections
uv run tasan-nexus update

# 交互列表 · Interactive list
uv run tasan-nexus list
```

`install` 和 `update` 会在修改前备份整个 Mods 目录到 `Mods.backup.YYYY-MM-DD/`。
`install` and `update` back up the Mods directory before making changes.

---

## 命令区别 · Command Comparison

| | download | install | update |
|---|---|---|---|
| 下载 zip · Download | | | |
| 解压 · Extract | — | | by `installed` flag |
| 备份 · Backup | — | | by `installed` flag |
| 配置路由 · Config routing | — | deferred | deferred |
| 版本来源 · Version source | collection | collection | latest upload |
| 删旧 · Remove old | — | — | |

---

## 配置 · Configuration

项目根目录放个 `config.json` 覆盖默认值，不创建就用下面的。
Place `config.json` in the project root to override defaults.

```json
{
  "data_dir": "~/Work/Backup/StardewValley/mods",
  "cookies_file": "nexus_cookies.json",
  "game_id": 1303,
  "game_domain": "stardewvalley",
  "game_dir": "~/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS/Mods",
  "skip_extract": ["SMAPI - Stardew Modding API"]
}
```

| 字段 · Field | 说明 · Description |
|---|---|
| `data_dir` | zip 缓存目录 · zip cache directory |
| `cookies_file` | cookie 文件路径 · cookies file path |
| `game_id` | 游戏数字 ID（星露谷 = 1303）· numeric game ID |
| `game_domain` | 游戏域名 slug · game domain slug |
| `game_dir` | 游戏 Mods 目录，解压目标 · game Mods directory |
| `skip_extract` | 跳过解压的 mod 名称列表 · mod names to skip extraction |

---

## 文件说明 · Key Files

| 文件 · File | 说明 · Description |
|---|---|
| `nexus_cookies.json` | 登陆态 · login session |
| `mods_list.json` | 已安装合集注册表 · collection registry `{url: {name, installed_at, updated_at, installed}}` |
| `.downloaded.json` | 合集清单 · per-collection manifest `{file_id: {name, version, optional, mod_id, file_title}}` |
| `config.json` | 用户配置（可选）· user config (optional) |

### `.downloaded.json` 格式 · Format

```json
{
  "135999": {
    "name": "Frontier Farm-3753-1-15-11-1751325482.zip",
    "version": "1.15.11",
    "optional": false,
    "mod_id": "3753",
    "file_title": "Frontier Farm"
  }
}
```

- key = `file_id`：Nexus 每次上传的唯一 ID · unique upload ID on Nexus
- `mod_id`：Nexus mod 页面 ID · mod page ID
- `file_title`：文件在 mod 页面上的标题，同 `mod_id` 下不同文件靠它区分 · file title on the mod page, used to distinguish files sharing the same `mod_id`

---

## 配置预设 · Config Presets

只含 `config.json`、没有 dll 和资源文件的 zip。不解压整个包，按 zip 内部目录路径把每个 `config.json` 写到游戏 Mods 目录对应位置。目标目录不存在就跳过（对应的 mod 还没解压）。
Zips containing only `config.json` — no dlls or resource files. Instead of extracting the whole archive, each `config.json` is copied to `game_dir` using the exact path from inside the zip. Skipped if the target directory doesn't exist.

---

## 压缩格式 · Archive Support

| 格式 · Format | 实现 · Implementation |
|---|---|
| `.zip` | `zipfile`（Python 自带） |
| `.7z` | `py7zr`（纯 Python） |
| `.rar` | `bsdtar` / `unrar` / `7z`（自动找可用的） |

---

## 架构 · Architecture

```
src/nexus/
├── main.py          # CLI 入口 · entry point
├── collection.py    # GraphQL：合集解析、最新版查询 · API client
├── downloader.py    # CDN 下载 + manifest 管理 + 版本检查 · download & manifest
├── extractor.py     # 备份 + 解压 + 配置路由 · backup, extract, config routing
├── config.py        # config.json 读取 · config loader
└── modslist.py      # mods_list.json 增删改查 · registry CRUD
```
