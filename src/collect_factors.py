"""
Download daily Fama-French 5 factors (Mkt-RF, SMB, HML, RMW, CMA, RF) and the daily
momentum factor from Kenneth French's data library.

Used for (a) the risk-free rate in Sharpe ratios and excess returns, and (b) factor
regressions that check whether the insider-buying edge is just a size / value /
profitability / investment / momentum tilt in disguise.

Source: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
"""
import io
import re
import zipfile

import pandas as pd
import requests

from common import HEADERS

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"
FILES = {
    "ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "mom": "F-F_Momentum_Factor_daily_CSV.zip",
}


def parse_french_csv(text: str) -> pd.DataFrame:
    """French's CSVs have a free-text preamble, then a header row, then YYYYMMDD rows (in percent)."""
    lines = text.splitlines()
    first = next(i for i, l in enumerate(lines) if re.match(r"^\s*\d{8}\s*,", l))
    header = [c.strip() for c in lines[first - 1].split(",")]
    header[0] = "date"
    rows = []
    for l in lines[first:]:
        if not re.match(r"^\s*\d{8}\s*,", l):
            break  # end of the daily block
        rows.append([c.strip() for c in l.split(",")])
    df = pd.DataFrame(rows, columns=header)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    for c in header[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
    return df.set_index("date")


def fetch(name: str) -> pd.DataFrame:
    r = requests.get(f"{BASE}/{FILES[name]}", headers=HEADERS, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    text = z.open(z.namelist()[0]).read().decode("latin-1")
    return parse_french_csv(text)


def main():
    ff5 = fetch("ff5")
    mom = fetch("mom")
    mom.columns = ["Mom"]  # file labels it 'Mom' (older versions: 'Mom   ')
    factors = ff5.join(mom, how="inner")
    factors = factors[["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom", "RF"]]
    factors.to_csv("data/ff_factors_daily.csv", index_label="date")
    print(f"Wrote {len(factors)} daily factor rows ({factors.index.min().date()} .. {factors.index.max().date()}) "
          f"to data/ff_factors_daily.csv")


if __name__ == "__main__":
    main()
