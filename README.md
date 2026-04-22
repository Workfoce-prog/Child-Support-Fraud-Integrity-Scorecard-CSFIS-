# Child Support Fraud & Integrity Scorecard

This package contains a deployable Streamlit prototype for a **distance-adjusted Child Support Fraud & Integrity Scorecard**. It integrates:

- **NCP fraud and compliance risk**
- **CP integrity and reporting risk**
- **System / structural risk**
- **CP-NCP living distance** as a cross-cutting burden and integrity variable

## Files

- `app.py` - Streamlit app
- `data/mock_child_support_cases.csv` - mock case-level dataset
- `data/zip_reference.csv` - ZIP-code reference used for map points
- `county_overrides_template.json` - optional local threshold overrides
- `requirements.txt` - dependencies

## Score formulas

### NCP risk
`NCP_Risk = 0.20*Payment_Irregularity + 0.15*Income_Volatility + 0.20*Employment_Mismatch + 0.15*Arrears_Growth + 0.15*Distance_Score + 0.15*Mobility_Risk`

### CP risk
`CP_Risk = 0.25*Benefit_Overlap + 0.20*Household_Mismatch + 0.15*Income_Discrepancy + 0.20*Custody_Reporting_Flag + 0.10*Distance_Score + 0.10*Interstate_Complexity`

### System risk
`System_Risk = 0.25*Data_Lag + 0.25*Order_Accuracy_Gap + 0.20*Enforcement_Fit + 0.15*Interstate_Delay + 0.15*Distance_Burden`

### Final score
`Total_Risk = 0.40*NCP_Risk + 0.30*CP_Risk + 0.30*System_Risk`

## Distance logic

Distance is computed at the mock-data level and normalized into a score:

- `< 25 miles` -> `10`
- `25-99 miles` -> `30`
- `100-299 miles` -> `60`
- `300-999 miles` -> `80`
- `1000+ miles` -> `100`

Distance burden is then adjusted by travel burden relative to income:
`Distance_Burden = Distance_Score * (Travel_Cost_Index / Income_Level)`

## Risk bands

- `0-29` Low
- `30-59` Moderate
- `60-79` High
- `80-100` Critical

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud

1. Upload this folder to GitHub.
2. In Streamlit Cloud, choose the repo and set `app.py` as the entry point.
3. Deploy.

## Suggested next enhancements

- Connect to PRISM / MAXIS / wage interfaces
- Add PDF executive export
- Add county-level benchmark tables
- Add case notes and audit trail fields
- Replace ZIP centroid logic with GIS geocoding for production

## Notes

This is a prototype with mock data intended for demonstration, strategy, and internal design discussion.
