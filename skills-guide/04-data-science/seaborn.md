# seaborn

## Where it fits in my work (say this honestly)
**seaborn is not imported in CareFlow or MedVision.** MedVision's figures (training curves, confusion matrix, reliability diagrams) are drawn with **plain Matplotlib** (`ml/src/medvision_ml/evaluation/plots.py`) to keep dependencies minimal. seaborn is built on Matplotlib, so the same figures could be made with fewer lines.

> If asked "where did you use seaborn?" → "For exploratory data analysis in notebooks/coursework — distributions, correlations, class balance. In MedVision's pipeline I used Matplotlib directly for the report figures, but a seaborn `heatmap(cm, annot=True)` is exactly the confusion matrix I produce."

---

## 30-second answer
seaborn is a statistical visualisation library on top of Matplotlib that works directly with pandas DataFrames. One function call gives attractive plots for distributions (`histplot`, `kdeplot`, `boxplot`, `violinplot`), relationships (`scatterplot`, `lineplot`, `regplot`, `pairplot`), categories (`barplot`, `countplot`) and matrices (`heatmap`), with automatic grouping by colour (`hue`) and confidence intervals.

---

## Basics you must know

```python
import seaborn as sns
import matplotlib.pyplot as plt
sns.set_theme(style="whitegrid")
```

### Figure-level vs axes-level
- **Axes-level** (`histplot`, `scatterplot`, `heatmap`, `boxplot`) draw on one Matplotlib Axes — pass `ax=`.
- **Figure-level** (`displot`, `relplot`, `catplot`, `pairplot`, `jointplot`) create their own figure with facets (`col=`, `row=`).

### Common plots
```python
sns.countplot(data=df, x="diagnosis")                          # class imbalance
sns.histplot(data=df, x="age_approx", hue="malignant", kde=True)
sns.boxplot(data=df, x="site", y="age_approx")
sns.scatterplot(data=df, x="position", y="wait_min", hue="walk_in")
sns.lineplot(data=history, x="epoch", y="val_loss")
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=classes, yticklabels=classes)
sns.heatmap(df.corr(numeric_only=True), annot=True, cmap="coolwarm", center=0)
sns.pairplot(df, hue="label")
```

### Key parameters
`data`, `x`, `y`, `hue` (colour by group), `style`, `size`, `col`/`row` (facets), `palette`, `errorbar`.

---

## How it could have been used in my projects (discussion points)

| Figure | Current (Matplotlib) | seaborn equivalent |
|---|---|---|
| MedVision confusion matrix | `ax.imshow` + manual labels | `sns.heatmap(cm, annot=True, fmt="d")` |
| MedVision class balance (nevus 1,286 vs dermatofibroma 24 in test) | Tables in the README | `sns.countplot(x="class")` |
| MedVision subgroup alert recall (men 0.95, women 0.84, ages 30–49 0.76) | Model card table | `sns.barplot(x="group", y="recall")` |
| CareFlow wait-time error by queue position | JSON results | `sns.scatterplot(x="position", y="abs_error", hue="walk_in")` |
| CareFlow emergency classifier threshold choice | Printed table (`emergency_tune`) | `sns.lineplot` of recall and false alarms vs threshold |

---

## Interview questions

**Q: seaborn vs Matplotlib?**
seaborn is a higher-level layer on Matplotlib for statistical plots with DataFrames and sensible defaults; Matplotlib gives full low-level control. You can mix them — seaborn returns Matplotlib Axes.

**Q: What does `hue` do?**
Splits the data by a categorical column and draws each group in a different colour.

**Q: How do you plot a correlation matrix?**
`sns.heatmap(df.corr(numeric_only=True), annot=True, cmap="coolwarm", center=0)`.

**Q: Figure-level vs axes-level functions?**
Figure-level create their own figure and support facets; axes-level draw into an existing Axes.
