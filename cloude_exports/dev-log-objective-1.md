╭─── Claude Code v2.1.161 ─────────────────────────────────────────────────────╮
│                                                    │ Tips for getting        │
│                Welcome back Sergio!                │ started                 │
│                                                    │ ✔ Run /init to create … │
│                       ▐▛███▜▌                      │ ─────────────────────── │
│                      ▝▜█████▛▘                     │ What's new              │
│                        ▘▘ ▝▝                       │ `claude agents --json`… │
│   Sonnet 4.6 · Claude Pro ·                        │ `--tools`: explicitly … │
│   sergio.salazar.relayze@gmail.com's Organization  │ `/effort` now confirms… │
│         ~/Documents/Projects/segundaVuelta         │ /release-notes for more │
╰──────────────────────────────────────────────────────────────────────────────╯

   Opus 4.8 is now available! · /model to switch

❯ /model                                                                        
  ⎿  Set model to Sonnet 4.6 (default) and saved as your default for new
     sessions

❯ /effort                                                                       
  ⎿  Set effort level to medium: Balanced approach with standard implementation
     and testing

❯ /init                                                                         

  Read 7 files, listed 2 directories (ctrl+o to expand)

● Now I have enough context to write the CLAUDE.md file.

● Write(CLAUDE.md)
  ⎿  Wrote 84 lines to CLAUDE.md
      1 # CLAUDE.md
      3 This file provides guidance to Claude Code (claude.ai/code) when 
        working with code in this repository.
      4 
      6 
      7 This is a Peru election results scraper and statistical projectio
        ales) API. It scrapes live vote tallies by district (ubigeo), agg
        regates them, and projects final results using a dynamic stratifi
        ed sampling model.
      9 ## Pipeline Execution Order
     … +99 lines (ctrl+o to expand)

● CLAUDE.md created. It covers the four-step pipeline execution order, the role
  of each key file, scraper run modes, the projection model's dynamic
  stratification logic, and the data contract for scraped records.

✻ Brewed for 41s

❯ Now think and create an interactive front-end, that runs in localhost but can 
  later turn into a webpage that has the current observed results and the       
  prediction model results. Take into account that later we will add another    
  model which is still in methodology definition phase.                         

● Let me look at the actual data before designing anything.

  Ran 5 shell commands (ctrl+o to expand)

● Good picture of the data. Let me check requirements and the first-round data
  directory before designing.

  Listed 1 directory, ran 1 shell command (ctrl+o to expand)

● Now I have a complete picture of the data and the pipeline. Let me plan then
  build this properly.

● User declined to answer questions
  ⎿  · Which of these best matches how you want the dashboard to look and feel? 
     (Election night / Analyst dashboard)

● What would you like to clarify?

✻ Baked for 5m 35s

❯ I would like the front end to be an html page                                 

● Got it — a single dashboard.html served by a lightweight Flask backend. Let me
  look at the existing Plotly export and the full data shape one more time,
  then build everything.

  Ran 3 shell commands (ctrl+o to expand)

● Good. Now I'll build all four files — two edits to existing code, two new
  files.

  Read 1 file (ctrl+o to expand)

