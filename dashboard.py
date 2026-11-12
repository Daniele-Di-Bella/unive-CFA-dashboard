import os
import re
import csv
import datetime
import threading
from collections import deque
import pandas as pd
import flask # type: ignore
from flask import request, jsonify # type: ignore
import dash # type: ignore
from dash import dcc, html, dash_table # type: ignore
from dash.dependencies import Input, Output, State # type: ignore
import dash_bootstrap_components as dbc # type: ignore
import plotly.graph_objs as go # type: ignore

# ==========================================
# 1. CONFIGURATION & DATA STRUCTURES
# ==========================================
MAX_POINTS = 300  # 5 minutes of data at 1Hz
VIEW_WINDOW_SEC = 60  # Fixed visible seconds on x-axis for real-time scrolling
CONFIG_FILE = 'config.xlsx'

class DataStore:
    def __init__(self):
        self.lock = threading.Lock()
        
        # Raw Data Arrays
        self.timestamps = deque(maxlen=MAX_POINTS)
        self.abk_hist = [0] * 32
        self.abk_total = deque(maxlen=MAX_POINTS)
        self.cnd = [deque(maxlen=MAX_POINTS) for _ in range(4)]
        self.flw = deque(maxlen=MAX_POINTS)
        self.drw = deque(maxlen=MAX_POINTS)
        self.pmp_rpm = 0.0
        self.pmp_state = 0
        
        # Events
        self.events = deque(maxlen=20)
        
        # Calibration config
        self.scales = [1.0] * 24
        self.offsets = [0.0] * 24
        
        # Initialize Logging
        os.makedirs('logs', exist_ok=True)
        self.log_file = f"logs/telemetry_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(self.log_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Raw_String', 'Event_Tag'])

        self.load_config()

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            # Create a dummy config if none exists to prevent crashes
            df = pd.DataFrame({'Channel': range(1, 25), 'Scale': [0.1]*24, 'Offset': [0.0]*24})
            df.to_excel(CONFIG_FILE, index=False)
            print(f"Generated default {CONFIG_FILE}")

        try:
            df = pd.read_excel(CONFIG_FILE)
            for i in range(min(24, len(df))):
                self.scales[i] = float(df['Scale'].iloc[i])
                self.offsets[i] = float(df['Offset'].iloc[i])
        except Exception as e:
            print(f"Error reading config: {e}")

    def reset_histogram(self):
        with self.lock:
            self.abk_hist = [0] * 32

data_store = DataStore()

# ==========================================
# 2. FLASK SERVER & API INGESTION
# ==========================================
server = flask.Flask(__name__)

@server.route('/api/telemetry', methods=['POST'])
def receive_telemetry():
    """Endpoint for cRIO to push 1Hz data"""
    try:
        data = request.json
        raw_str = data.get('data', '')
        
        # Parse String using Regex
        abk_match = re.search(r'AbkStr;(.*?);AbkEnd', raw_str)
        cnd_match = re.search(r'CndStr;(.*?);CndEnd', raw_str)
        flw_match = re.search(r'FlwStr;(.*?);FlwEnd', raw_str)
        drw_match = re.search(r'DrwStr;(.*?);DrwEnd', raw_str)
        pmp_match = re.search(r'PmpStr;(.*?);(.*?);PmpEnd', raw_str)

        abk_vals = list(map(int, abk_match.group(1).split(';'))) if abk_match else [0]*32
        cnd_vals = list(map(float, cnd_match.group(1).split(';'))) if cnd_match else [0.0]*4
        flw_val = float(flw_match.group(1)) if flw_match else 0.0
        drw_val = float(drw_match.group(1)) if drw_match else 0.0
        pmp_rpm = float(pmp_match.group(1)) if pmp_match else 0.0
        pmp_state = int(pmp_match.group(2)) if pmp_match else 0

        now = datetime.datetime.now()
        
        with data_store.lock:
            data_store.timestamps.append(now)
            
            abk_tot = sum(abk_vals)
            data_store.abk_total.append(abk_tot)
            for i, v in enumerate(abk_vals):
                if i < 32: data_store.abk_hist[i] += v
                
            for i in range(4):
                if i < len(cnd_vals): data_store.cnd[i].append(cnd_vals[i])
                
            data_store.flw.append(flw_val)
            data_store.drw.append(drw_val)
            data_store.pmp_rpm = pmp_rpm
            data_store.pmp_state = pmp_state

        # Background log write
        event_tag = data.get('event', '')
        with open(data_store.log_file, 'a', newline='') as f:
            csv.writer(f).writerow([now.isoformat(), raw_str, event_tag])
            
        if event_tag:
            with data_store.lock:
                data_store.events.append((now, event_tag))

        return jsonify({'status': 'success'}), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

