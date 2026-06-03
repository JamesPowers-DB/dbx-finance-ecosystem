# Databricks brand palette (for dashboards + visuals)

Canonical hex values (mirrored from the app design system `apps/spend-analytics/frontend/public/ds/colors_and_type.css`, which is derived from the Databricks Extended Brand Guidelines). Use **shades of one family** for a series and the **opposing accent (Lava red)** to spotlight the focus metric.

## Core
| Token | Hex | Use |
|---|---|---|
| Lava 600 | `#FF3621` | **Primary accent / focus** (the one thing to look at) |
| Lava 700 | `#CC2B1A` | accent dark / danger |
| Lava 300 | `#FABFBA` | accent tint |
| Navy 900 | `#0B2026` | darkest base / text-on-light headers |
| Navy 800 | `#1B3139` | primary dark / series base |
| Navy 700 | `#243B44` | series shade |
| Navy 400 | `#7A99A6` | muted series / secondary |
| Navy 300 | `#C4CCD6` | light series / gridlines |
| Oat Light | `#F9F7F4` | page background |
| Oat Medium | `#EEEDE9` | subtle panel |
| White | `#FFFFFF` | canvas |

## Secondary (use sparingly, single-hue ramps)
| Token | Hex |
|---|---|
| Yellow 600 / 700 / 300 | `#FFAB00` / `#CC8A00` / `#FFDB96` |
| Green 700 / 300 | `#0B6B3B` / `#9ED6C4` |
| Blue 700 / 300 | `#04355D` / `#BAE1FC` |
| Maroon 700 / 300 | `#4A121A` / `#D69EA8` |
| Gray text / lines | `#5A6F77` / `#DCE0E2` |

## Dashboard convention used here
- **Managed spend** (the good outcome) → Navy ramp (`#1B3139` → `#7A99A6`).
- **Unmanaged / off-contract tail** (the problem to spotlight) → **Lava `#FF3621`** accent.
- Trend lines / ratios overlaid on bars → Lava `#FF3621`.
- Source: https://brandguides.brandfolder.com/databricks-extended-brand-guidelines/colors
