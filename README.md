# CFA Dashboard — Ca' Foscari University of Venice

Real-time control panel and monitoring dashboard for the Continuous Flow Analysis (CFA) system at Ca' Foscari University of Venice. Built with Flask, Plotly Dash, and Bootstrap, it ingests 1 Hz telemetry streams from a cRIO controller, logs raw strings and experimental events to CSV, and visualizes live and historical sensor metrics.

---

## Project Structure

* `dashboard.py` — Main Flask + Dash application server (`port 8050`) and `/api/telemetry` ingestion endpoint.
* `config.xlsx` — Channel calibration file containing `Scale` and `Offset` parameters for the 24 pump channels. *(Note: The repository version contains dummy values generated for testing alongside `injection-test.py`. If `config.xlsx` is missing at startup, the application will automatically generate a default file populated with dummy parameters until custom calibration values are entered.)*
* `injection-test.py` — Simulated telemetry generator for local testing without live cRIO hardware.
* `logs/` — Auto-generated directory storing timestamped CSV telemetry logs (ignored by Git).

---

## Setup & Installation

### 1. Prerequisites
Ensure Python 3.9+ is installed on your machine.

### 2. Install Dependencies
Clone the repository and install the required Python packages:

```bash
git clone https://github.com/Daniele-Di-Bella/unive-CFA-dashboard.git
cd unive-CFA-dashboard
pip install flask dash dash-bootstrap-components pandas plotly openpyxl
```

### 3. Configure Channel Calibration
Before running live experiments, open `config.xlsx` and replace the dummy `Scale` and `Offset` values for Channels 1–24 with your actual calibration parameters.

### 4. Run the Dashboard
Start the server:
```bash
python dashboard.py
```
Open a web browser and navigate to:
* Local machine: `http://127.0.0.1:8050`
* Local network: `http://<host-ip>:8050`

To test the interface without the cRIO connected, run `python injection-test.py` in a separate terminal window.

### User Guide
#### Live KPIs & Channel Table
* Top KPI Cards: Display the latest instantaneous readings for Total Dust, Conductivity (4-channel mean in $\text{mS}$), Main Flow ($\text{ml/min}$), and Core Height ($\text{cm}$).
* Pump & Channel Metrics (Right Sidebar): Displays the current Pump RPM and calculated flow rates ($\text{RPM} \times \text{Scale} + \text{Offset}$) for all 24 channels simultaneously.

#### Time-Series Plots & Historical Inspection
The three primary trend plots (Flow and Core Height, Conductivity per Channel, and Total Dust Trend) maintain a 60-second continuously scrolling window over a 5-minute (300-point) rolling buffer:
* Inspecting Past Data: Use the range slider directly beneath a plot's x-axis (or click-and-drag across the chart) to pan backward to a specific timestamp. The view will freeze at your selected historical window without resetting when new telemetry arrives.
* Resuming Live View: Drag the range slider handle all the way to the right edge (or double-click inside the plot area) to resume real-time scrolling.
* Moving Average (`MA`): Toggle the `MA` switch on the Total Dust Trend header to show or hide the 5-second rolling moving average across the time-series plots.
* Focus On a Variable: Click on a variable name in a plot's key and that variable will be excluded. Click again and the variable will be reintroduced. Double click at the center of the plot to reintroduce all excluded variables. 

#### Event Injection
Select an event tag (`NEW BAG`, `OBS`, or `BREAK`), add an optional note, and click **Mark**. The event is written to the active CSV log and plotted as a vertical dashed red line across the time-series graphs (hover over the line to read the tag and the note).

#### Abakus Distribution
Abakus Distribution ($\mu\text{m}$) displays cumulative particle counts across 32 size bins on a logarithmic y-axis. Click Reset in the card header to zero the accumulated histogram counts.