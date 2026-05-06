import re
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://link.sthj.sh.gov.cn/aqi"
SITE_PAGE_URL = f"{BASE_URL}/siteAqi/siteAqi.jsp?clickNum=2"
HOURLY_API_URL = f"{BASE_URL}/kqzl/KqzlSitehourlydataController/getSiteHourlyDataBySiteId.do"
OUTPUT_DIR = Path("data")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": SITE_PAGE_URL,
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

POLLUTANT_NAME_BY_ID = {
    "101": "PM2.5",
    "103": "PM10",
    "104": "O3",
    "108": "CO",
    "106": "SO2",
    "107": "NO2",
    "100": "AQI",
}


class SiteTableParser(HTMLParser):
    """Parse station rows from the rendered station AQI page."""

    def __init__(self):
        super().__init__()
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.current_site_id = None
        self.current_cells = []
        self.current_cell_parts = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "tbody":
            self.in_tbody = True
        elif self.in_tbody and tag == "tr":
            onclick = attrs_dict.get("onclick", "")
            match = re.search(r"setMap\(this,\s*'(?P<site_id>\d+)'\)", onclick)
            if match:
                self.in_tr = True
                self.current_site_id = match.group("site_id")
                self.current_cells = []
        elif self.in_tr and tag == "td":
            self.in_td = True
            self.current_cell_parts = []

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_tbody = False
        elif self.in_tr and tag == "td":
            text = " ".join("".join(self.current_cell_parts).split())
            self.current_cells.append(text)
            self.in_td = False
            self.current_cell_parts = []
        elif self.in_tr and tag == "tr":
            if self.current_site_id and len(self.current_cells) >= 10:
                self.rows.append(
                    {
                        "site_id": self.current_site_id,
                        "site_name": self.current_cells[0],
                        "quality": self.current_cells[8],
                        "primary_pollutant": self.current_cells[9],
                    }
                )
            self.in_tr = False
            self.current_site_id = None
            self.current_cells = []

    def handle_data(self, data):
        if self.in_td:
            self.current_cell_parts.append(data)


def fetch_site_page(session):
    response = session.get(SITE_PAGE_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def parse_latest_time(html):
    match = re.search(r'var\s+lstAqi\s*=\s*"(?P<lst_aqi>[^"]+)"', html)
    if not match:
        raise ValueError("未在站点页面中解析到最新更新时间 lstAqi")
    return match.group("lst_aqi")


def parse_station_list(html):
    parser = SiteTableParser()
    parser.feed(html)
    if not parser.rows:
        raise ValueError("未在站点页面中解析到监测站点列表")
    return parser.rows


def fetch_site_hourly_data(session, latest_time, site_id):
    response = session.post(
        HOURLY_API_URL,
        headers=HEADERS,
        data={"lstAqi": latest_time, "siteId": site_id},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def convert_value(aqi_item_id, value):
    if value in (None, "", "-"):
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return value

    # The website stores most pollutant concentrations as mg/m3 in JSON and
    # renders them as ug/m3 by multiplying by 1000. CO is already mg/m3.
    if aqi_item_id in {"101", "103", "104", "106", "107"}:
        return round(numeric_value * 1000, 1)
    return numeric_value


def normalize_parameter(value):
    if not value:
        return value
    return (
        str(value)
        .replace("₁", "1")
        .replace("₂", "2")
        .replace("₃", "3")
        .replace("₄", "4")
        .replace("₅", "5")
        .replace("₀", "0")
    )


def flatten_site_hourly_data(site, payload):
    rows_by_time = {}

    for aqi_item_id, records in payload.items():
        pollutant = POLLUTANT_NAME_BY_ID.get(aqi_item_id, aqi_item_id)
        for record in records:
            lst_aqi = record.get("lstAqi")
            if not lst_aqi:
                continue

            row = rows_by_time.setdefault(
                lst_aqi,
                {
                    "station_id": site["site_id"],
                    "station_name": record.get("name") or site["site_name"],
                    "monitor_time": lst_aqi,
                    "quality": site.get("quality", ""),
                    "primary_pollutant": "",
                    "PM2.5_ug_m3": None,
                    "PM10_ug_m3": None,
                    "O3_ug_m3": None,
                    "CO_mg_m3": None,
                    "SO2_ug_m3": None,
                    "NO2_ug_m3": None,
                    "AQI": None,
                },
            )

            if pollutant == "AQI":
                row["AQI"] = record.get("aqi")
                row["primary_pollutant"] = normalize_parameter(record.get("parameter")) or "-"
            elif pollutant == "PM2.5":
                row["PM2.5_ug_m3"] = convert_value(aqi_item_id, record.get("value"))
            elif pollutant == "PM10":
                row["PM10_ug_m3"] = convert_value(aqi_item_id, record.get("value"))
            elif pollutant == "O3":
                row["O3_ug_m3"] = convert_value(aqi_item_id, record.get("value"))
            elif pollutant == "CO":
                row["CO_mg_m3"] = convert_value(aqi_item_id, record.get("value"))
            elif pollutant == "SO2":
                row["SO2_ug_m3"] = convert_value(aqi_item_id, record.get("value"))
            elif pollutant == "NO2":
                row["NO2_ug_m3"] = convert_value(aqi_item_id, record.get("value"))

    return sorted(rows_by_time.values(), key=lambda item: item["monitor_time"])


def crawl_sh_air_data():
    started_at = datetime.now()
    print(f"[{started_at:%Y-%m-%d %H:%M:%S}] 开始爬取上海空气监测站点过去24小时小时数据...")

    try:
        session = requests.Session()
        html = fetch_site_page(session)
        latest_time = parse_latest_time(html)
        stations = parse_station_list(html)

        all_rows = []
        for index, station in enumerate(stations, start=1):
            payload = fetch_site_hourly_data(session, latest_time, station["site_id"])
            station_rows = flatten_site_hourly_data(station, payload)
            all_rows.extend(station_rows)
            print(
                f"  [{index:02d}/{len(stations)}] {station['site_name']} "
                f"获取 {len(station_rows)} 条小时记录"
            )
            time.sleep(0.2)

        if not all_rows:
            raise ValueError("接口返回为空，未获取到任何小时数据")

        OUTPUT_DIR.mkdir(exist_ok=True)
        save_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = OUTPUT_DIR / f"上海空气监测站点_过去24小时小时数据_{save_time}.csv"

        df = pd.DataFrame(all_rows)
        df.sort_values(["station_id", "monitor_time"], inplace=True)
        df.to_csv(filename, index=False, encoding="utf-8-sig")

        print(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 爬取完成："
            f"{len(stations)} 个站点，{len(all_rows)} 条小时数据，已保存至 {filename}"
        )
        return filename
    except Exception as exc:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 爬取异常：{exc}")
        raise


if __name__ == "__main__":
    crawl_sh_air_data()