● Update(propagation_model.py)
  ⎿  Added 1 line, removed 1 line
      42  
      43  
      44  def run_dynamic_stratified_projection(
      45 -    df, candidate_cols, party_mapping, z_score=1.96            
      45 +    df, candidate_cols, party_mapping, z_score=1.96, generate_h
         +tml=True                                                       
      46  ):
      47      """Executes an election projection evaluating stability DYN
          AMICALLY per district.
      48  

● Update(propagation_model.py)
  ⎿  Added 2 lines, removed 1 line
      191      results_df = pd.DataFrame(projections).T
      192      results_df.index.name = "Political Organization"
      193  
      194 -    create_interactive_dashboard(results_df, "Dynamic Per-Dist
          -rict Stratum")                                                
      194 +    if generate_html:                                         
      195 +        create_interactive_dashboard(results_df, "Dynamic Per-
          +District Stratum")                                            
      196      return results_df.sort_values(by="Projected Share (%)", as
           cending=False)
      197  
      198  

● Now add get_projection_data() before the __main__ block:

● Update(propagation_model.py)
  ⎿  Added 36 lines
      243      print(f"🌐 Interactive dashboard exported successfully as 
           '{filename}'")
      244  
      245  
      246 +def get_projection_data(data_path=None, mapping_path=None, z_s
          +core=1.96):                                                   
      247 +    """Returns projection results as a JSON-serializable dict 
          +for the web API."""                                           
      248 +    if data_path is None:                                     
      249 +        data_path = os.path.join("processed_results", "agg_dis
          +trital.json")                                                 
      250 +    if mapping_path is None:                                  
      251 +        mapping_path = os.path.join("processed_results", "idx_
          +codigo_nombre_partido.json")                                  
      252 +                                                              
      253 +    if not os.path.exists(data_path) or not os.path.exists(map
          +ping_path):                                                   
      254 +        return {"error": "Data files not found", "parties": []
          +}                                                             
      255 +                                                              
      256 +    df_flat, candidate_cols, party_mapping = preprocess_electo
          +ral_data(data_path, mapping_path)                             
      257 +    results_df = run_dynamic_stratified_projection(           
      258 +        df_flat, candidate_cols, party_mapping, z_score, gener
          +ate_html=False                                                
      259 +    )                                                         
      260 +                                                              
      261 +    parties_data = []                                         
      262 +    for name, row in results_df.iterrows():                   
      263 +        parties_data.append({                                 
      264 +            "name": name,                                     
      265 +            "id": str(row["ID"]),                             
      266 +            "observed_votes": int(row["Observed Votes"]),     
      267 +            "projected_votes": int(row["Projected Votes"]),   
      268 +            "projected_share": float(row["Projected Share (%)"
          +]),                                                           
      269 +            "moe": float(row["MOE (%)"]),                     
      270 +            "lower_bound": float(row["Lower Bound Share (%)"])
          +,                                                             
      271 +            "upper_bound": float(row["Upper Bound Share (%)"])
          +,                                                             
      272 +        })                                                    
      273 +                                                              
      274 +    return {                                                  
      275 +        "model": "dynamic_stratified_propagation",            
      276 +        "z_score": z_score,                                   
      277 +        "confidence_level": "95%",                            
      278 +        "parties": sorted(parties_data, key=lambda x: x["proje
          +cted_share"], reverse=True),                                  
      279 +    }                                                         
      280 +                                                              
      281 +                                                              
      282  if __name__ == "__main__":
      283      DATA_PATH = "processed_results/agg_distrital.json"
      284      MAPPING_PATH = "processed_results/idx_codigo_nombre_partid
           o.json"
● Now the Flask server:

● Write(app.py)
  ⎿  Wrote 64 lines to app.py
       1 import json
       2 import os
       3 import sys
       4 import time
       5 
       6 from flask import Flask, jsonify, send_file
       7 
       8 app = Flask(__name__)
       9 
      10 _cache: dict = {}
     … +56 lines (ctrl+o to expand)

● Now the main dashboard.html — single file, all CSS and JS inline:

● Write(dashboard.html)
  ⎿  Wrote 822 lines to dashboard.html
      1 <!DOCTYPE html>
      2 <html lang="es">
      3 <head>
      5   <meta name="viewport" content="width=device-width, initial-scal
        e=1.0">
      6   <title>Elecciones Generales 2026 · Dashboard</title>
      7   <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/c
        hart.umd.min.js"></script>
      9     *, *::before, *::after { box-sizing: border-box; margin: 0; p
        adding: 0; }
     … +908 lines (ctrl+o to expand)

● Now let me verify everything works:

  Ran 2 shell commands (ctrl+o to expand)

● All three endpoints return correctly. Let me start the server for you to
  browse:

  Ran 1 shell command (ctrl+o to expand)

● Dashboard is running at http://127.0.0.1:5000

  Here's what was built and how to run it in future sessions:

  source .venv/bin/activate && python app.py

  What the dashboard shows:

  - Header: Peru flag stripe, election title, live indicator, refresh button +
  last-updated timestamp
  - 4 KPI cards: Actas %, votos válidos, participación, blancos+nulos
  - Observed results chart (Chart.js horizontal bars): top 12 parties sorted by
  share, gold border on the top 2 advancing to segunda vuelta, "ver todos"
  button to expand all 38, tab switcher for Nacional / Perú / Exterior
  - Propagation model card: Observed vs projected share with 95% CI per party —
  loads in background after the main chart renders
  - Vote migration model card: placeholder with description, clearly marked "En
  desarrollo" — ready to be wired up when the second model is built
  - Department table: sortable by any column (1st/2nd place, actas %,
  participación)

  Adding the second model later — just add a new route to app.py
  (/api/model/migration) and wire up the placeholder card in dashboard.html with
  a fetchMigration() function following the same pattern as fetchProp().

✻ Crunched for 8m 14s

● Background command "Start dashboard server" failed with exit code 1

  Read 1 file (ctrl+o to expand)

● Port 5000 is still occupied by the test run from earlier. Let me kill it and
  restart:

  Ran 3 shell commands (ctrl+o to expand)

● Server is up. Open http://127.0.0.1:5000 in your browser.

✻ Sautéed for 19s

❯ edit the front end so it uses the information inside information in           
  first_round_agg_results to show them as stable and as a tab. But prepare it   
  for the second round, where as information is updated, the information will   
  feed into processed_results and the propagation model for the second round.   

● Let me look at what's in that directory first.

  Ran 2 shell commands (ctrl+o to expand)

● Good — identical schema, just different source directories. The plan is clear:
  - Primera Vuelta tab: reads from first_round_agg_results/, locked/stable,
  shows finalists banner
  - Segunda Vuelta tab: reads from processed_results/ (live), propagation model
  runs on it

  Let me update app.py first (small addition), then rewrite dashboard.html.

  Read 1 file (ctrl+o to expand)

● Update(app.py)
  ⎿  Added 28 lines, removed 15 lines
      21      return send_file("dashboard.html")
      22  
      23  
      24 -@app.route("/api/observed")                                    
      25 -def api_observed():                                            
      26 -    base = "processed_results"                                 
      24 +def _round_payload(base: str, is_final: bool):                 
      25      paths = {
      28 -        "ambito": f"{base}/agg_ambito.json",                   
      29 -        "departamental": f"{base}/agg_departamental.json",     
      30 -        "parties": f"{base}/idx_codigo_nombre_partido.json",   
      26 +        "ambito":       f"{base}/agg_ambito.json",             
      27 +        "departamental":f"{base}/agg_departamental.json",      
      28 +        "parties":      f"{base}/idx_codigo_nombre_partido.json
         +",                                                             
      29      }
      30      missing = [p for p in paths.values() if not os.path.exists(
          p)]
      31      if missing:
      32 +        return None, missing                                   
      33 +    data = {                                                   
      34 +        "ambito":       _read(paths["ambito"]),                
      35 +        "departamental":_read(paths["departamental"]),         
      36 +        "parties":      _read(paths["parties"]),               
      37 +        "last_updated": os.path.getmtime(paths["departamental"]
         +),                                                             
      38 +        "is_final":     is_final,                              
      39 +    }                                                          
      40 +    return data, None                                          
      41 +                                                               
      42 +                                                               
      43 +@app.route("/api/round/first")                                 
      44 +def api_first_round():                                         
      45 +    data, missing = _round_payload("first_round_agg_results", i
         +s_final=True)                                                  
      46 +    if missing:                                                
      47          return jsonify({"ok": False, "error": f"Missing: {missi
          ng}"}), 404
      48 +    return jsonify({"ok": True, "data": data})                 
      49  
      36 -    return jsonify({                                           
      37 -        "ok": True,                                            
      38 -        "data": {                                              
      39 -            "ambito": _read(paths["ambito"]),                  
      40 -            "departamental": _read(paths["departamental"]),    
      41 -            "parties": _read(paths["parties"]),                
      42 -            "last_updated": os.path.getmtime(paths["departament
         -al"]),                                                         
      43 -        },                                                     
      44 -    })                                                         
      50  
      51 +@app.route("/api/round/second")                                
      52 +@app.route("/api/observed")          # keep old path working   
      53 +def api_second_round():                                        
      54 +    data, missing = _round_payload("processed_results", is_fina
         +l=False)                                                       
      55 +    if missing:                                                
      56 +        return jsonify({"ok": False, "error": f"Missing: {missi
         +ng}"}), 404                                                    
      57 +    return jsonify({"ok": True, "data": data})                 
      58  
      59 +                                                               
      60  @app.route("/api/model/propagation")
      61  def api_model_propagation():
      62      now = time.time()

● Now rewrite dashboard.html with the two-round structure:

● Write(dashboard.html)
  ⎿  Added 561 lines, removed 366 lines
       9      *, *::before, *::after { box-sizing: border-box; margin: 0;
           padding: 0; }
      10  
      11      :root {
      12 -      --red:        #C0392B;                                   
      13 -      --red-light:  #FDECEA;                                   
      14 -      --blue:       #1A3A6B;                                   
      15 -      --blue-light: #EBF0FA;                                   
      16 -      --gold:       #B7950B;                                   
      17 -      --gold-bg:    #FEFCE8;                                   
      18 -      --gold-border:#D4AC0D;                                   
      19 -      --bg:         #F0F4F8;                                   
      20 -      --card:       #FFFFFF;                                   
      21 -      --text:       #1A202C;                                   
      22 -      --muted:      #64748B;                                   
      23 -      --border:     #E2E8F0;                                   
      24 -      --green:      #166534;                                   
      25 -      --green-bg:   #F0FDF4;                                   
      12 +      --red:         #C0392B;                                  
      13 +      --red-light:   #FDECEA;                                  
      14 +      --blue:        #1A3A6B;                                  
      15 +      --blue-mid:    #2d5aa0;                                  
      16 +      --blue-light:  #EBF0FA;                                  
      17 +      --gold:        #B7950B;                                  
      18 +      --gold-bg:     #FEFCE8;                                  
      19 +      --gold-border: #D4AC0D;                                  
      20 +      --bg:          #F0F4F8;                                  
      21 +      --card:        #FFFFFF;                                  
      22 +      --text:        #1A202C;                                  
      23 +      --muted:       #64748B;                                  
      24 +      --border:      #E2E8F0;                                  
      25 +      --green:       #166534;                                  
      26 +      --green-bg:    #F0FDF4;                                  
      27      }
      28  
      29      body {
     ...
      35      }
      36  
      37      /* ── Header ──────────────────────────────────────────────
          ─ */
      37 -    .header-flag {                                             
      38 +    .flag-stripe {                                             
      39        height: 6px;
      40        background: linear-gradient(90deg, var(--red) 33.3%, #fff
           33.3% 66.6%, var(--red) 66.6%);
      41      }
     ...
      51        gap: 12px;
      52      }
      53  
      53 -    .header-left h1 { font-size: 1.1rem; font-weight: 700; lett
         -er-spacing: .02em; }                                           
      54 -    .header-left p  { font-size: .75rem; opacity: .7; margin-to
         -p: 2px; }                                                      
      54 +    .h-title h1 { font-size: 1.05rem; font-weight: 700; letter-
         +spacing: .02em; }                                              
      55 +    .h-title p  { font-size: .72rem; opacity: .65; margin-top: 
         +2px; }                                                         
      56  
      56 -    .header-right { display: flex; align-items: center; gap: 12
         -px; flex-wrap: wrap; }                                         
      57 +    .h-right { display: flex; align-items: center; gap: 12px; f
         +lex-wrap: wrap; }                                              
      58  
      58 -    .live-badge {                                              
      59 +    .live-dot {                                                
      60        display: inline-flex; align-items: center; gap: 6px;
      61        background: rgba(255,255,255,.12); padding: 4px 10px;
      61 -      border-radius: 999px; font-size: .75rem;                 
      62 +      border-radius: 999px; font-size: .72rem;                 
      63      }
      64      .pulse {
      65        width: 8px; height: 8px; border-radius: 50%;
      65 -      background: #4ADE80;                                     
      66 -      animation: pulse 2s infinite;                            
      66 +      background: #4ADE80; animation: pulse 2s infinite;       
      67      }
      68      @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }
      69  
      70 -    #ts { font-size: .72rem; opacity: .65; }                   
      71 -                                                               
      70      .btn {
      71        padding: 6px 14px; border-radius: 6px; cursor: pointer;
      74 -      font-size: .78rem; font-weight: 600; border: none; transi
         -tion: opacity .15s;                                            
      72 +      font-size: .78rem; font-weight: 600; border: none;       
      73 +      transition: opacity .15s;                                
      74      }
      76 -    .btn:disabled { opacity: .5; cursor: default; }            
      75 +    .btn:disabled { opacity: .45; cursor: default; }           
      76      .btn-ghost {
      77        background: rgba(255,255,255,.15);
      78        border: 1px solid rgba(255,255,255,.3);
     ...
       80      }
       81      .btn-ghost:not(:disabled):hover { background: rgba(255,255
           ,255,.25); }
       82  
       83 +    /* ── Round switcher ─────────────────────────────────────
          +─── */                                                        
       84 +    .round-bar {                                              
       85 +      background: var(--blue);                                
       86 +      border-top: 1px solid rgba(255,255,255,.1);             
       87 +      padding: 0 24px;                                        
       88 +      display: flex;                                          
       89 +      align-items: flex-end;                                  
       90 +      gap: 4px;                                               
       91 +    }                                                         
       92 +                                                              
       93 +    .round-tab {                                              
       94 +      padding: 10px 20px 12px;                                
       95 +      border: none; background: transparent;                  
       96 +      color: rgba(255,255,255,.55);                           
       97 +      font-size: .82rem; font-weight: 600;                    
       98 +      cursor: pointer; border-bottom: 3px solid transparent;  
       99 +      display: flex; align-items: center; gap: 8px;           
      100 +      transition: color .15s, border-color .15s;              
      101 +      white-space: nowrap;                                    
      102 +    }                                                         
      103 +    .round-tab:hover { color: rgba(255,255,255,.85); }        
      104 +    .round-tab.active {                                       
      105 +      color: #fff;                                            
      106 +      border-bottom-color: #fff;                              
      107 +    }                                                         
      108 +                                                              
      109 +    .rtag {                                                   
      110 +      font-size: .62rem; font-weight: 700; padding: 2px 6px;  
      111 +      border-radius: 4px; letter-spacing: .04em;              
      112 +    }                                                         
      113 +    .rtag-done { background: rgba(74,222,128,.2); color: #4ADE
          +80; }                                                         
      114 +    .rtag-live { background: rgba(251,191,36,.2);  color: #FBD
          +24C; }                                                        
      115 +    .rtag-wait { background: rgba(255,255,255,.1); color: rgba
          +(255,255,255,.5); }                                           
      116 +                                                              
      117      /* ── Layout ─────────────────────────────────────────────
           ─── */
      118      main { max-width: 1280px; margin: 0 auto; padding: 20px 20
           px 56px; }
      119  
       87 -    /* ── KPI cards ──────────────────────────────────────────
          -─── */                                                        
      120 +    /* ── KPI grid ───────────────────────────────────────────
          +─── */                                                        
      121      .kpi-grid {
      122        display: grid;
      123        grid-template-columns: repeat(4, 1fr);
     ...
      125        margin-bottom: 20px;
      126      }
      127      @media (max-width: 860px) { .kpi-grid { grid-template-colu
           mns: repeat(2,1fr); } }
       95 -    @media (max-width: 480px) { .kpi-grid { grid-template-colu
          -mns: 1fr; } }                                                 
      128  
      129      .kpi {
       98 -      background: var(--card);                                
       99 -      border-radius: 10px;                                    
      100 -      padding: 14px 18px;                                     
      101 -      box-shadow: 0 1px 3px rgba(0,0,0,.08);                  
      130 +      background: var(--card); border-radius: 10px;           
      131 +      padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.08
          +);                                                            
      132        border-left: 4px solid var(--blue);
      133      }
      134      .kpi.red   { border-left-color: var(--red); }
     ...
      142      .kpi-value { font-size: 1.55rem; font-weight: 800; line-he
           ight: 1; }
      143      .kpi-sub   { font-size: .72rem; color: var(--muted); margi
           n-top: 4px; }
      144  
      115 -    .prog-wrap { background: var(--bg); border-radius: 999px; 
          -height: 7px; margin-top: 8px; overflow: hidden; }             
      116 -    .prog-fill { height: 100%; border-radius: 999px; backgroun
          -d: var(--blue); transition: width 1s ease; }                  
      145 +    .prog-wrap {                                              
      146 +      background: var(--bg); border-radius: 999px;            
      147 +      height: 7px; margin-top: 8px; overflow: hidden;         
      148 +    }                                                         
      149 +    .prog-fill {                                              
      150 +      height: 100%; border-radius: 999px; background: var(--bl
          +ue);                                                          
      151 +      transition: width 1s ease; width: 0%;                   
      152 +    }                                                         
      153  
      118 -    /* ── Section card ───────────────────────────────────────
          -──── */                                                       
      154 +    /* ── Finalists banner ───────────────────────────────────
          +─── */                                                        
      155 +    .finalists-wrap {                                         
      156 +      background: linear-gradient(135deg, var(--blue) 0%, var(
          +--blue-mid) 100%);                                            
      157 +      border-radius: 10px;                                    
      158 +      padding: 18px 20px 20px;                                
      159 +      margin-bottom: 20px;                                    
      160 +      color: #fff;                                            
      161 +      box-shadow: 0 2px 8px rgba(26,58,107,.3);               
      162 +    }                                                         
      163 +    .finalists-label {                                        
      164 +      font-size: .68rem; font-weight: 700; text-transform: upp
          +ercase;                                                       
      165 +      letter-spacing: .1em; opacity: .65; text-align: center; 
          +margin-bottom: 14px;                                          
      166 +    }                                                         
      167 +    .finalists-row {                                          
      168 +      display: flex; align-items: stretch; justify-content: ce
          +nter;                                                         
      169 +      gap: 16px; flex-wrap: wrap;                             
      170 +    }                                                         
      171 +    .finalist-card {                                          
      172 +      background: rgba(255,255,255,.12);                      
      173 +      border: 1px solid rgba(255,255,255,.18);                
      174 +      border-radius: 8px;                                     
      175 +      padding: 14px 22px;                                     
      176 +      text-align: center;                                     
      177 +      flex: 1; min-width: 160px; max-width: 260px;            
      178 +    }                                                         
      179 +    .finalist-rank {                                          
      180 +      font-size: .68rem; font-weight: 700;                    
      181 +      opacity: .6; margin-bottom: 6px; letter-spacing: .06em; 
      182 +    }                                                         
      183 +    .finalist-name {                                          
      184 +      font-size: .88rem; font-weight: 800;                    
      185 +      margin-bottom: 8px; line-height: 1.3;                   
      186 +    }                                                         
      187 +    .finalist-share {                                         
      188 +      font-size: 1.8rem; font-weight: 900; line-height: 1;    
      189 +    }                                                         
      190 +    .finalist-votes { font-size: .7rem; opacity: .6; margin-to
          +p: 4px; }                                                     
      191 +    .finalist-color-bar {                                     
      192 +      height: 3px; border-radius: 999px;                      
      193 +      margin: 10px auto 0; width: 40px;                       
      194 +    }                                                         
      195 +    .finalists-vs {                                           
      196 +      display: flex; align-items: center;                     
      197 +      font-size: 1rem; font-weight: 900;                      
      198 +      opacity: .4; padding: 0 4px; flex-shrink: 0;            
      199 +    }                                                         
      200 +                                                              
      201 +    /* ── Card ───────────────────────────────────────────────
          +─── */                                                        
      202      .card {
      203        background: var(--card);
      204        border-radius: 10px;
     ...
      218      }
      219      .card-body { padding: 18px; }
      220  
      138 -    /* ── Tabs ───────────────────────────────────────────────
          -──── */                                                       
      221 +    /* ── Definitivo badge ───────────────────────────────────
          +─── */                                                        
      222 +    .badge-final {                                            
      223 +      display: inline-flex; align-items: center; gap: 5px;    
      224 +      background: var(--green-bg); color: var(--green);       
      225 +      border: 1px solid #BBF7D0; border-radius: 5px;          
      226 +      font-size: .7rem; font-weight: 700; padding: 3px 9px;   
      227 +    }                                                         
      228 +                                                              
      229 +    /* ── Tabs ───────────────────────────────────────────────
          +─── */                                                        
      230      .tabs {
      231        display: flex; gap: 3px;
      232        background: var(--bg); padding: 3px; border-radius: 7px;
     ...
      241        font-weight: 700; box-shadow: 0 1px 3px rgba(0,0,0,.1);
      242      }
      243  
      153 -    /* ── Chart container ────────────────────────────────────
          -─── */                                                        
      244 +    /* ── Chart ──────────────────────────────────────────────
          +─── */                                                        
      245      .chart-wrap { position: relative; width: 100%; }
      155 -                                                              
      246      .chart-legend {
      157 -      display: flex; align-items: center; gap: 6px;           
      247 +      display: flex; align-items: center; gap: 6px; margin-top
          +: 10px;                                                       
      248        font-size: .72rem; color: #92400E;
      159 -      margin-top: 10px; padding: 6px 10px;                    
      249 +      padding: 6px 10px;                                      
      250        background: var(--gold-bg); border-radius: 6px;
      251        border: 1px solid #FDE68A;
      252      }
      253      .legend-box {
      254        width: 13px; height: 13px;
      165 -      border: 2px solid var(--gold-border); border-radius: 3px
          -;                                                             
      166 -      flex-shrink: 0;                                         
      255 +      border: 2px solid var(--gold-border); border-radius: 3px
          +; flex-shrink: 0;                                             
      256      }
      257  
      258      .show-more-btn {
      259        display: block; margin: 12px auto 0;
      171 -      padding: 6px 18px;                                      
      172 -      border: 1px solid var(--border); background: #fff;      
      173 -      border-radius: 6px; cursor: pointer;                    
      260 +      padding: 6px 18px; border: 1px solid var(--border);     
      261 +      background: #fff; border-radius: 6px; cursor: pointer;  
      262        font-size: .78rem; color: var(--muted); transition: bord
           er-color .15s;
      263      }
      264      .show-more-btn:hover { border-color: var(--blue); color: v
           ar(--blue); }
     ...
      274        background: var(--card); border-radius: 10px;
      275        box-shadow: 0 1px 3px rgba(0,0,0,.08); overflow: hidden;
      276      }
      189 -    .model-card.dim { opacity: .6; }                          
      277 +    .model-card.dim { opacity: .55; }                         
      278  
      279      .model-head {
      280        display: flex; align-items: flex-start; justify-content:
            space-between;
     ...
      285      .model-body { padding: 14px 18px; }
      286  
      287      .badge {
      200 -      display: inline-block; padding: 2px 8px;                
      201 -      border-radius: 4px; font-size: .68rem; font-weight: 700;
      202 -      white-space: nowrap; flex-shrink: 0;                    
      288 +      display: inline-block; padding: 2px 8px; border-radius: 
          +4px;                                                          
      289 +      font-size: .68rem; font-weight: 700; white-space: nowrap
          +; flex-shrink: 0;                                             
      290      }
      204 -    .badge-on   { background: var(--green-bg); color: var(--gr
          -een); }                                                       
      205 -    .badge-off  { background: var(--bg); color: var(--muted); 
          -}                                                             
      206 -    .badge-gold {                                             
      291 +    .badge-on  { background: var(--green-bg); color: var(--gre
          +en); }                                                        
      292 +    .badge-off { background: var(--bg); color: var(--muted); }
      293 +    .badge-adv {                                              
      294        background: var(--gold-bg); color: #92400E;
      208 -      border: 1px solid #FDE68A; font-size: .65rem;           
      295 +      border: 1px solid #FDE68A; font-size: .62rem;           
      296      }
      297  
      211 -    /* ── Model results table ────────────────────────────────
          -─── */                                                        
      212 -    .model-table {                                            
      213 -      width: 100%; border-collapse: collapse; font-size: .78re
          -m;                                                            
      214 -    }                                                         
      215 -    .model-table th {                                         
      298 +    /* ── Model table ────────────────────────────────────────
          +─── */                                                        
      299 +    .mtable { width: 100%; border-collapse: collapse; font-siz
          +e: .78rem; }                                                  
      300 +    .mtable th {                                              
      301        text-align: right; color: var(--muted); font-weight: 700
           ;
      302        font-size: .68rem; text-transform: uppercase; letter-spa
           cing: .04em;
      303        padding: 0 8px 8px;
      304      }
      220 -    .model-table th:first-child { text-align: left; }         
      221 -    .model-table td {                                         
      305 +    .mtable th:first-child { text-align: left; }              
      306 +    .mtable td {                                              
      307        padding: 5px 8px; border-top: 1px solid var(--border); t
           ext-align: right;
      308      }
      224 -    .model-table td:first-child { text-align: left; }         
      225 -    .model-table tr:hover td { background: #F8FAFC; }         
      226 -    .model-table tr.adv td   { background: var(--gold-bg); }  
      227 -    .model-table tr.adv:hover td { background: #FEF3C7; }     
      309 +    .mtable td:first-child { text-align: left; }              
      310 +    .mtable tr:hover td   { background: #F8FAFC; }            
      311 +    .mtable tr.adv td     { background: var(--gold-bg); }     
      312 +    .mtable tr.adv:hover td { background: #FEF3C7; }          
      313  
      229 -    .party-dot {                                              
      314 +    .pdot {                                                   
      315        display: inline-block; width: 9px; height: 9px;
      231 -      border-radius: 2px; flex-shrink: 0; vertical-align: midd
          -le;                                                           
      232 -      margin-right: 5px;                                      
      316 +      border-radius: 2px; vertical-align: middle; margin-right
          +: 5px;                                                        
      317      }
      234 -                                                              
      318      .ci { font-size: .7rem; color: var(--muted); }
      319 +    .info-note {                                              
      320 +      margin-top: 12px; padding: 8px 12px; border-radius: 6px;
      321 +      background: var(--blue-light); color: #1E40AF; font-size
          +: .73rem;                                                     
      322 +    }                                                         
      323  
      324      /* ── Dept table ─────────────────────────────────────────
           ──── */
      238 -    .dept-table {                                             
      239 -      width: 100%; border-collapse: collapse; font-size: .8rem
          -;                                                             
      240 -    }                                                         
      241 -    .dept-table th {                                          
      242 -      text-align: left; padding: 8px 12px;                    
      243 -      background: var(--bg); font-size: .7rem; font-weight: 70
          -0;                                                            
      244 -      text-transform: uppercase; letter-spacing: .04em; color:
          - var(--muted);                                                
      325 +    .dtable { width: 100%; border-collapse: collapse; font-siz
          +e: .8rem; }                                                   
      326 +    .dtable th {                                              
      327 +      text-align: left; padding: 8px 12px; background: var(--b
          +g);                                                           
      328 +      font-size: .7rem; font-weight: 700; text-transform: uppe
          +rcase;                                                        
      329 +      letter-spacing: .04em; color: var(--muted);             
      330        cursor: pointer; user-select: none; white-space: nowrap;
      331      }
      247 -    .dept-table th:hover { background: #E4EAF2; }             
      248 -    .dept-table th.sort-active { color: var(--blue); }        
      249 -    .dept-table td { padding: 7px 12px; border-top: 1px solid 
          -var(--border); }                                              
      250 -    .dept-table tr:hover td { background: #F8FAFC; }          
      332 +    .dtable th:hover { background: #E4EAF2; }                 
      333 +    .dtable th.sa { color: var(--blue); }                     
      334 +    .dtable td { padding: 7px 12px; border-top: 1px solid var(
          +--border); }                                                  
      335 +    .dtable tr:hover td { background: #F8FAFC; }              
      336  
      337      .pill {
      338        display: inline-block; padding: 2px 8px; border-radius: 
           4px;
      339        font-size: .7rem; font-weight: 600; color: #fff; white-s
           pace: nowrap;
      340      }
      256 -                                                              
      257 -    .mini-bar-wrap {                                          
      341 +    .mbar {                                                   
      342        display: flex; align-items: center; gap: 6px;
      343      }
      260 -    .mini-bar-track {                                         
      344 +    .mbar-t {                                                 
      345        width: 60px; height: 6px; background: var(--bg);
      346        border-radius: 999px; overflow: hidden; flex-shrink: 0;
      347      }
      264 -    .mini-bar-fill { height: 100%; border-radius: 999px; backg
          -round: var(--blue); }                                         
      348 +    .mbar-f { height: 100%; border-radius: 999px; background: 
          +var(--blue); }                                                
      349  
      266 -    /* ── Loaders / placeholders ─────────────────────────────
          -─── */                                                        
      350 +    /* ── Loaders / states ───────────────────────────────────
          +─── */                                                        
      351      .loader {
      352        display: flex; align-items: center; justify-content: cen
           ter;
      353        padding: 44px 16px; gap: 10px; color: var(--muted); font
           -size: .82rem;
     ...
      355      .spinner {
      356        width: 18px; height: 18px; border-radius: 50%;
      357        border: 2px solid var(--border); border-top-color: var(-
           -blue);
      274 -      animation: spin .7s linear infinite;                    
      358 +      animation: spin .7s linear infinite; flex-shrink: 0;    
      359      }
      360      @keyframes spin { to { transform: rotate(360deg); } }
      361  
     ...
      364        align-items: center; text-align: center;
      365        padding: 36px 20px; color: var(--muted);
      366      }
      283 -    .placeholder-icon { font-size: 1.8rem; margin-bottom: 8px;
          - }                                                            
      284 -    .placeholder-title { font-weight: 700; font-size: .82rem; 
          -color: var(--text); }                                         
      285 -    .placeholder-text  { font-size: .75rem; margin-top: 4px; m
          -ax-width: 280px; }                                            
      367 +    .ph-icon  { font-size: 1.8rem; margin-bottom: 8px; }      
      368 +    .ph-title { font-weight: 700; font-size: .82rem; color: va
          +r(--text); }                                                  
      369 +    .ph-text  { font-size: .75rem; margin-top: 4px; max-width:
          + 280px; }                                                     
      370  
      287 -    .err {                                                    
      371 +    .errbox {                                                 
      372        display: flex; align-items: center; gap: 10px;
      373        padding: 12px 14px; border-radius: 7px; margin: 8px 0;
      374        background: var(--red-light); color: #7F1D1D; font-size:
            .8rem;
      375        border: 1px solid #FECACA;
      376      }
      377  
      294 -    .info-note {                                              
      295 -      margin-top: 12px; padding: 8px 12px;                    
      296 -      background: var(--blue-light); color: #1E40AF;          
      297 -      border-radius: 6px; font-size: .73rem;                  
      298 -    }                                                         
      299 -                                                              
      378      .overflow-x { overflow-x: auto; }
      379    </style>
      380  </head>
      381  <body>
      382  
      305 -<div class="header-flag"></div>                               
      383 +<div class="flag-stripe"></div>                               
      384  <header>
      307 -  <div class="header-left">                                   
      308 -    <h1>🗳️ Elecciones Generales 2026 — Primera Vuelta</h1>    
      385 +  <div class="h-title">                                       
      386 +    <h1>🗳️ Elecciones Generales 2026</h1>                     
      387      <p id="ts">Cargando datos…</p>
      388    </div>
      311 -  <div class="header-right">                                  
      312 -    <div class="live-badge"><span class="pulse"></span> En viv
          -o</div>                                                       
      389 +  <div class="h-right">                                       
      390 +    <div class="live-dot"><span class="pulse"></span> En vivo<
          +/div>                                                         
      391      <button id="btn-refresh" class="btn btn-ghost" onclick="re
           freshAll()">↻ Actualizar</button>
      392    </div>
      393  </header>
      394  
      395 +<!-- Round switcher -->                                       
      396 +<div class="round-bar">                                       
      397 +  <button class="round-tab active" id="tab-primera" onclick="s
          +witchRound('primera')">                                       
      398 +    Primera Vuelta                                            
      399 +    <span class="rtag rtag-done" id="rtag-primera">Definitivo<
          +/span>                                                        
      400 +  </button>                                                   
      401 +  <button class="round-tab" id="tab-segunda" onclick="switchRo
          +und('segunda')">                                              
      402 +    Segunda Vuelta                                            
      403 +    <span class="rtag rtag-wait" id="rtag-segunda">Esperando</
          +span>                                                         
      404 +  </button>                                                   
      405 +</div>                                                        
      406 +                                                              
      407  <main>
      408  
      319 -  <!-- KPI row -->                                            
      320 -  <div class="kpi-grid">                                      
      321 -    <div class="kpi" id="kpi-actas">                          
      322 -      <div class="kpi-label">Actas contabilizadas</div>       
      323 -      <div class="kpi-value" id="kv-actas">—</div>            
      324 -      <div class="kpi-sub"  id="ks-actas"></div>              
      325 -      <div class="prog-wrap" id="kp-actas-wrap" style="display
          -:none">                                                       
      326 -        <div class="prog-fill" id="kp-actas" style="width:0%">
          -</div>                                                        
      409 +  <!-- ═══ PRIMERA VUELTA ════════════════════════════════════
          +═══ -->                                                       
      410 +  <div id="section-primera">                                  
      411 +                                                              
      412 +    <!-- KPIs -->                                             
      413 +    <div id="p1-kpi">                                         
      414 +      <div class="loader"><div class="spinner"></div> Cargando
          + primera vuelta…</div>                                        
      415 +    </div>                                                    
      416 +                                                              
      417 +    <!-- Finalists banner -->                                 
      418 +    <div id="p1-finalists"></div>                             
      419 +                                                              
      420 +    <!-- Observed chart -->                                   
      421 +    <div class="card">                                        
      422 +      <div class="card-head">                                 
      423 +        <div style="display:flex;align-items:center;gap:10px">
      424 +          <span class="card-title">Resultados — Primera Vuelta
          +</span>                                                       
      425 +          <span class="badge-final">✓ Resultados definitivos</
          +span>                                                         
      426 +        </div>                                                
      427 +        <div class="tabs" id="p1-ambito-tabs">                
      428 +          <button class="tab active" onclick="switchAmbito('pr
          +imera','total',this)">Nacional</button>                       
      429 +          <button class="tab" onclick="switchAmbito('primera',
          +'1',this)">Perú</button>                                      
      430 +          <button class="tab" onclick="switchAmbito('primera',
          +'2',this)">Exterior</button>                                  
      431 +        </div>                                                
      432        </div>
      433 +      <div class="card-body" id="p1-chart">                   
      434 +        <div class="loader"><div class="spinner"></div> Cargan
          +do…</div>                                                     
      435 +      </div>                                                  
      436      </div>
      329 -    <div class="kpi red">                                     
      330 -      <div class="kpi-label">Votos válidos</div>              
      331 -      <div class="kpi-value" id="kv-validos">—</div>          
      332 -      <div class="kpi-sub"  id="ks-validos"></div>            
      333 -    </div>                                                    
      334 -    <div class="kpi green">                                   
      335 -      <div class="kpi-label">Participación</div>              
      336 -      <div class="kpi-value" id="kv-part">—</div>             
      337 -      <div class="kpi-sub">Del padrón electoral</div>         
      338 -    </div>                                                    
      339 -    <div class="kpi gold">                                    
      340 -      <div class="kpi-label">Blancos + Nulos</div>            
      341 -      <div class="kpi-value" id="kv-bn">—</div>               
      342 -      <div class="kpi-sub"  id="ks-bn"></div>                 
      343 -    </div>                                                    
      344 -  </div>                                                      
      437  
      346 -  <!-- Observed results -->                                   
      347 -  <div class="card">                                          
      348 -    <div class="card-head">                                   
      349 -      <span class="card-title">Resultados Observados</span>   
      350 -      <div class="tabs">                                      
      351 -        <button class="tab active" onclick="switchAmbito('tota
          -l',this)">Nacional</button>                                   
      352 -        <button class="tab" onclick="switchAmbito('1',this)">P
          -erú</button>                                                  
      353 -        <button class="tab" onclick="switchAmbito('2',this)">E
          -xterior</button>                                              
      438 +    <!-- Dept table -->                                       
      439 +    <div class="card">                                        
      440 +      <div class="card-head">                                 
      441 +        <span class="card-title">Resultados por Departamento —
          + Primera Vuelta</span>                                        
      442 +        <span style="font-size:.72rem;color:var(--muted)">Haz 
          +clic en columna para ordenar</span>                           
      443        </div>
      444 +      <div id="p1-dept">                                      
      445 +        <div class="loader"><div class="spinner"></div> Cargan
          +do…</div>                                                     
      446 +      </div>                                                  
      447      </div>
      356 -    <div class="card-body" id="obs-container">                
      357 -      <div class="loader"><div class="spinner"></div> Cargando
          - resultados…</div>                                            
      358 -    </div>                                                    
      359 -  </div>                                                      
      448  
      361 -  <!-- Models -->                                             
      362 -  <div class="models-grid">                                   
      449 +  </div><!-- /section-primera -->                             
      450  
      364 -    <!-- Model 1: Propagation -->                             
      365 -    <div class="model-card">                                  
      366 -      <div class="model-head">                                
      367 -        <div>                                                 
      368 -          <div class="model-name">Modelo de Propagación Dinámi
          -ca</div>                                                      
      369 -          <div class="model-desc">Estratificación adaptativa p
          -or distrito con IC 95%</div>                                  
      451 +                                                              
      452 +  <!-- ═══ SEGUNDA VUELTA ════════════════════════════════════
          +════ -->                                                      
      453 +  <div id="section-segunda" style="display:none">             
      454 +                                                              
      455 +    <!-- KPIs -->                                             
      456 +    <div id="p2-kpi">                                         
      457 +      <div class="loader"><div class="spinner"></div> Cargando
          + segunda vuelta…</div>                                        
      458 +    </div>                                                    
      459 +                                                              
      460 +    <!-- Live chart -->                                       
      461 +    <div class="card">                                        
      462 +      <div class="card-head">                                 
      463 +        <span class="card-title">Resultados en Curso — Segunda
          + Vuelta</span>                                                
      464 +        <div class="tabs" id="p2-ambito-tabs">                
      465 +          <button class="tab active" onclick="switchAmbito('se
          +gunda','total',this)">Nacional</button>                       
      466 +          <button class="tab" onclick="switchAmbito('segunda',
          +'1',this)">Perú</button>                                      
      467 +          <button class="tab" onclick="switchAmbito('segunda',
          +'2',this)">Exterior</button>                                  
      468          </div>
      371 -        <span class="badge badge-on">Activo</span>            
      469        </div>
      373 -      <div class="model-body" id="prop-body">                 
      374 -        <div class="loader"><div class="spinner"></div> Calcul
          -ando proyección…</div>                                        
      470 +      <div class="card-body" id="p2-chart">                   
      471 +        <div class="loader"><div class="spinner"></div> Cargan
          +do…</div>                                                     
      472        </div>
      473      </div>
      474  
      378 -    <!-- Model 2: Placeholder -->                             
      379 -    <div class="model-card dim">                              
      380 -      <div class="model-head">                                
      381 -        <div>                                                 
      382 -          <div class="model-name">Modelo de Migración de Votos
          -</div>                                                        
      383 -          <div class="model-desc">Proyección de segunda vuelta
          - por transferencia electoral</div>                            
      475 +    <!-- Models -->                                           
      476 +    <div class="models-grid">                                 
      477 +                                                              
      478 +      <div class="model-card">                                
      479 +        <div class="model-head">                              
      480 +          <div>                                               
      481 +            <div class="model-name">Modelo de Propagación Diná
          +mica</div>                                                    
      482 +            <div class="model-desc">Estratificación adaptativa
          + por distrito con IC 95%</div>                                
      483 +          </div>                                              
      484 +          <span class="badge badge-on">Activo</span>          
      485          </div>
      385 -        <span class="badge badge-off">En desarrollo</span>    
      486 +        <div class="model-body" id="prop-body">               
      487 +          <div class="loader"><div class="spinner"></div> Calc
          +ulando proyección…</div>                                      
      488 +        </div>                                                
      489        </div>
      387 -      <div class="model-body">                                
      388 -        <div class="placeholder">                             
      389 -          <div class="placeholder-icon">🔬</div>              
      390 -          <div class="placeholder-title">Metodología en defini
          -ción</div>                                                    
      391 -          <div class="placeholder-text">                      
      392 -            Estimará el resultado de la segunda vuelta modelan
          -do cómo migran los votos                                      
      393 -            de los candidatos eliminados hacia los dos finalis
          -tas.                                                          
      490 +                                                              
      491 +      <div class="model-card dim">                            
      492 +        <div class="model-head">                              
      493 +          <div>                                               
      494 +            <div class="model-name">Modelo de Migración de Vot
          +os</div>                                                      
      495 +            <div class="model-desc">Proyección de segunda vuel
          +ta por transferencia electoral</div>                          
      496            </div>
      497 +          <span class="badge badge-off">En desarrollo</span>  
      498          </div>
      499 +        <div class="model-body">                              
      500 +          <div class="placeholder">                           
      501 +            <div class="ph-icon">🔬</div>                     
      502 +            <div class="ph-title">Metodología en definición</d
          +iv>                                                           
      503 +            <div class="ph-text">                             
      504 +              Estimará el resultado de la segunda vuelta model
          +ando cómo migran los votos                                    
      505 +              de los candidatos eliminados hacia los dos final
          +istas.                                                        
      506 +            </div>                                            
      507 +          </div>                                              
      508 +        </div>                                                
      509        </div>
      397 -    </div>                                                    
      510  
      399 -  </div>                                                      
      511 +    </div><!-- /models-grid -->                               
      512  
      401 -  <!-- Geographic breakdown -->                               
      402 -  <div class="card">                                          
      403 -    <div class="card-head">                                   
      404 -      <span class="card-title">Resultados por Departamento</sp
          -an>                                                           
      405 -      <span style="font-size:.72rem;color:var(--muted)">Haz cl
          -ic en columna para ordenar</span>                             
      513 +    <!-- Dept table -->                                       
      514 +    <div class="card">                                        
      515 +      <div class="card-head">                                 
      516 +        <span class="card-title">Resultados por Departamento —
          + Segunda Vuelta</span>                                        
      517 +        <span style="font-size:.72rem;color:var(--muted)">Haz 
          +clic en columna para ordenar</span>                           
      518 +      </div>                                                  
      519 +      <div id="p2-dept">                                      
      520 +        <div class="loader"><div class="spinner"></div> Cargan
          +do…</div>                                                     
      521 +      </div>                                                  
      522      </div>
      407 -    <div id="dept-container">                                 
      408 -      <div class="loader"><div class="spinner"></div> Cargando
          - desglose geográfico…</div>                                   
      409 -    </div>                                                    
      410 -  </div>                                                      
      523  
      524 +  </div><!-- /section-segunda -->                             
      525 +                                                              
      526  </main>
      527  
      528  <script>
      529  // ─── State ─────────────────────────────────────────────────
           ───────────────────
      530  const S = {
      417 -  obs: null,         // raw /api/observed payload             
      418 -  prop: null,        // raw /api/model/propagation payload    
      419 -  ambito: 'total',   // 'total' | '1' | '2'                   
      420 -  showAll: false,    // show all parties in chart?            
      421 -  deptKey: 'first_share',                                     
      422 -  deptAsc: false,                                             
      531 +  data:        { primera: null, segunda: null },              
      532 +  prop:        null,                                          
      533 +  activeRound: 'primera',                                     
      534 +  ambito:      { primera: 'total', segunda: 'total' },        
      535 +  showAll:     { primera: false, segunda: false },            
      536 +  dept:        {                                              
      537 +    primera: { key: 'first_share', asc: false },              
      538 +    segunda: { key: 'first_share', asc: false },              
      539 +  },                                                          
      540  };
      541  
      425 -let obsChart = null;                                          
      542 +const charts = { primera: null, segunda: null };              
      543  
      427 -// ─── Color palette ─────────────────────────────────────────
          -───────────────────                                           
      544 +// ─── Colors ────────────────────────────────────────────────
          +───────────────────                                           
      545  const FIXED = {
      546    '8':  '#E67E22', '10': '#C0392B', '35': '#2980B9',
      547    '16': '#27AE60', '14': '#8E44AD', '23': '#17A589',
      548    '2':  '#F39C12', '33': '#7F8C8D', '31': '#D35400',
      549    '21': '#2C3E50', '32': '#1ABC9C', '27': '#E91E63',
      550    '12': '#FF7043', '25': '#0288D1', '29': '#558B2F',
      434 -  '37': '#6D4C41', '22': '#AD1457', '1':  '#1565C0',          
      435 -  '20': '#00838F', '17': '#4527A0', '3':  '#558B2F',          
      551 +  '22': '#AD1457', '1':  '#1565C0', '20': '#00838F',          
      552  };
      437 -const AUTO_PAL = [                                            
      553 +const PAL = [                                                 
      554    '#4E79A7','#F28E2B','#E15759','#76B7B2','#59A14F',
      555    '#EDC948','#B07AA1','#FF9DA7','#9C755F','#BAB0AC',
      440 -  '#AEC7E8','#FFBB78','#98DF8A','#FF9896','#C5B0D5',          
      556  ];
      442 -const colorIdx = {}; let palCursor = 0;                       
      443 -function partyColor(id) {                                     
      557 +const colorMap = {}; let palIdx = 0;                          
      558 +function pColor(id) {                                         
      559    if (FIXED[id]) return FIXED[id];
      445 -  if (colorIdx[id]) return colorIdx[id];                      
      446 -  const c = AUTO_PAL[palCursor % AUTO_PAL.length]; palCursor++
          -;                                                             
      447 -  return (colorIdx[id] = c);                                  
      560 +  if (colorMap[id]) return colorMap[id];                      
      561 +  return (colorMap[id] = PAL[palIdx++ % PAL.length]);         
      562  }
      563  
      564  // ─── Formatters ────────────────────────────────────────────
           ───────────────────
      451 -const fmt2  = n => n.toFixed(2);                              
      452 -const fmt1  = n => n.toFixed(1);                              
      453 -const fmtM  = n => n >= 1e6 ? (n/1e6).toFixed(2)+'M'          
      454 -                 : n >= 1e3 ? (n/1e3).toFixed(1)+'K'          
      455 -                 : String(n);                                 
      456 -const fmtN  = n => n.toLocaleString('es-PE');                 
      457 -const fmtTs = ts => new Date(ts*1000).toLocaleString('es-PE',{
      458 -  day:'2-digit',month:'short',year:'numeric',hour:'2-digit',mi
          -nute:'2-digit'                                                
      565 +const f2  = n => n.toFixed(2);                                
      566 +const f1  = n => n.toFixed(1);                                
      567 +const fM  = n => n >= 1e6 ? (n/1e6).toFixed(2)+'M' : n >= 1e3 
          +? (n/1e3).toFixed(1)+'K' : String(n);                         
      568 +const fN  = n => n.toLocaleString('es-PE');                   
      569 +const fTs = ts => new Date(ts*1000).toLocaleString('es-PE',{  
      570 +  day:'2-digit', month:'short', year:'numeric', hour:'2-digit'
          +, minute:'2-digit'                                            
      571  });
      460 -const trunc = (s, n) => s.length > n ? s.slice(0, n-1)+'…' : s
          -;                                                             
      572 +const trunc = (s, n) => s.length > n ? s.slice(0, n-1) + '…' :
          + s;                                                           
      573  
      462 -// ─── Data helpers ──────────────────────────────────────────
          -────────────────────                                          
      463 -const BLANK_NULL = ['80','81'];                               
      574 +const BN = ['80', '81'];                                      
      575  
      576 +// ─── Data helpers ──────────────────────────────────────────
          +────────────────────                                          
      577  function mergeAmbitos(arr) {
      578    const m = JSON.parse(JSON.stringify(arr[0]));
      579    for (let i = 1; i < arr.length; i++) {
      580      const a = arr[i];
      469 -    m.actas_total += a.actas_total;                           
      581 +    m.actas_total          += a.actas_total;                  
      582      m.actas_contabilizadas += a.actas_contabilizadas;
      471 -    m.votos_emitidos += a.votos_emitidos;                     
      472 -    m.votos_validos += a.votos_validos;                       
      473 -    m.votos_habiles += a.votos_habiles;                       
      583 +    m.votos_emitidos       += a.votos_emitidos;               
      584 +    m.votos_validos        += a.votos_validos;                
      585 +    m.votos_habiles        += a.votos_habiles;                
      586      for (const [id, v] of Object.entries(a.votos_partidos))
      587        m.votos_partidos[id] = (m.votos_partidos[id] || 0) + v;
      588    }
     ...
      593    return m;
      594  }
      595  
      484 -function getAmbito(key) {                                     
      485 -  const { ambito } = S.obs;                                   
      486 -  if (key === 'total') return mergeAmbitos(ambito);           
      487 -  return ambito.find(a => a.ambito === key) || mergeAmbitos(am
          -bito);                                                        
      596 +function getAmbito(d, key) {                                  
      597 +  if (key === 'total') return mergeAmbitos(d.ambito);         
      598 +  return d.ambito.find(a => a.ambito === key) || mergeAmbitos(
          +d.ambito);                                                    
      599  }
      600  
      601  function sortedParties(votos, excludeBN = true) {
      602    return Object.entries(votos)
      492 -    .filter(([id]) => !excludeBN || !BLANK_NULL.includes(id)) 
      493 -    .map(([id, votes]) => ({ id, name: S.obs.parties[id] || `P
          -artido ${id}`, votes }))                                      
      603 +    .filter(([id]) => !excludeBN || !BN.includes(id))         
      604 +    .map(([id, votes]) => ({ id, votes }))                    
      605      .sort((a, b) => b.votes - a.votes);
      606  }
      607  
      608 +// ─── DOM helpers ───────────────────────────────────────────
          +───────────────────                                           
      609 +const setHTML = (id, h) => { const el = document.getElementByI
          +d(id); if (el) el.innerHTML = h; };                           
      610 +const loader  = msg => `<div class="loader"><div class="spinne
          +r"></div>${msg}</div>`;                                       
      611 +const errBox  = e   => `<div class="errbox">⚠️ ${e.message || e
          +}</div>`;                                                     
      612 +                                                              
      613  // ─── Fetch ─────────────────────────────────────────────────
           ───────────────────
      498 -async function fetchObs() {                                   
      614 +async function fetchRound(round) {                            
      615 +  const url = round === 'primera' ? '/api/round/first' : '/api
          +/round/second';                                               
      616    try {
      500 -    const r = await fetch('/api/observed');                   
      617 +    const r = await fetch(url);                               
      618      const j = await r.json();
      619      if (!j.ok) throw new Error(j.error);
      503 -    S.obs = j.data;                                           
      504 -    renderAll();                                              
      620 +    S.data[round] = j.data;                                   
      621 +    renderRound(round);                                       
      622    } catch(e) {
      506 -    setHTML('obs-container',  errBox(e));                     
      507 -    setHTML('dept-container', errBox(e));                     
      623 +    const pfx = round === 'primera' ? 'p1' : 'p2';            
      624 +    setHTML(`${pfx}-kpi`,       errBox(e));                   
      625 +    setHTML(`${pfx}-chart`,     errBox(e));                   
      626 +    setHTML(`${pfx}-dept`,      errBox(e));                   
      627 +    if (round === 'primera') setHTML('p1-finalists', '');     
      628    }
      629  }
      630  
     ...
      641    }
      642  }
      643  
      524 -// ─── Render helpers ────────────────────────────────────────
          -───────────────────                                           
      525 -const setHTML = (id, h) => { document.getElementById(id).inner
          -HTML = h; };                                                  
      526 -const loader  = msg => `<div class="loader"><div class="spinne
          -r"></div>${msg}</div>`;                                       
      527 -const errBox  = e  => `<div class="err">⚠️ ${e.message || e}</d
          -iv>`;                                                         
      644 +// ─── Render dispatcher ─────────────────────────────────────
          +───────────────────                                           
      645 +function renderRound(round) {                                 
      646 +  const d = S.data[round];                                    
      647 +  if (!d) return;                                             
      648 +  const ad = getAmbito(d, S.ambito[round]);                   
      649 +  const pfx = round === 'primera' ? 'p1' : 'p2';              
      650  
      529 -// ─── Render all ────────────────────────────────────────────
          -───────────────────                                           
      530 -function renderAll() {                                        
      531 -  if (!S.obs) return;                                         
      532 -  const ad = getAmbito(S.ambito);                             
      533 -  renderKPI(ad);                                              
      534 -  renderObs(ad);                                              
      535 -  renderDept();                                               
      651 +  renderKPI(pfx, ad, d.is_final);                             
      652 +  renderObsChart(round, ad, d.parties);                       
      653 +  renderDeptTable(round, d.departamental, d.parties);         
      654 +  if (round === 'primera') renderFinalists(d);                
      655 +                                                              
      656 +  // Update round tag                                         
      657 +  const tag  = document.getElementById('rtag-segunda');       
      658 +  const pct2 = S.data.segunda ? getAmbito(S.data.segunda, 'tot
          +al').pct_actas_contabilizadas : null;                         
      659 +  if (round === 'segunda' && pct2 !== null) {                 
      660 +    if (pct2 >= 100) {                                        
      661 +      tag.textContent = 'Definitivo';                         
      662 +      tag.className = 'rtag rtag-done';                       
      663 +    } else if (pct2 > 0) {                                    
      664 +      tag.textContent = f1(pct2) + '%';                       
      665 +      tag.className = 'rtag rtag-live';                       
      666 +    }                                                         
      667 +  }                                                           
      668 +                                                              
      669    document.getElementById('ts').textContent =
      537 -    'Última actualización: ' + fmtTs(S.obs.last_updated);     
      670 +    'Última actualización: ' + fTs(d.last_updated);           
      671  }
      672  
      540 -// ─── KPI ───────────────────────────────────────────────────
          -───────────────────                                           
      541 -function renderKPI(ad) {                                      
      542 -  const pct = ad.pct_actas_contabilizadas;                    
      543 -  const blancos = ad.votos_partidos['80'] || 0;               
      544 -  const nulos   = ad.votos_partidos['81'] || 0;               
      545 -  const bn = blancos + nulos;                                 
      673 +// ─── KPI cards ─────────────────────────────────────────────
          +───────────────────                                           
      674 +function renderKPI(pfx, ad, isFinal) {                        
      675 +  const pct  = ad.pct_actas_contabilizadas;                   
      676 +  const bn   = (ad.votos_partidos['80'] || 0) + (ad.votos_part
          +idos['81'] || 0);                                             
      677 +  const progId = `${pfx}-prog`;                               
      678  
      547 -  setText('kv-actas', fmt1(pct) + '%');                       
      548 -  setText('ks-actas', fmtN(ad.actas_contabilizadas) + ' de ' +
          - fmtN(ad.actas_total) + ' actas');                            
      549 -  if (pct < 100) {                                            
      550 -    show('kp-actas-wrap');                                    
      551 -    setTimeout(() => setText('kp-actas', '', 'style.width', pc
          -t + '%'), 50);                                                
      679 +  const progHTML = !isFinal                                   
      680 +    ? `<div class="prog-wrap"><div class="prog-fill" id="${pro
          +gId}"></div></div>                                            
      681 +       <div style="font-size:.68rem;color:var(--muted);margin-
          +top:4px">${fN(ad.actas_contabilizadas)} de ${fN(ad.actas_total
          +)} actas</div>`                                               
      682 +    : `<div style="font-size:.72rem;color:var(--muted);margin-
          +top:4px">${fN(ad.actas_contabilizadas)} actas · escrutinio com
          +pleto</div>`;                                                 
      683 +                                                              
      684 +  setHTML(`${pfx}-kpi`, `                                     
      685 +    <div class="kpi-grid">                                    
      686 +      <div class="kpi ${isFinal ? 'green' : ''}">             
      687 +        <div class="kpi-label">Actas contabilizadas</div>     
      688 +        <div class="kpi-value">${f1(pct)}%</div>              
      689 +        ${progHTML}                                           
      690 +      </div>                                                  
      691 +      <div class="kpi red">                                   
      692 +        <div class="kpi-label">Votos válidos</div>            
      693 +        <div class="kpi-value">${fM(ad.votos_validos)}</div>  
      694 +        <div class="kpi-sub">${f1((ad.votos_validos / ad.votos
          +_emitidos) * 100)}% de emitidos</div>                         
      695 +      </div>                                                  
      696 +      <div class="kpi green">                                 
      697 +        <div class="kpi-label">Participación</div>            
      698 +        <div class="kpi-value">${f1(ad.pct_participacion)}%</d
          +iv>                                                           
      699 +        <div class="kpi-sub">Del padrón electoral</div>       
      700 +      </div>                                                  
      701 +      <div class="kpi gold">                                  
      702 +        <div class="kpi-label">Blancos + Nulos</div>          
      703 +        <div class="kpi-value">${fM(bn)}</div>                
      704 +        <div class="kpi-sub">${f1((bn / ad.votos_emitidos) * 1
          +00)}% de emitidos</div>                                       
      705 +      </div>                                                  
      706 +    </div>`);                                                 
      707 +                                                              
      708 +  if (!isFinal) {                                             
      709 +    setTimeout(() => {                                        
      710 +      const el = document.getElementById(progId);             
      711 +      if (el) el.style.width = pct + '%';                     
      712 +    }, 60);                                                   
      713    }
      714 +}                                                             
      715  
      554 -  setText('kv-validos', fmtM(ad.votos_validos));              
      555 -  setText('ks-validos', fmt1((ad.votos_validos / ad.votos_emit
          -idos) * 100) + '% de emitidos');                              
      716 +// ─── Finalists banner ──────────────────────────────────────
          +───────────────────                                           
      717 +function renderFinalists(d) {                                 
      718 +  const ad = mergeAmbitos(d.ambito);                          
      719 +  const sp = sortedParties(ad.votos_partidos);                
      720 +  const tot = sp.reduce((s, p) => s + p.votes, 0);            
      721 +  const [f1p, f2p] = sp.slice(0, 2);                          
      722 +  if (!f1p || !f2p) return;                                   
      723  
      557 -  setText('kv-part', fmt1(ad.pct_participacion) + '%');       
      724 +  const card = (p, rank) => {                                 
      725 +    const name = d.parties[p.id] || `Partido ${p.id}`;        
      726 +    const share = (p.votes / tot) * 100;                      
      727 +    const color = pColor(p.id);                               
      728 +    return `                                                  
      729 +      <div class="finalist-card">                             
      730 +        <div class="finalist-rank">${rank === 1 ? '1° LUGAR' :
          + '2° LUGAR'}</div>                                            
      731 +        <div class="finalist-name">${trunc(name, 28)}</div>   
      732 +        <div class="finalist-share">${f2(share)}%</div>       
      733 +        <div class="finalist-votes">${fN(p.votes)} votos válid
          +os</div>                                                      
      734 +        <div class="finalist-color-bar" style="background:${co
          +lor}"></div>                                                  
      735 +      </div>`;                                                
      736 +  };                                                          
      737  
      559 -  setText('kv-bn', fmtM(bn));                                 
      560 -  setText('ks-bn', fmt1((bn / ad.votos_emitidos) * 100) + '% d
          -e emitidos');                                                 
      738 +  setHTML('p1-finalists', `                                   
      739 +    <div class="finalists-wrap">                              
      740 +      <div class="finalists-label">Avanzan a segunda vuelta</d
          +iv>                                                           
      741 +      <div class="finalists-row">                             
      742 +        ${card(f1p, 1)}                                       
      743 +        <div class="finalists-vs">VS</div>                    
      744 +        ${card(f2p, 2)}                                       
      745 +      </div>                                                  
      746 +    </div>`);                                                 
      747  }
      748  
      563 -function setText(id, val, prop, extra) {                      
      564 -  const el = document.getElementById(id);                     
      565 -  if (!el) return;                                            
      566 -  if (prop) el[prop] = extra; else el.textContent = val;      
      567 -}                                                             
      568 -function show(id) {                                           
      569 -  const el = document.getElementById(id);                     
      570 -  if (el) el.style.display = 'block';                         
      571 -}                                                             
      572 -                                                              
      749  // ─── Observed chart ────────────────────────────────────────
           ───────────────────
      750  const TOP_N = 12;
      751  
      576 -function renderObs(ad) {                                      
      577 -  const all = sortedParties(ad.votos_partidos);               
      578 -  const total = all.reduce((s, p) => s + p.votes, 0);         
      579 -  const top2ids = all.slice(0, 2).map(p => p.id);             
      580 -  const shown = S.showAll ? all : all.slice(0, TOP_N);        
      752 +function renderObsChart(round, ad, parties) {                 
      753 +  const pfx = round === 'primera' ? 'p1' : 'p2';              
      754 +  const sp  = sortedParties(ad.votos_partidos);               
      755 +  const tot = sp.reduce((s, p) => s + p.votes, 0);            
      756 +  const top2ids  = sp.slice(0, 2).map(p => p.id);             
      757 +  const visible  = S.showAll[round] ? sp : sp.slice(0, TOP_N);
      758  
      582 -  const labels  = shown.map(p => trunc(p.name, 34));          
      583 -  const shares  = shown.map(p => (p.votes / total) * 100);    
      584 -  const votes   = shown.map(p => p.votes);                    
      585 -  const colors  = shown.map(p => partyColor(p.id));           
      586 -  const advancing = shown.map(p => top2ids.includes(p.id));   
      587 -  const borders = advancing.map(a => a ? '#D4AC0D' : 'rgba(0,0
          -,0,0)');                                                      
      588 -  const bwidths = advancing.map(a => a ? 2 : 0);              
      759 +  const labels    = visible.map(p => trunc(parties[p.id] || `P
          +artido ${p.id}`, 34));                                        
      760 +  const shares    = visible.map(p => (p.votes / tot) * 100);  
      761 +  const votes     = visible.map(p => p.votes);                
      762 +  const colors    = visible.map(p => pColor(p.id));           
      763 +  const advancing = visible.map(p => top2ids.includes(p.id)); 
      764  
      590 -  const container = document.getElementById('obs-container'); 
      765 +  const container = document.getElementById(`${pfx}-chart`);  
      766    container.innerHTML = '';
      767  
      768    const wrap = document.createElement('div');
      769    wrap.className = 'chart-wrap';
      595 -  wrap.style.height = Math.max(300, shown.length * 35) + 'px';
      770 +  wrap.style.height = Math.max(280, visible.length * 34) + 'px
          +';                                                            
      771    const canvas = document.createElement('canvas');
      772    wrap.appendChild(canvas);
      773    container.appendChild(wrap);
      774  
      600 -  if (advancing.some(Boolean)) {                              
      775 +  // Legend for primera vuelta                                
      776 +  if (round === 'primera' && advancing.some(Boolean)) {       
      777      const leg = document.createElement('div');
      778      leg.className = 'chart-legend';
      779      leg.innerHTML = '<span class="legend-box"></span> Los dos 
           primeros avanzan a segunda vuelta';
      780      container.appendChild(leg);
      781    }
      782  
      607 -  if (all.length > TOP_N) {                                   
      783 +  // Show more / less button                                  
      784 +  if (sp.length > TOP_N) {                                    
      785      const btn = document.createElement('button');
      786      btn.className = 'show-more-btn';
      610 -    btn.textContent = S.showAll                               
      787 +    btn.textContent = S.showAll[round]                        
      788        ? '▲ Mostrar menos'
      612 -      : `▼ Ver todos los partidos (${all.length})`;           
      789 +      : `▼ Ver todos los partidos (${sp.length})`;            
      790      btn.onclick = () => {
      614 -      S.showAll = !S.showAll;                                 
      615 -      renderObs(ad);                                          
      791 +      S.showAll[round] = !S.showAll[round];                   
      792 +      renderObsChart(round, ad, parties);                     
      793      };
      794      container.appendChild(btn);
      795    }
      796  
      620 -  if (obsChart) { obsChart.destroy(); obsChart = null; }      
      797 +  if (charts[round]) { charts[round].destroy(); charts[round] 
          += null; }                                                     
      798  
      622 -  obsChart = new Chart(canvas, {                              
      799 +  charts[round] = new Chart(canvas, {                         
      800      type: 'bar',
      801      data: {
      802        labels,
      803        datasets: [{
      804          data: shares,
      805          backgroundColor: colors,
      629 -        borderColor: borders,                                 
      630 -        borderWidth: bwidths,                                 
      806 +        borderColor:  advancing.map(a => a ? '#D4AC0D' : 'rgba
          +(0,0,0,0)'),                                                  
      807 +        borderWidth:  advancing.map(a => a ? 2 : 0),          
      808          borderRadius: 4,
      809          borderSkipped: false,
      810        }]
     ...
      818          legend: { display: false },
      819          tooltip: {
      820            callbacks: {
      644 -            title: ctx => shown[ctx[0].dataIndex].name,       
      821 +            title: ctx => (parties[sp[ctx[0].dataIndex]?.id] |
          +| ''),                                                        
      822              label: ctx => {
      823                const i = ctx.dataIndex;
      824                return [
      648 -                `  ${fmt2(shares[i])}% de votos válidos`,     
      649 -                `  ${fmtN(votes[i])} votos`,                  
      825 +                `  ${f2(shares[i])}% de votos válidos`,       
      826 +                `  ${fN(votes[i])} votos`,                    
      827                  advancing[i] ? '  → Avanza a segunda vuelta' :
            null,
      828                ].filter(Boolean);
      652 -            },                                                
      829 +            }                                                 
      830            }
      831          }
      832        },
     ...
      834          x: {
      835            title: { display: true, text: '% de votos válidos', 
           font: { size: 11 } },
      836            grid: { color: '#F0F4F8' },
      660 -          ticks: { callback: v => v + '%' },                  
      837 +          ticks: { callback: v => v + '%' }                   
      838          },
      662 -        y: {                                                  
      663 -          grid: { display: false },                           
      664 -          ticks: { font: { size: 11 } },                      
      665 -        }                                                     
      839 +        y: { grid: { display: false }, ticks: { font: { size: 
          +11 } } }                                                      
      840        }
      841      }
      842    });
      843  }
      844  
      671 -// ─── Propagation model ─────────────────────────────────────
          -───────────────────                                           
      845 +// ─── Propagation model card ────────────────────────────────
          +───────────────────                                           
      846  function renderProp() {
      847    if (!S.prop) return;
      674 -  const valid = S.prop.parties.filter(p => !BLANK_NULL.include
          -s(p.id));                                                     
      675 -  const totalObs = valid.reduce((s, p) => s + p.observed_votes
          -, 0);                                                         
      676 -  const top2ids  = valid.slice(0, 2).map(p => p.id);          
      848 +  const valid   = S.prop.parties.filter(p => !BN.includes(p.id
          +));                                                           
      849 +  const totalOb = valid.reduce((s, p) => s + p.observed_votes,
          + 0);                                                          
      850 +  const top2ids = valid.slice(0, 2).map(p => p.id);           
      851  
      678 -  let rows = valid.slice(0, 12).map(p => {                    
      679 -    const obs = (p.observed_votes / totalObs) * 100;          
      852 +  const rows = valid.slice(0, 12).map(p => {                  
      853 +    const obs = (p.observed_votes / totalOb) * 100;           
      854      const adv = top2ids.includes(p.id);
      681 -    return `                                                  
      682 -      <tr class="${adv ? 'adv' : ''}">                        
      683 -        <td>                                                  
      684 -          <span class="party-dot" style="background:${partyCol
          -or(p.id)}"></span>                                            
      685 -          <strong>${trunc(p.name, 30)}</strong>               
      686 -          ${adv ? '<span class="badge badge-gold" style="margi
          -n-left:4px">↗ 2da vuelta</span>' : ''}                        
      687 -        </td>                                                 
      688 -        <td>${fmt2(obs)}%</td>                                
      689 -        <td><strong>${fmt2(p.projected_share)}%</strong></td> 
      690 -        <td><span class="ci">[${fmt2(p.lower_bound)}, ${fmt2(p
          -.upper_bound)}]</span></td>                                   
      691 -      </tr>`;                                                 
      855 +    return `<tr class="${adv ? 'adv' : ''}">                  
      856 +      <td>                                                    
      857 +        <span class="pdot" style="background:${pColor(p.id)}">
          +</span>                                                       
      858 +        <strong>${trunc(p.name, 30)}</strong>                 
      859 +        ${adv ? '<span class="badge badge-adv" style="margin-l
          +eft:4px">↗ 2da vuelta</span>' : ''}                           
      860 +      </td>                                                   
      861 +      <td>${f2(obs)}%</td>                                    
      862 +      <td><strong>${f2(p.projected_share)}%</strong></td>     
      863 +      <td><span class="ci">[${f2(p.lower_bound)}, ${f2(p.upper
          +_bound)}]</span></td>                                         
      864 +    </tr>`;                                                   
      865    }).join('');
      866  
      694 -  const ad = S.obs ? getAmbito('total') : null;               
      695 -  const pctDone = ad ? ad.pct_actas_contabilizadas : 0;       
      696 -  const note = pctDone >= 100                                 
      867 +  const ad2  = S.data.segunda ? getAmbito(S.data.segunda, 'tot
          +al') : null;                                                  
      868 +  const pct  = ad2 ? ad2.pct_actas_contabilizadas : 0;        
      869 +  const note = pct >= 100                                     
      870      ? '<div class="info-note">✓ Escrutinio al 100% — la proyec
           ción confirma los resultados definitivos.</div>'
      871      : '';
      872  
      873    setHTML('prop-body', `
      701 -    <table class="model-table">                               
      874 +    <table class="mtable">                                    
      875        <thead><tr>
      703 -        <th>Partido</th>                                      
      704 -        <th>Observado</th>                                    
      705 -        <th>Proyectado</th>                                   
      706 -        <th>IC 95%</th>                                       
      876 +        <th>Partido</th><th>Observado</th><th>Proyectado</th><
          +th>IC 95%</th>                                                
      877        </tr></thead>
      878        <tbody>${rows}</tbody>
      879      </table>${note}`);
      880  }
      881  
      882  // ─── Department table ──────────────────────────────────────
           ───────────────────
      713 -function renderDept() {                                       
      714 -  if (!S.obs) return;                                         
      715 -  const { departamental, parties } = S.obs;                   
      883 +function renderDeptTable(round, departamental, parties) {     
      884 +  const pfx = round === 'primera' ? 'p1' : 'p2';              
      885 +  const ds  = S.dept[round];                                  
      886  
      887    const rows = departamental
      888      .filter(d => d.ambito === '1')
      889      .map(d => {
      720 -      const sp = sortedParties(d.votos_partidos);             
      890 +      const sp  = sortedParties(d.votos_partidos);            
      891        const tot = sp.reduce((s, p) => s + p.votes, 0);
      722 -      const [f, s2] = sp;                                     
      892 +      const [f, s] = sp;                                      
      893        return {
      724 -        dept: d.departamento,                                 
      725 -        pct_actas: d.pct_actas_contabilizadas,                
      726 -        pct_part: d.pct_participacion,                        
      727 -        first_id:    f ? f.id : '',                           
      728 -        first_name:  f ? f.name : '—',                        
      729 -        first_share: f ? (f.votes / tot) * 100 : 0,           
      730 -        second_id:   s2 ? s2.id : '',                         
      731 -        second_name: s2 ? s2.name : '—',                      
      732 -        second_share:s2 ? (s2.votes / tot) * 100 : 0,         
      894 +        dept:         d.departamento,                         
      895 +        pct_actas:    d.pct_actas_contabilizadas,             
      896 +        pct_part:     d.pct_participacion,                    
      897 +        first_id:     f ? f.id : '',                          
      898 +        first_name:   f ? (parties[f.id] || `P${f.id}`) : '—',
      899 +        first_share:  f ? (f.votes / tot) * 100 : 0,          
      900 +        second_id:    s ? s.id : '',                          
      901 +        second_name:  s ? (parties[s.id] || `P${s.id}`) : '—',
      902 +        second_share: s ? (s.votes / tot) * 100 : 0,          
      903        };
      904      });
      905  
      906    rows.sort((a, b) => {
      737 -    const av = a[S.deptKey], bv = b[S.deptKey];               
      907 +    const av = a[ds.key], bv = b[ds.key];                     
      908      if (typeof av === 'string')
      739 -      return S.deptAsc ? av.localeCompare(bv) : bv.localeCompa
          -re(av);                                                       
      740 -    return S.deptAsc ? av - bv : bv - av;                     
      909 +      return ds.asc ? av.localeCompare(bv) : bv.localeCompare(
          +av);                                                          
      910 +    return ds.asc ? av - bv : bv - av;                        
      911    });
      912  
      743 -  function th(label, key) {                                   
      744 -    const active = S.deptKey === key;                         
      745 -    const arrow  = active ? (S.deptAsc ? ' ▲' : ' ▼') : '';   
      746 -    return `<th class="${active ? 'sort-active' : ''}" onclick
          -="sortDept('${key}')">${label}${arrow}</th>`;                 
      747 -  }                                                           
      913 +  const th = (label, key) => {                                
      914 +    const active = ds.key === key;                            
      915 +    const arrow  = active ? (ds.asc ? ' ▲' : ' ▼') : '';      
      916 +    return `<th class="${active ? 'sa' : ''}" onclick="sortDep
          +t('${round}','${key}')">${label}${arrow}</th>`;               
      917 +  };                                                          
      918  
      919    const tbody = rows.map(r => `
      920      <tr>
      921        <td><strong>${r.dept}</strong></td>
      922        <td>
      923          <div style="display:flex;align-items:center;gap:6px">
      754 -          <span class="pill" style="background:${partyColor(r.
          -first_id)}">${trunc(r.first_name, 24)}</span>                 
      755 -          <span style="font-weight:600">${fmt1(r.first_share)}
          -%</span>                                                      
      924 +          <span class="pill" style="background:${pColor(r.firs
          +t_id)}">${trunc(r.first_name, 24)}</span>                     
      925 +          <span style="font-weight:600">${f1(r.first_share)}%<
          +/span>                                                        
      926          </div>
      927        </td>
      928        <td>
      929          <div style="display:flex;align-items:center;gap:6px">
      760 -          <span class="pill" style="background:${partyColor(r.
          -second_id)}">${trunc(r.second_name, 24)}</span>               
      761 -          <span>${fmt1(r.second_share)}%</span>               
      930 +          <span class="pill" style="background:${pColor(r.seco
          +nd_id)}">${trunc(r.second_name, 24)}</span>                   
      931 +          <span>${f1(r.second_share)}%</span>                 
      932          </div>
      933        </td>
      934        <td>
      765 -        <div class="mini-bar-wrap">                           
      766 -          <div class="mini-bar-track">                        
      767 -            <div class="mini-bar-fill" style="width:${r.pct_ac
          -tas}%"></div>                                                 
      768 -          </div>                                              
      769 -          <span>${fmt1(r.pct_actas)}%</span>                  
      935 +        <div class="mbar">                                    
      936 +          <div class="mbar-t"><div class="mbar-f" style="width
          +:${r.pct_actas}%"></div></div>                                
      937 +          <span>${f1(r.pct_actas)}%</span>                    
      938          </div>
      939        </td>
      772 -      <td>${fmt1(r.pct_part)}%</td>                           
      940 +      <td>${f1(r.pct_part)}%</td>                             
      941      </tr>`).join('');
      942  
      775 -  setHTML('dept-container', `                                 
      943 +  setHTML(`${pfx}-dept`, `                                    
      944      <div class="overflow-x">
      777 -      <table class="dept-table">                              
      945 +      <table class="dtable">                                  
      946          <thead><tr>
      779 -          ${th('Departamento','dept')}                        
      780 -          ${th('1er lugar','first_share')}                    
      781 -          ${th('2do lugar','second_share')}                   
      782 -          ${th('Actas','pct_actas')}                          
      947 +          ${th('Departamento', 'dept')}                       
      948 +          ${th('1er lugar',   'first_share')}                 
      949 +          ${th('2do lugar',   'second_share')}                
      950 +          ${th('Actas',       'pct_actas')}                   
      951            ${th('Participación','pct_part')}
      952          </tr></thead>
      953          <tbody>${tbody}</tbody>
     ...
       955      </div>`);
       956  }
       957  
       790 -// ─── Event handlers ───────────────────────────────────────
           -────────────────────                                         
       791 -function switchAmbito(key, btn) {                            
       792 -  S.ambito = key;                                            
       793 -  document.querySelectorAll('.tab').forEach(t => t.classList.
           -remove('active'));                                           
       958 +// ─── Events ───────────────────────────────────────────────
           +────────────────────                                         
       959 +function switchRound(round) {                                
       960 +  S.activeRound = round;                                     
       961 +  document.getElementById('section-primera').style.display = 
           +round === 'primera' ? '' : 'none';                           
       962 +  document.getElementById('section-segunda').style.display = 
           +round === 'segunda' ? '' : 'none';                           
       963 +  document.getElementById('tab-primera').classList.toggle('ac
           +tive', round === 'primera');                                 
       964 +  document.getElementById('tab-segunda').classList.toggle('ac
           +tive', round === 'segunda');                                 
       965 +}                                                            
       966 +                                                             
       967 +function switchAmbito(round, key, btn) {                     
       968 +  S.ambito[round] = key;                                     
       969 +  const tabGroup = document.getElementById(                  
       970 +    round === 'primera' ? 'p1-ambito-tabs' : 'p2-ambito-tabs'
       971 +  );                                                         
       972 +  tabGroup.querySelectorAll('.tab').forEach(t => t.classList.
           +remove('active'));                                           
       973    btn.classList.add('active');
       795 -  if (S.obs) { const ad = getAmbito(key); renderKPI(ad); rend
           -erObs(ad); }                                                 
       974 +  if (S.data[round]) {                                       
       975 +    const ad = getAmbito(S.data[round], key);                
       976 +    renderKPI(round === 'primera' ? 'p1' : 'p2', ad, S.data[r
           +ound].is_final);                                             
       977 +    renderObsChart(round, ad, S.data[round].parties);        
       978 +  }                                                          
       979  }
       980  
       798 -function sortDept(key) {                                     
       799 -  S.deptKey === key ? (S.deptAsc = !S.deptAsc) : (S.deptKey =
           - key, S.deptAsc = key === 'dept');                           
       800 -  renderDept();                                              
       981 +function sortDept(round, key) {                              
       982 +  const ds = S.dept[round];                                  
       983 +  ds.key === key ? (ds.asc = !ds.asc) : (ds.key = key, ds.asc
           + = key === 'dept');                                          
       984 +  if (S.data[round]) renderDeptTable(round, S.data[round].dep
           +artamental, S.data[round].parties);                          
       985  }
       986  
       987  async function refreshAll() {
       988    const btn = document.getElementById('btn-refresh');
       989    btn.disabled = true; btn.textContent = '↻ Actualizando…';
       806 -  S.obs = null; S.prop = null;                               
       807 -  setHTML('obs-container',  loader('Cargando resultados…')); 
       808 -  setHTML('dept-container', loader('Cargando desglose geográf
           -ico…'));                                                     
       809 -  setHTML('prop-body',      loader('Calculando proyección…'))
           -;                                                            
       810 -  await fetchObs();                                          
       811 -  await fetchProp();                                         
       990 +                                                             
       991 +  // Reset loaders                                           
       992 +  ['primera','segunda'].forEach(r => {                       
       993 +    const p = r === 'primera' ? 'p1' : 'p2';                 
       994 +    setHTML(`${p}-kpi`,   loader('Cargando…'));              
       995 +    setHTML(`${p}-chart`, loader('Cargando…'));              
       996 +    setHTML(`${p}-dept`,  loader('Cargando…'));              
       997 +    S.data[r] = null;                                        
       998 +    if (charts[r]) { charts[r].destroy(); charts[r] = null; }
       999 +  });                                                        
      1000 +  S.prop = null;                                             
      1001 +  setHTML('p1-finalists', '');                               
      1002 +  setHTML('prop-body', loader('Calculando proyección…'));    
      1003 +                                                             
      1004 +  await Promise.all([fetchRound('primera'), fetchRound('segun
           +da')]);                                                      
      1005 +  fetchProp();                                               
      1006 +                                                             
      1007    btn.disabled = false; btn.textContent = '↻ Actualizar';
      1008  }
      1009  
      1010  // ─── Init ─────────────────────────────────────────────────
            ─────────────────────
      1011  (async () => {
       817 -  await fetchObs();                                          
       818 -  fetchProp();   // runs in background, no await             
      1012 +  await Promise.all([fetchRound('primera'), fetchRound('segun
           +da')]);                                                      
      1013 +  fetchProp();  // background, no await                      
      1014  })();
      1015  </script>
      1016  </body>

● Now let's restart the server and verify all endpoints:

  Ran 1 shell command (ctrl+o to expand)

● Background command "Start dashboard server on port 5000" was stopped

● All four endpoints work. The server is running at http://127.0.0.1:5000 — open
  it in your browser.

  Here's what changed:

  Primera Vuelta tab (stable):
  - Reads from first_round_agg_results/, is_final: true
  - "Resultados definitivos" green badge on the chart header
  - Blue gradient finalists banner dynamically shows the top 2 advancing to
  segunda vuelta (computed from the data, not hardcoded)
  - KPI actas card shows green since it's 100%
  - No models section — final results don't need projection

  Segunda Vuelta tab (live):
  - Reads from processed_results/ — whatever the scraper puts there as
  second-round counting proceeds
  - KPI actas card shows a progress bar while < 100%
  - Round tag in the tab bar updates to show live counting % (e.g. 47.3%) or
  Definitivo when done
  - Propagation model + vote migration placeholder

  To wire up the second model when ready, add /api/model/migration to app.py and
  call fetchMigration() in the JS, pointing it at the placeholder card's body
  element — same pattern as the propagation model.

✻ Crunched for 5m 45s

※ recap: Building an election results dashboard for Peru's 2026 runoff. The frontend is done with two tabs — Primera Vuelta (stable, from first_round_agg_results) and Segunda Vuelta (live, fed by the scraper). Next step is defining the vote migration model methodology. (disable recaps in /config)