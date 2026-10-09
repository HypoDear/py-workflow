# py-workflow

个人 Python 脚本集。每个脚本均为纯标准库实现，统一暴露 `main(params)` 入口，便于接入工作流按需调用。

## 脚本清单

| 脚本 | 用途 |
|---|---|
| `amap-poi.py` | 高德地图 POI 搜索，支持关键词检索与「附近/周边」定位搜索，自动清洗口语化噪音词 |
| `amap-travel.py` | 高德地图路线规划，自动识别驾车/公交/步行/骑行方式并解析起终点 |
| `flac-kw.py` | 酷我音乐 FLAC 无损音源搜索，返回可用直链 |
| `github-read.py` | GitHub 只读查询，口语化提问自动识别意图：读文件/列目录/列仓库/搜仓库/搜代码/本周热门榜 |
| `gold-price.py` | 今日金价查询，含工作日判断与周大福金价 |
| `prompt-image.py` | 从腾讯文档表格按标题匹配并提取对应正文（提示词） |
| `short-parse.py` | 解析快手分享链接，返回无水印视频直链 |
| `weather-hour.py` | 逐小时天气预报（数据源 open-meteo） |
| `weibo-hot.py` | 微博实时热搜榜 |

## 使用

各脚本统一通过 `main(params)` 调用，`params` 为参数字典，返回结果字典（通常含 `status` 与 `content` 字段）。具体入参见各脚本内的 `main` 实现。

部分脚本需要凭证或账号信息，通过 `params` 传入，不在代码中硬编码：

| 脚本 | 参数 | 说明 |
|---|---|---|
| `github-read.py` | `token` | GitHub 个人访问令牌。读公开内容可省略（限速 60 次/时），带令牌为 5000 次/时；代码内容搜索必须提供 |
| `github-read.py` | `github_user` | 自己的 GitHub 用户名，作为 `owner` 缺省值。省略仓库归属时用它补全；显式指定的归属优先，因此仍可读他人公开仓库 |
| `github-read.py` | `query` | 整句口语提问，脚本自行解析意图，如「查一下 py-workflow 里 amap-poi 的代码」「我有哪些仓库」「本周热门」 |

`github-read.py` 仅实现 GET 请求，不提供任何写入能力。

## 许可

MIT
