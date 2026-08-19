from pathlib import Path
import pandas as pd

root = Path(r"H:\OptionGreeks\data\greeks")

for folder in ["INDICES", "STOCKS"]:
    print("=" * 80)
    print(folder)
    print("=" * 80)

    for file in sorted((root / folder).glob("*.csv")):
        try:
            df = pd.read_csv(file, nrows=5)

            print()
            print(file.name)
            print("Columns:")

            for c in df.columns:
                print("  ", c)

            print("Types:")
            print(df.dtypes)

        except Exception as e:
            print(file.name, e)