# ==========================================
# 3. DASH APPLICATION & LAYOUT
# ==========================================
app = dash.Dash(__name__, server=server, external_stylesheets=[dbc.themes.SLATE], update_title=None)
app.title = "CFA Melter Dashboard"

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    </head>
    <body>
        {%app_entry%}
        <footer>{%config%} {%scripts%} {%renderer%}</footer>
    </body>
</html>
'''

def dark_figure():
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=40, r=40, t=30, b=30),
        paper_bgcolor='#272B30',
        plot_bgcolor='#272B30',
        font=dict(color='#c8c8c8', size=10),
        xaxis=dict(showgrid=True, gridcolor='#333'),
        yaxis=dict(showgrid=True, gridcolor='#333'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

app.layout = dbc.Container([
    dcc.Interval(id='interval-comp', interval=1000, n_intervals=0),
    
    # Header
    dbc.Row([
        dbc.Col(html.H4("CFA CONTROL PANEL", className="text-uppercase fw-bold mb-0 text-white"), width=8),
        dbc.Col(html.Div(id='live-clock', className="text-end font-monospace text-muted"), width=4)
    ], className="border-bottom border-secondary pb-2 mb-3 mt-3 align-items-center"),

    dbc.Row([
        # Main Dashboard Column
        dbc.Col([
            # KPIs
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([html.Div("Total Dust", className="text-muted text-uppercase", style={'fontSize': '0.7rem'}), html.Div(id='kpi-abk', className="fs-5 fw-bold text-white font-monospace")]), className="border-start border-primary border-4 rounded-0 mb-2")),
                dbc.Col(dbc.Card(dbc.CardBody([html.Div("Conductivity", className="text-muted text-uppercase", style={'fontSize': '0.7rem'}), html.Div(id='kpi-cnd', className="fs-5 fw-bold text-white font-monospace")]), className="border-start border-warning border-4 rounded-0 mb-2")),
                dbc.Col(dbc.Card(dbc.CardBody([html.Div("Main Flow", className="text-muted text-uppercase", style={'fontSize': '0.7rem'}), html.Div(id='kpi-flw', className="fs-5 fw-bold text-white font-monospace")]), className="border-start border-success border-4 rounded-0 mb-2")),
                dbc.Col(dbc.Card(dbc.CardBody([html.Div("Core Height", className="text-muted text-uppercase", style={'fontSize': '0.7rem'}), html.Div(id='kpi-drw', className="fs-5 fw-bold text-white font-monospace")]), className="border-start border-info border-4 rounded-0 mb-2")),
            ]),
            
            # Event Logger
            dbc.Card(dbc.CardBody(dbc.Row([
                dbc.Col(html.Span("INJECT EVENT:", className="fw-bold text-muted text-uppercase"), width="auto", className="d-flex align-items-center"),
                dbc.Col(dbc.Select(id='event-type', options=[{'label': i, 'value': i} for i in ['NEW BAG', 'OBS', 'BREAK']], value='NEW BAG', size="sm", className="rounded-0 bg-dark text-white")),
                dbc.Col(dbc.Input(id='event-note', placeholder="Note...", size="sm", className="rounded-0 bg-dark text-white")),
                dbc.Col(dbc.Button("Mark", id='btn-event', color="primary", size="sm", className="rounded-0 px-4 w-100"), width="auto"),
                html.Div(id='event-status', className="d-none") # Hidden status
            ], className="g-2")), className="rounded-0 mb-3 bg-dark"),

            # Flow & Core Height (1)
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Flow and Core Height"),
                    dbc.CardBody(dcc.Graph(id='graph-flw-drw', config={'displayModeBar': False}, style={'height': '280px'}), className="p-1")
                ], className="rounded-0 mb-2"), width=12)
            ]),
            
            # Conductivity (2)
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Conductivity per Channel [mS]"),
                    dbc.CardBody(dcc.Graph(id='graph-cnd', config={'displayModeBar': False}, style={'height': '280px'}), className="p-1")
                ], className="rounded-0 mb-2"), width=12)
            ]),

            # Total Dust Trend (3)
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(dbc.Row([dbc.Col("Total Dust Trend"), dbc.Col(dbc.Switch(id='toggle-ma', label="MA", value=True, className="float-end"), width="auto")])),
                    dbc.CardBody(dcc.Graph(id='graph-abk-tot', config={'displayModeBar': False}, style={'height': '280px'}), className="p-1")
                ], className="rounded-0 mb-2"), width=12)
            ]),

            # Abakus Distribution (4)
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(dbc.Row([dbc.Col("Abakus Distribution (μm)"), dbc.Col(dbc.Button("Reset", id="btn-reset", size="sm", color="secondary", className="float-end rounded-0 py-0"), width="auto")])),
                    dbc.CardBody(dcc.Graph(id='graph-abk-hist', config={'displayModeBar': False}, style={'height': '280px'}), className="p-1")
                ], className="rounded-0 mb-2"), width=12)
            ]),
        ], lg=9),

        # Sidebar Table
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Pump & Channel Metrics", className="text-info"),
                dbc.CardBody([
                    dash_table.DataTable(
                        id='metrics-table',
                        style_table={'overflowY': 'visible'},
                        style_header={'backgroundColor': '#1c1e22', 'color': 'white', 'fontWeight': 'bold'},
                        style_cell={'backgroundColor': '#272B30', 'color': '#c8c8c8', 'border': '1px solid #1c1e22', 'padding': '5px', 'fontSize': '12px'},
                        style_data_conditional=[{'if': {'row_index': 0}, 'backgroundColor': '#1a2634', 'fontWeight': 'bold', 'color': '#0dcaf0'}]
                    )
                ], className="p-0")
            ], className="rounded-0 h-100")
        ], lg=3)
    ])
], fluid=True, className="p-3")

# ==========================================
# 4. CALLBACKS
# ==========================================
@app.callback(
    Output('event-status', 'children'),
    Input('btn-event', 'n_clicks'),
    State('event-type', 'value'),
    State('event-note', 'value'),
    prevent_initial_call=True
)
def handle_event(n_clicks, ev_type, note):
    tag = f"{ev_type}: {note}" if note else ev_type
    with data_store.lock:
        data_store.events.append((datetime.datetime.now(), tag))
        # Log event independently if UI triggered
        with open(data_store.log_file, 'a', newline='') as f:
            csv.writer(f).writerow([datetime.datetime.now().isoformat(), 'UI_INJECTION', tag])
    return tag

@app.callback(
    Output('graph-abk-hist', 'figure'),
    Input('btn-reset', 'n_clicks'),
    prevent_initial_call=True
)
def reset_hist(n):
    data_store.reset_histogram()
    return dash.no_update

@app.callback(
    [Output('live-clock', 'children'),
     Output('kpi-abk', 'children'), Output('kpi-cnd', 'children'),
     Output('kpi-flw', 'children'), Output('kpi-drw', 'children'),
     Output('graph-abk-hist', 'figure'), Output('graph-abk-tot', 'figure'),
     Output('graph-cnd', 'figure'), Output('graph-flw-drw', 'figure'),
     Output('metrics-table', 'data'), Output('metrics-table', 'columns')],
    [Input('interval-comp', 'n_intervals')],
    [State('toggle-ma', 'value'),
     State('graph-abk-tot', 'relayoutData'),
     State('graph-cnd', 'relayoutData'),
     State('graph-flw-drw', 'relayoutData')]
)
def update_dashboard(n, show_ma, relayout_tot, relayout_cnd, relayout_flw):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with data_store.lock:
        t = list(data_store.timestamps)
        hist = list(data_store.abk_hist)
        tot = list(data_store.abk_total)
        cnd = [list(c) for c in data_store.cnd]
        flw = list(data_store.flw)
        drw = list(data_store.drw)
        rpm = data_store.pmp_rpm
        scales = data_store.scales
        offsets = data_store.offsets
        evts = list(data_store.events)
        
    # Formatting KPIs
    k_abk = f"{tot[-1]}" if tot else "0"
    
    if all(len(c) > 0 for c in cnd):
        mean_cnd = sum(c[-1] for c in cnd) / 4.0
        k_cnd = f"{mean_cnd:.4f} mS"
    else:
        k_cnd = "0.0000 mS"
        
    k_flw = f"{flw[-1]:.2f} ml/min" if flw else "0.00 ml/min"
    k_drw = f"{drw[-1]:.0f} cm" if drw else "0 cm"

    # Helper to add moving average
    def apply_ma(y_data, window=5):
        s = pd.Series(y_data)
        return s.rolling(window=window, min_periods=1).mean().tolist()
        
    def add_events(fig, y_min, y_max):
        for ev_t, ev_tag in evts:
            if t and t[0] <= ev_t <= t[-1]:
                # Overlaid transparent line to activate hover text specifically on the marker
                fig.add_trace(go.Scatter(
                    x=[ev_t, ev_t],
                    y=[y_min, y_max],
                    mode="lines",
                    line=dict(dash="dash", color="red", width=2),
                    hoverinfo="text",
                    hovertext=ev_tag,
                    showlegend=False
                ))
        return fig

    # Helper to control live scrolling vs historical freeze with rangeslider
    def get_xaxis_dict(relayout_data, timestamps, window_seconds=VIEW_WINDOW_SEC):
        base_xaxis = dict(
            showgrid=True,
            gridcolor='#333',
            rangeslider=dict(visible=True, thickness=0.08, bgcolor='#1c1e22')
        )
        if not timestamps:
            return base_xaxis
        
        latest = timestamps[-1]
        earliest = timestamps[0]
        base_xaxis['rangeslider']['range'] = [earliest, latest]
        
        user_range = None
        if relayout_data:
            if 'xaxis.range[0]' in relayout_data and 'xaxis.range[1]' in relayout_data:
                user_range = [relayout_data['xaxis.range[0]'], relayout_data['xaxis.range[1]']]
            elif 'xaxis.range' in relayout_data and isinstance(relayout_data['xaxis.range'], list) and len(relayout_data['xaxis.range']) == 2:
                user_range = relayout_data['xaxis.range']
                
            if relayout_data.get('xaxis.autorange') is True or relayout_data.get('autosize') is True:
                user_range = None

        if user_range:
            try:
                r0 = pd.to_datetime(user_range[0]).to_pydatetime().replace(tzinfo=None)
                r1 = pd.to_datetime(user_range[1]).to_pydatetime().replace(tzinfo=None)
                # Resume live scrolling if user slides back to the latest timestamp
                if (latest - r1).total_seconds() <= 2.0:
                    start = latest - datetime.timedelta(seconds=window_seconds)
                    base_xaxis['range'] = [start, latest]
                else:
                    # Freeze display at the inspected timestamp while maintaining the 60-second window
                    frozen_start = r1 - datetime.timedelta(seconds=window_seconds)
                    base_xaxis['range'] = [frozen_start, r1]
            except Exception:
                start = latest - datetime.timedelta(seconds=window_seconds)
                base_xaxis['range'] = [start, latest]
        else:
            start = latest - datetime.timedelta(seconds=window_seconds)
            base_xaxis['range'] = [start, latest]
            
        return base_xaxis

    # 1. Histogram
    f_hist = dark_figure()
    bins = ['0.8','0.9','1','1.1','1.2','1.3','1.4','1.6','1.8','2','2.2','2.4','2.6','2.9','3.2','3.5','3.9','4.3','4.8','5.3','5.8','6.4','7.1','7.8','8.6','9.5','10.5','11.6','12.8','14.1','15.5','80']
    f_hist.add_trace(go.Bar(x=bins, y=hist, marker_color='#0d6efd', name='Count'))
    f_hist.update_layout(yaxis_type="log", xaxis_tickangle=0)

    # 2. Total Abakus
    f_tot = dark_figure()
    f_tot.update_layout(
        uirevision='constant',
        xaxis=get_xaxis_dict(relayout_tot, t)
    )
    f_tot.add_trace(go.Scatter(x=t, y=tot, mode='lines', name='Total', line=dict(color='#6610f2')))
    if show_ma and tot: f_tot.add_trace(go.Scatter(x=t, y=apply_ma(tot), mode='lines', name='MA', line=dict(dash='dash', color='#d63384')))
    
    y_min_tot = min(tot) if tot else 0
    y_max_tot = max(tot) if tot else 1
    f_tot = add_events(f_tot, y_min_tot, y_max_tot)

    # 3. Conductivity
    f_cnd = dark_figure()
    f_cnd.update_layout(
        uirevision='constant',
        xaxis=get_xaxis_dict(relayout_cnd, t)
    )
    colors = ['#fd7e14', '#ffc107', '#198754', '#20c997']
    for i in range(4):
        if len(cnd[i]) > 0:
            f_cnd.add_trace(go.Scatter(x=t, y=cnd[i], mode='lines', name=f'Ch {i+1}', line=dict(color=colors[i])))
            
    all_cnd = [val for c in cnd for val in c]
    y_min_cnd = min(all_cnd) if all_cnd else 0
    y_max_cnd = max(all_cnd) if all_cnd else 1
    f_cnd = add_events(f_cnd, y_min_cnd, y_max_cnd)

    # 4. Flow & Draw
    f_flw = dark_figure()
    f_flw.update_layout(
        uirevision='constant',
        xaxis=get_xaxis_dict(relayout_flw, t),
        yaxis=dict(title='Flow [ml/min]', side='left', showgrid=True),
        yaxis2=dict(title='Core [cm]', side='right', overlaying='y', showgrid=False)
    )
    f_flw.add_trace(go.Scatter(x=t, y=flw, mode='lines', name='Flow', line=dict(color='#0dcaf0'), yaxis='y1'))
    f_flw.add_trace(go.Scatter(x=t, y=drw, mode='lines', name='Drw', line=dict(color='#6f42c1'), yaxis='y2'))
    if show_ma and flw and drw:
        f_flw.add_trace(go.Scatter(x=t, y=apply_ma(flw), mode='lines', name='Flw MA', line=dict(dash='dash', color='#0dcaf0'), yaxis='y1'))
        f_flw.add_trace(go.Scatter(x=t, y=apply_ma(drw), mode='lines', name='Drw MA', line=dict(dash='dash', color='#6f42c1'), yaxis='y2'))
    
    y_min_flw = min(flw) if flw else 0
    y_max_flw = max(flw) if flw else 1
    f_flw = add_events(f_flw, y_min_flw, y_max_flw)

    # Table calculation
    cols = [{'name': 'Parameter', 'id': 'Parameter'}, {'name': 'Value', 'id': 'Value'}]
    table_data = [{'Parameter': 'PUMP RPM', 'Value': f"{rpm:.3f}"}]
    for i in range(24):
        flow_val = (rpm * scales[i]) + offsets[i]
        table_data.append({'Parameter': f'Ch {i+1} Flow', 'Value': f"{flow_val:.4f}"})

    return now_str, k_abk, k_cnd, k_flw, k_drw, f_hist, f_tot, f_cnd, f_flw, table_data, cols

if __name__ == '__main__':
    # Do not run app.run(debug=True) in production.
    app.run(host='0.0.0.0', port=8050, debug=False)