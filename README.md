# Shanghai Air Crawler

定时抓取上海空气质量监测站点过去 24 小时小时数据，并保存为 CSV。

## 本地运行

```bash
pip install -r requirements.txt
python sh_air_crawler.py
```

## GitHub Actions 定时运行

仓库已包含 `.github/workflows/sh-air-crawler.yml`。推送到 GitHub 后，Actions 会：

1. 每天北京时间 00:10 触发一次。GitHub Actions 的 cron 使用 UTC，因此配置为 `10 16 * * *`。
2. 安装 Python 依赖。
3. 执行 `python sh_air_crawler.py`，爬取一次并退出。
4. 将 `data/*.csv` 中新增的结果提交回仓库。

也可以在 GitHub 页面进入 `Actions -> Shanghai Air Crawler -> Run workflow` 手动触发。
