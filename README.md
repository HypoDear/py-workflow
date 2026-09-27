# py-workflow

个人 Python 脚本集。每个脚本均为纯标准库实现，统一暴露 `main(params)` 入口，便于接入工作流按需调用。

## 脚本清单

| 脚本 | 用途 |
|---|---|
| `amap-poi.py` | 高德地图 POI 搜索，支持关键词检索与「附近/周边」定位搜索，自动清洗口语化噪音词 |
| `amap-travel.py` | 高德地图路线规划，自动识别驾车/公交/步行/骑行方式并解析起终点 |
| `flac-kw.py` | 酷我音乐 FLAC 无损音源搜索，返回可用直链 |
| `gold-price.py` | 今日金价查询，含工作日判断与周大福金价 |
| `prompt-image.py` | 从腾讯文档表格按标题匹配并提取对应正文（提示词）|
| `short-parse.py` | 解析快手分享链接，返回无水印视频直链 |
| `weather-hour.py` | 逐小时天气预报（数据源 open-meteo）|
| `weibo-hot.py` | 微博实时热搜榜 |

## 使用

各脚本统一通过 `main(params)` 调用，`params` 为参数字典，返回结果字典（通常含 `status` 与 `content` 字段）。具体入参见各脚本内的 `main` 实现。
