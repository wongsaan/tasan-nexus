# tasan-nexus

Nexus Mods 合集下载器。

通过 GraphQL API 下载合集，免浏览器，全自动。

[English version](README.md)

---

## 功能

- **登陆**：从浏览器自动读 cookie，不用手动 F12
- **安装合集**：备份 → 下载 → 解压 → 配置路由，一条龙
- **更新合集**：逐个查最新版，删旧下新
- **仅下载**：只要 zip，不解压，纯囤货
- **交互列表**：`list` 显示已安装合集，输编号安装、`u`+编号更新、`q` 退出

### 一些细节

- **配置预设推迟路由**：所有 mod 解压完才写 `config.json`，避免目录还没创建就写进去
- **同一 mod 页面多文件共存**：East Scarp 底下有 Remastered 和 Compatibility Fixes 两个文件，不会误删对方
- **更新按文件名匹配**：不会把 Frontier Farm 更新成 Immersive Farm，各自的版本各自查
- **跨合集去重**：两个合集有同一个 mod 同一版本，直接复制不重复下载
- **可选 mod 自动归档**：Optional 文件存 `Optional/` 子目录
- **跳过解压**：SMAPI 这种 mod 加载器没必要解压到 Mods 目录，`skip_extract` 配置一下就行

---

## 安装

```bash
git clone git@github.com:wongsaan/tasan-nexus.git
cd tasan-nexus
uv sync
```

需要 Python 3.14+ 和 [uv](https://docs.astral.sh/uv/)。

---

## 登陆

先浏览器登 [nexusmods.com](https://www.nexusmods.com/)，然后：

```bash
uv run tasan-nexus login
```

自动从 Chrome / Firefox / Safari / Edge 读 cookie，存 `nexus_cookies.json`。

> 手动方式：F12 → Application → Cookies，复制 `nexusmods_session`、`__cf_bm`、`cf_clearance` 三个值，创建 `nexus_cookies.json`：
> ```json
> [
>   {"name": "nexusmods_session", "value": "..."},
>   {"name": "__cf_bm", "value": "..."},
>   {"name": "cf_clearance", "value": "..."}
> ]
> ```

---

## 用法

```bash
# 登陆
uv run tasan-nexus login

# 安装合集（备份→下载→解压→配置路由）
uv run tasan-nexus install https://www.nexusmods.com/games/stardewvalley/collections/tckf0m/mods

# 仅下载 zip
uv run tasan-nexus download https://www.nexusmods.com/games/stardewvalley/collections/tckf0m/mods

# 更新所有已安装合集
uv run tasan-nexus update

# 交互列表
uv run tasan-nexus list
```

`install` 和 `update` 会在修改前备份整个 Mods 目录到 `Mods.backup.YYYY-MM-DD/`。

---

## 命令区别

| | download | install | update |
|---|---|---|---|
| 下载 zip | ✔ | ✔ | ✔ |
| 解压 | — | ✔ | 按 `installed` 标记 |
| 备份 | — | ✔ | 按 `installed` 标记 |
| 配置路由 | — | 推迟统一 | 推迟统一 |
| 版本来源 | 合集固定 | 合集固定 | 最新上传版 |
| 删旧 | — | — | ✔ |

---

## 配置

项目根目录放个 `config.json` 覆盖默认值，不创建就用下面的。

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

| 字段 | 说明 |
|---|---|
| `data_dir` | zip 缓存目录 |
| `cookies_file` | cookie 文件路径 |
| `game_id` | 游戏数字 ID（星露谷 = 1303） |
| `game_domain` | 游戏域名 slug |
| `game_dir` | 游戏 Mods 目录，解压目标 |
| `skip_extract` | 跳过解压的 mod 名称列表 |

---

## 文件说明

| 文件 | 说明 |
|---|---|
| `nexus_cookies.json` | 登陆态 |
| `mods_list.json` | 已安装合集注册表 `{url: {name, installed_at, updated_at, installed}}` |
| `.downloaded.json` | 合集清单 `{file_id: {name, version, optional, mod_id, file_title}}` |
| `config.json` | 用户配置（可选） |

### `.downloaded.json` 格式

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

- key = `file_id`：Nexus 每次上传的唯一 ID
- `mod_id`：Nexus mod 页面 ID
- `file_title`：文件在 mod 页面上的标题，同 `mod_id` 下不同文件靠它区分

---

## 配置预设

只含 `config.json`、没有 dll 和资源文件的 zip。不解压整个包，按 zip 内部目录路径把每个 `config.json` 写到游戏 Mods 目录对应位置。目标目录不存在就跳过。

---

## 压缩格式

| 格式 | 实现 |
|---|---|
| `.zip` | `zipfile`（Python 自带） |
| `.7z` | `py7zr`（纯 Python） |
| `.rar` | `bsdtar` / `unrar` / `7z`（自动找可用的） |

---

## 架构

```
src/nexus/
├── main.py          # CLI 入口
├── collection.py    # GraphQL：合集解析、最新版查询
├── downloader.py    # CDN 下载 + manifest 管理 + 版本检查
├── extractor.py     # 备份 + 解压 + 配置路由
├── config.py        # config.json 读取
└── modslist.py      # mods_list.json 增删改查
```
