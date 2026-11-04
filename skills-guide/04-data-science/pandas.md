# pandas

## Where it fits in my work (say this honestly)
**pandas is not imported in CareFlow or MedVision.** Tabular data there is small and handled with the standard `csv` / `json` modules, NumPy arrays and SQL:
- MedVision reads the ISIC 2019 metadata and group files with `csv.DictReader` (`ml/src/medvision_ml/data/groups.py`, `isic2019.py`) and computes metrics with NumPy/scikit-learn.
- CareFlow builds the wait-time training set straight from the database into NumPy arrays (`app/ml/dataset.py`), and analytics runs SQL over PostgreSQL views.

> If asked "where did you use pandas?" → "For exploratory analysis and coursework/Kaggle notebooks. In my two projects I deliberately kept the production code free of pandas: the data flows from SQL or CSV straight into NumPy, which keeps the containers lighter. For example, the CareFlow analytics feature returns SQL results that the UI exports to CSV, and the MedVision subgroup report — recall by sex, age and body site — is a typical `groupby` problem that I solved with plain Python and NumPy."

---

## 30-second answer
pandas is Python's library for tabular data. A **DataFrame** is a table of named columns (each a **Series**) with an index. It reads CSV/Excel/SQL/JSON/Parquet, cleans and transforms data, handles missing values, joins tables and does `groupby` aggregations — the standard tool for data exploration before modelling.

---

## Basics you must know

### Creating and inspecting
```python
import pandas as pd
df = pd.read_csv("ISIC_2019_Training_Metadata.csv")
df.head(), df.tail(), df.shape, df.info(), df.describe(), df.dtypes
df["anatom_site_general"].value_counts()
```

### Selecting
```python
df["age_approx"]                 # Series
df[["image", "sex"]]             # DataFrame
df.loc[df["sex"] == "female", "age_approx"]    # label-based
df.iloc[0:10, 0:3]                              # position-based
df.query("age_approx >= 70 and sex == 'male'")
```

### Cleaning
```python
df.isna().sum()
df["age_approx"] = df["age_approx"].fillna(df["age_approx"].median())
df = df.dropna(subset=["lesion_id"])
df = df.drop_duplicates()
df["sex"] = df["sex"].astype("category")
df = df.rename(columns={"anatom_site_general": "site"})
```

### Transforming
```python
df["age_group"] = pd.cut(df["age_approx"], bins=[0, 30, 50, 70, 120], labels=["<30", "30–49", "50–69", "70+"])
df["malignant"] = df["diagnosis"].isin(["MEL", "BCC", "SCC", "AK"])
df.apply(func, axis=1)   # avoid when a vectorised version exists
```

### GroupBy (split–apply–combine)
```python
df.groupby("age_group")["malignant"].mean()
df.groupby(["sex", "site"]).agg(n=("image", "count"), malignant_rate=("malignant", "mean"))
```

### Combining
```python
pd.merge(images, metadata, on="image", how="left")   # SQL-style joins
pd.concat([df1, df2], axis=0)
df.pivot_table(index="doctor", columns="weekday", values="wait_min", aggfunc="mean")
```

### Time series
`pd.to_datetime`, `.dt.hour`, `.dt.weekday`, `resample("D")`, rolling windows.

### Output
`df.to_csv`, `df.to_parquet`, `df.to_sql`.

### Performance tips
Vectorise instead of `apply`/loops, use `category` dtype for repeated strings, read only needed columns (`usecols`), Parquet for big files.

---

## How pandas *would* map onto my projects (good for interview discussion)

| Task in my project | How I did it | pandas version |
|---|---|---|
| MedVision subgroup recall (men 0.95, women 0.84, ages 30–49 0.76, …) | `evaluation/subgroups.py` with dictionaries and NumPy masks | `df.groupby(["sex"])` → `.apply(recall)` |
| ISIC metadata + lesion groups | `csv.DictReader`, dicts | `read_csv` + `merge` on `image` |
| CareFlow wait-time features (22 columns) | Built row by row from DB records into a NumPy array | A DataFrame from SQL with `read_sql`, then feature columns |
| CareFlow analytics (utilisation, no-show rate) | SQL over reporting views | `read_sql` + `groupby` + `pivot_table` |

---

## Interview questions

**Q: `loc` vs `iloc`?**
`loc` selects by label (index/column names, boolean masks); `iloc` by integer position.

**Q: How do you handle missing values?**
Inspect with `isna().sum()`, then drop, fill (mean/median/mode, forward-fill for time series) or add an "is missing" indicator — depending on why data is missing.

**Q: `merge` vs `concat` vs `join`?**
`merge` is a SQL-style join on columns; `concat` stacks frames along an axis; `join` merges on the index.

**Q: Why is `apply` slow?**
It calls a Python function per row; vectorised column operations run in C.

**Q: Series vs DataFrame?**
A Series is a single labelled column; a DataFrame is a table of Series sharing an index.
