# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
uv run tasan-nexus login                 # 从浏览器自动获取 cookie
uv run tasan-nexus list                  # 交互式：编号=安装，u+编号=更新，q=退出
uv run tasan-nexus download <url>        # 只下载 zip，不解压
uv run tasan-nexus install <url>         # 完整安装（备份→下载→解压→配置路由）
uv run tasan-nexus update                # 更新所有已安装合集（按 installed 标记决定是否解压）
uv run tasan-nexus <url>                 # 等同于 install
uv run python -m nexus.main ...          # 同上，直接跑模块
```

无测试，无 lint 配置。

## 架构

```
src/nexus/
├── main.py          # CLI 入口，子命令分发
├── collection.py    # Nexus Mods GraphQL API（合集解析、最新版本查询）
├── downloader.py    # CDN 下载 + manifest 管理 + 版本检查 + 解压
├── extractor.py     # 备份 + 解压 + 配置路由（支持 zip/7z/rar）
├── config.py        # config.json 配置管理
└── modslist.py      # mods_list.json CRUD（含 installed 标记）
```

## 配置

`config.json`（可选），默认值见 `config.py`：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `data_dir` | `~/Work/Backup/StardewValley/mods` | zip 缓存目录 |
| `cookies_file` | `nexus_cookies.json` | cookie 文件路径 |
| `game_id` | `1303` | 游戏数字 ID |
| `game_domain` | `stardewvalley` | 游戏域名 slug |
| `game_dir` | `~/Library/.../MacOS/Mods` | 游戏 Mods 目录，解压目标 |
| `skip_extract` | `["SMAPI - Stardew Modding API"]` | 跳过解压的 mod 名称列表 |

## 命令区别

| | download | install | update |
|---|---|---|---|
| 下载 zip | ✔ | ✔ | ✔ |
| 解压到 game_dir | — | ✔ | 按 installed 标记 |
| 备份 Mods | — | ✔ | 按 installed 标记 |
| 配置路由 | — | ✔ (最后统一) | ✔ (最后统一) |
| 版本来源 | 合集固定 | 合集固定 | 最新上传版 |
| mods_list installed | false | true | 保持原值 |

## 数据流

### download
1. `parse_collection(url)` → GraphQL 获取合集数据
2. `sync_manifest()` → 补齐 manifest
3. `download_mod()` 逐个 → 下载 zip 到 `data_dir`

### install
1. `backup_mods()` → 备份 `game_dir`
2. 同 download 流程
3. 每个 zip 下载后 `_maybe_extract()` → 普通 mod 解压，配置预设和 `skip_extract` 列表中的 mod 跳过
4. 最后 `route_all_configs()` 按 zip 内部路径原样写入 `game_dir`

### update
1. `parse_collection(url)` + `fetch_latest_versions()` → 按 `(mod_id, file_name)` 查每个文件最新版
2. 版本对比，`remove_manifest_entry()` 删旧版，更新为新 `file_id`/`version`
3. 后续同 install（按 `installed` 标记决定是否解压）

### login
1. `browser_cookie3` 从 Chrome/Firefox/Safari 自动读 `nexusmods.com` 的 cookie
2. 保存需要的 3 个（`nexusmods_session`、`__cf_bm`、`cf_clearance`）

## 关键文件

- `nexus_cookies.json` — Nexus Mods 登录态，可通过 `login` 命令自动获取
- `mods_list.json` — 已安装合集注册表，URL → `{name, installed_at, updated_at, installed}`
- `.downloaded.json` — 合集级 manifest，`{file_id: {name, version, optional, mod_id, file_title}}`
- `config.json` — 用户配置（可选），覆盖默认值

## Manifest 格式

```json
{
  "file_id": {"name": "文件名.zip", "version": "1.2.3", "optional": false, "mod_id": "12345", "file_title": "Mod 文件标题"}
}
```

- key = `file_id`：Nexus 每次上传的唯一 ID
- `file_title`：文件在 mod 页面上的标题，同 `mod_id` 下不同文件靠它区分
- `_cleanup_same_mod()` 下载新版本时通过 `mod_id` + `file_title` 双重匹配删除旧条目，不同 `file_title` 的文件不会被误删
- `sync_manifest()` 自动给旧条目补 `file_title`

## 配置预设检测

`_is_config_preset()` 判断 zip 是否为纯配置：
- 无 `.dll`
- 无资源文件（`.png`/`.xnb`/`.tbin` 等）
- 所有非目录文件为 `.json`

配置预设不解压，由 `route_configs()` 按 zip 内部路径原样写入 `game_dir`，目标目录不存在则跳过。

## 压缩格式支持

| 格式 | 实现 |
|---|---|
| `.zip` | `zipfile`（Python 内置） |
| `.7z` | `py7zr`（纯 Python） |
| `.rar` | `bsdtar` / `unrar` / `7z`（自动查找） |
