# Shanghai Air Crawler

定时抓取上海空气质量监测站点过去 24 小时小时数据，并保存为 CSV。

## 本地运行

```bash
pip install -r requirements.txt
python sh_air_crawler.py
```

如果需要在本地常驻并每小时执行一次：

```bash
python sh_air_crawler.py --schedule
```

## GitHub Actions 定时运行

仓库已包含 `.github/workflows/sh-air-crawler.yml`。推送到 GitHub 后，Actions 会：

1. 每小时第 5 分钟触发一次，GitHub 的 cron 使用 UTC。
2. 安装 Python 依赖。
3. 执行 `python sh_air_crawler.py`，只爬取一次并退出。
4. 将 `data/*.csv` 中新增的结果提交回仓库。

也可以在 GitHub 页面进入 `Actions -> Shanghai Air Crawler -> Run workflow` 手动触发。
