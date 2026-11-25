# Usage Analytics / 用量分析

用一个页面查看当前环境的 Claude Code 用量。四类 Token（新输入、输出、缓存读取、缓存创建）分别展示，支持今天、最近 7、30、90 个自然日、按精确模型 ID 筛选、每日趋势和每页 25 条请求记录。默认显示最近 7 天，包含今天。

- **缓存命中率**按 Token 数计算，等于缓存读取 ÷（新输入 + 缓存读取 + 缓存创建）。分母为零时显示「—」，全期使用合计计算。
- 日期和日志时间使用运行环境的本地时区，与原生用量的日分组口径一致。日志来自原生采集器去重后的使用记录，显示时间、模型、客户端和四类计数。旧数据库的客户端显示为 `unknown`。
- 页面提供简体中文、繁体中文和英文。其他界面语言使用英文。市场标题和说明覆盖 15 种要求的语言。

## 运行方式与数据流

此扩展适用于 Cage 0.2.0 及以上、具有原生用量采集功能的 Linux guest 环境。插件通过 `python3 -B server.py` 启动，仅使用 Python 标准库及其 SQLite 模块。

固定读取环境内 `~/.local/share/cage/token-usage/counters.sqlite3` 的 `requests` 表，通过 stdio 和仅页面可调用的 MCP 工具返回数据。清单按官方 guest 规则使用 `permissions: []`，文件访问限于环境内原生用量数据库及其 SQLite 辅助文件检查。查询使用 SQLite `mode=ro` 和 `query_only`，不执行写入或迁移。报告仅在页面内存中保存，插件不读取账户、请求正文或凭据，也不接管请求或调用外部网络。远程工作台通过 Cage 自带的连接把结果显示在客户端。

「刷新」重新读取现有数据库。数据更新节奏、暂停收集和清空以原生用量统计为准。暂停后已收集的历史仍可读取，清空成功后下次读取应反映结果。数据库缺失、结构不兼容或忙碌时显示明确提示。订阅额度仍在原生账号页面查看。

## 在真实 Cage 环境验证

1. 检出本 PR 对应分支。将整个 `plugins/usage-analytics/` 目录复制到 **Cage 控制端配置目录**下的 `plugins/usage-analytics/`，默认完整路径为 `~/.claude-cage/plugins/usage-analytics/`。自定义配置或远程部署使用该控制端实际配置目录。在插件页打开总开关并点「重新加载」，确认插件已启用。
2. 启动环境，在一个允许测试的账号上发送数次普通 Claude Code 请求。打开原生用量统计并刷新，等本次采集完成。打开侧栏「Usage Analytics」，确认能看到四类计数、缓存命中率、趋势和请求记录。
3. 选择相同的自然日范围，原生界面按同一模型或全部模型、全部来源和客户端对照四类计数。展开「查看每日数值」核对当天和日期边界。选择一个模型，确认汇总、趋势和每一行都按该模型过滤。记录超过 25 条时检查上一页、下一页。
4. 如果页面仍提示不可用，在**同一个 Cage 环境**的内置终端执行下方检查。它只输出有效 UID、只读查询状态和计数表是否可读。记录权限错误的类型即可，保留现有权限设置。

   ```bash
   python3 - <<'PY'
   from pathlib import Path
   import os
   import sqlite3

   path = Path.home() / ".local/share/cage/token-usage/counters.sqlite3"
   print("uid:", os.geteuid())
   try:
       with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.4) as db:
           db.execute("PRAGMA query_only = ON")
           db.execute("SELECT 1 FROM requests LIMIT 1").fetchone()
       print("native usage table is readable")
   except sqlite3.Error as error:
       print(getattr(error, "sqlite_errorname", type(error).__name__))
   PY
   ```
5. 用测试环境验证暂停与清空。暂停后产生新用量，确认插件刷新仍显示原有历史。仅在可丢弃统计的环境执行原生清空，随后刷新插件，确认旧记录消失。恢复采集并产生新请求，确认新记录可见。通过桌面端 SSH 连接远程 Cage 时，重复安装与对照，确认页面显示的是远程环境的数据。
6. 切换浅色和深色主题，截取插件加载页、用量页面与筛选后的日志，脱敏后附在 PR 描述中。

## 开发检查

在仓库根目录运行以下命令。

```bash
python3 -B -m unittest discover -s tests -p test_usage_analytics.py
python3 scripts/build.py
python3 scripts/build.py --check
```

开发分支的归档也可解压后手动安装。官方构建脚本生成的市场索引使用官方 `main` URL，因此个人 Fork 中的归档通过上述本地安装流程验证。
