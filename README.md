# Plotboard

![Plotboard logo](logo/logo.png)

A browser-based plotting tool for luciferase reporter assay data (or any GraphPad Prism-style grouped Excel file). Upload your data, configure every visual aspect of the figure in the sidebar, run statistics, and export publication-ready PNG / SVG / PDF — all without writing code.

---

## Quick start

**With uv (recommended):**
```bash
uv sync
uv run streamlit run app.py
```

**With conda:**
```bash
conda create -n plotboard python=3.11
conda activate plotboard
pip install -e .
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Input data format

The tool reads **Excel files (.xlsx)** laid out in the **GraphPad Prism grouped** format:

| Condition | Treatment A |  |  | Treatment B |  |  |
|---|---|---|---|---|---|---|
| Group 1 | rep1 | rep2 | rep3 | rep1 | rep2 | rep3 |
| Group 2 | … |  |  | … |  |  |

Rules:
- **Row 1** — `Condition` in cell A1; treatment names in the **first column of each group**; the remaining replicate columns in that group are left empty.
- **Rows 2+** — one row per experimental condition; numeric replicate values packed into the columns of each group.
- Replicate counts can vary between groups and between files.
- Sheets with Excel formulas (e.g. a `Normalized` sheet computing Nano/Firefly ratios) are supported — the tool reads cached values.
- Multiple sheets per workbook are supported; you switch between them with the **Sheet** selector.

---

## Sidebar reference

The top of the sidebar holds the controls you reach for constantly — the file,
the sheet, and presets — and below them five tabs grouped by what they change:
**Data** (which rows, in what order), **Plot** (the marks themselves),
**Axes**, **Text**, and **Stats**.

### 📂 Data — file & sheet (above the tabs)

| Control | Description |
|---|---|
| **Upload .xlsx file** | Drag-and-drop or click to browse. |
| **…or enter a local file path** | Type an absolute path (e.g. `C:\data\results.xlsx`) if the file is already on disk. |
| **Sheet** | Select which sheet of the workbook to plot. |

Under the selector a line reports what actually parsed — `5 conditions · 4 treatments · 3 replicates`. Check it after switching sheets: because the Prism layout is read by column position, a stray header cell shows up here as the wrong number of treatments.

---

### 💾 Presets (above the tabs)

Save and restore all visual/style settings as named presets (stored as JSON files in `.presets/`).

| Control | Description |
|---|---|
| **Preset dropdown** | Lists all saved presets. The current startup preset is marked with ★. |
| **Load** | Apply the selected preset immediately. |
| **⋯** | Popover holding the rest: save the current settings under a name, set the selected preset as the startup one, delete it, or reset every setting back to defaults. |

The **Default** preset is created automatically on first launch and always reflects the original factory settings. It cannot be accidentally overwritten — rename it if you want a customised starting point.

---

### 🔍 Data tab — filter & order

| Control | Description |
|---|---|
| **Show conditions** | Multiselect. Uncheck conditions you want to hide from the plot. Removed conditions are also excluded from statistical tests. |

---

### 📊 Plot tab

| Option | Description |
|---|---|
| **bar+strip** | Grouped bar chart with mean ± error bars, overlaid with individual data points. |
| **box+strip** | Box-and-whisker plot (IQR box, median line, no outlier markers) overlaid with data points. |
| **violin+strip** | Kernel density violin overlaid with data points. |
| **line+scatter** | One line per treatment across conditions, with an error band or bars and optional trend line. |

Settings are kept per plot type: switching to another type and back restores what you had.

### Marks, points & error bars *(Plot tab)*

| Control | Description |
|---|---|
| **Gap between groups** | Fraction of the mark's width used as a gap within one condition group. 0 = touching. Does not move the strip dots or the brackets. |
| **Opacity / Edge width / Edge colour** *(bar only)* | Bar fill transparency and outline. |
| **Error bar** *(bar and line)* | SD — standard deviation; SEM — standard error of the mean; 95 % CI — confidence interval. |
| **Cap size** | Width of the horizontal cap on the error bars (0 = no caps). |
| **Show individual data points** | Overlay a strip plot of every replicate. |
| **Dot size / Dot opacity** | Appearance of the strip dots. |

### Line options *(line+scatter only)*

| Control | Description |
|---|---|
| **X-axis spacing** | **Auto-detect** (default) uses proportional spacing when every condition label starts with a number (`0`, `2 h`, `100 nM`), otherwise equal spacing. **Numeric** and **Categorical** force one or the other. |
| **X-axis unit suffix** | Appended to tick labels that are a bare number, e.g. ` h`. |
| **X / Y tick interval** | Fixed spacing between ticks; 0 = automatic. |
| **Error style** | Shaded band or error bars. |
| **Line width / Marker / Marker size** | Line and point appearance. |
| **Trend line** | Smooth (through points), linear, polynomial 2/3, exponential, logarithmic, power law, or smoothing spline. Fit from group means or all replicates; overlay on the connecting line or replace it. |

---

### 📐 Axes tab

| Control | Description |
|---|---|
| **Log scale** | Switches the y-axis to log₁₀. Zero and negative values are excluded. |
| **Horizontal gridlines** | Draws light grid lines behind the marks. |
| **Y-axis number format** | **Auto** — matplotlib default. **Plain** — no scientific notation. **Scientific** — always ×10ⁿ. **SI prefix** — `1M`, `500k`, useful for raw luminescence counts. |
| **Y / X min & max** | Override the automatic limits; blank means automatic. |
| **Y / X tick interval** | Fixed spacing between ticks; 0 = automatic. |
| **Label rotation / size** | Tick label angle and size. Rotated labels are anchored by their right-hand end at the tick, so the end of each label sits under the group it names. |
| **Tick marks** | Expander: direction (in/out/both), major and minor length and width, and how many minor ticks sit in each interval. |
| **Axis border** | **Open (L-shape)** — top and right spines removed (default). **Full box**. **None**. |
| **Border / tick width** | Linewidth of the axis spines and tick marks. |

---

### 🏷️ Text tab

| Control | Description |
|---|---|
| **Title** | Figure title. Follows `filename · sheet` until you type something; clear it again to get a blank title. |
| **X-axis label** | Label below the x-axis. |
| **Y-axis label** | Label on the y-axis. Follows the sheet name until you edit it; clear it for no label. |
| **Legend title** | Header text of the colour legend. |
| **Show legend** | Toggle legend visibility. |
| **Legend inside** | Place the legend inside the plot area (top-right) instead of outside to the right. |

---

### 🎨 Colours *(Plot tab)*

| Control | Description |
|---|---|
| **Palette** | Choose a preset colour scheme: **iGEM** (lab default), Tab10, Viridis, Pastel, Colorblind, Set2. Select **Custom** to assign a colour to each treatment individually. |

---

### 📏 Figure size *(Plot tab)*

| Control | Description |
|---|---|
| **Preset** | Common publication sizes: single column (85 mm), 1.5 column (114 mm), double column (180 mm), a 16:9 slide, or square. Sets a starting width and height that you can then fine-tune. |
| **Width / Height** | Figure dimensions in inches. |

If the figure is too small for everything around the axes — easy to hit at a single-column width with a large font scale and the legend outside — a note appears under the plot, because labels would otherwise be clipped on export.

---

### 📈 Stats tab

| Control | Description |
|---|---|
| **Run statistical tests** | Master toggle. |
| **Test** | **t-test vs reference condition** — independent two-sample t-test comparing every (treatment, condition) pair against a chosen reference condition. **ANOVA + Tukey HSD** — one-way ANOVA followed by Tukey's honestly significant difference test for all pairwise comparisons. |
| **Compare** | **Conditions (per treatment)** — compares condition groups within each treatment. **Treatments (per condition)** — compares treatments within each condition group. **All cell means** *(two-way ANOVA only)* — every cell against every other, with a global Sidak correction, matching Prism. |
| **Reference condition** *(t-test only)* | The baseline condition all others are compared against. |
| **Show p-values instead of stars** | Label brackets with `p=0.023` / `p<0.001` instead of `*` / `***`. |
| **Show significance / Show fold change** | What to print above each bracket. With both on, the fold change (e.g. `1.7x`) sits above the significance label. |
| **Bracket line width** | Thickness of the significance bracket lines. |
| **Bracket font size** | Font size of the star / p-value text above brackets. |

Brackets are chosen in the **📋 Statistical comparisons** table below the plot: tick a row to draw it. The table is sorted by adjusted p-value, and the plot updates in the same interaction.

Significance thresholds: `***` p < 0.001 · `**` p < 0.01 · `*` p < 0.05 · `ns` p ≥ 0.05

Brackets are stacked automatically so they never overlap: non-overlapping brackets share the same height tier; overlapping brackets are pushed to higher tiers.

---

### 🔤 Typography *(Text tab)*

| Control | Description |
|---|---|
| **Font family** | sans-serif (default), serif, or monospace. |
| **Font sizing — Global scale** | A single multiplier (0.5–2.5) applied to all text elements simultaneously. |
| **Font sizing — Per element** | Set individual sizes for Title, Axis labels, Tick labels, and Legend text. |

---

### 🗂️ Data preview / Label editor

Enable **Rename labels & show raw data** in the Data tab to reveal these sections below the figure:

1. **Rename condition labels** — editable table mapping original condition names (as they appear in the Excel file) to display labels shown on the x-axis. Changes are ephemeral; the source file is never modified.
2. **Rename treatment labels** — same for treatment names shown in the legend.
3. **Summary statistics** — mean, SD, and N for every condition × treatment group.
4. **All individual values** — expandable table of the full long-format dataset.

---

## Export

A **⬇️ Download figure** button sits directly under the plot; it opens a popover with four formats:

| Button | Format | DPI |
|---|---|---|
| PNG 300 DPI | Raster | 300 |
| PNG 600 DPI | Raster | 600 |
| SVG | Vector | — |
| PDF | Vector (text editable in Illustrator / Inkscape) | — |

Each file is rendered when you click its button, not in advance, so having four formats on offer costs nothing while you are adjusting the plot.

### Background options

Inside the same popover, below the format buttons:

| Control | Description |
|---|---|
| **Transparent background** | Exports with no background fill (PNG and SVG only; PDF falls back to white). |
| **Background color** | Color picker for the figure background. Disabled when transparent is checked. Default white. |

### Batch export

The **📦 Batch export** expander generates one PNG (300 DPI) per sheet in the workbook and bundles them into a single ZIP file. All current sidebar settings are applied to every sheet — including axis limits, tick styling and line options — so the exported figures match the preview. Statistics are not run in batch mode.

---

## Panel mode

The **🔲 Panel mode** toggle at the top of the sidebar builds a single publication figure containing several plots in a grid. Click a panel button to edit that slot: the ordinary Data / Plot / Style / Stats tabs then apply to it. Each slot keeps its own sheet, condition filter, ordering, styling and significance brackets, and can be set to *Empty* to leave a gap for a figure you will paste in later. Panel labels (A B C…, i ii iii…, or your own text), grid size, figure size and spacing are under **Layout**.

Batch export is hidden in panel mode — it produces one figure per sheet, which has no meaning for a composed panel.

---

## Project structure

```
app.py        # Entry point — loads the workbook and assembles the figure
settings.py   # Durable store for every sidebar setting
figspec.py    # Settings → plotting arguments (shared by preview, panels, batch)
dataio.py     # Cached workbook access + DataFrame reshaping
parser.py     # Excel → tidy long-format DataFrame
plotter.py    # DataFrame → matplotlib Figure
panel.py      # Multi-panel figure composition
stats.py      # Statistical tests + significance bar drawing
presets.py    # Settings schema + preset files
utils.py      # Colour palettes, figure export helpers
ui/           # All Streamlit widgets, one module per sidebar tab
tests/        # Regression suite
data/         # Example files (E24_Analysis.xlsx, 2025-09-22_results_F43.xlsx)
```

---

## Requirements

```
streamlit>=1.41
pandas>=2.0
openpyxl>=3.1
matplotlib>=3.7
seaborn>=0.13
scipy>=1.10
pingouin>=0.5
numpy>=1.24
```

Install everything at once:

```bash
pip install -e .
# or
pip install -r requirements.txt
```

## Tests

```bash
python tests/test_regressions.py     # no pytest required
# or
pip install -e ".[dev]" && pytest
```
