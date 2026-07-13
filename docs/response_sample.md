you › /machine M104
active machine set to M104

you › M104 just triggered a critical vibration alert. What's wrong and what do we do?
  ↳ get_machine_by_id  {'id': 'M104'}
  ↳ filter_alert_by_machine_id  {'value': 'M104'}
  ↳ filter_workorder_by_machine_id  {'value': 'M104'}
  ↳ get_technician_by_id  {'id': 'T03'}
  ↳ filter_faulthistory_by_machine_id  {'value': 'M104'}
  ↳ filter_part_by_category  {'value': 'bearing'}

iris ›
What's wrong with M104 (Alpha Mill)                                                                                                                                                               

Current state                                                                                                                                                                                     

 • Status: fault — the machine is down                                                                                                                                                            
 • Alert A301: critical, open, vibration type — 9.2 mm/s vs. threshold of 8.0 mm/s (16% over)                                                                                                     
 • Machine readings: vibration 9.2 mm/s, temp 68 °C, 512 hrs since last major service                                                                                                             

Root cause — likely front bearing failure. This isn't a one-off: M104 has a documented history of the same symptom.                                                                               

                                                                                                        
 Fault  Symptom                    Root cause                  Resolution                      Downtime 
 ────────────────────────────────────────────────────────────────────────────────────────────────────── 
 FH801  High vibration (8.1 mm/s)  Front bearing wear          Bearing replacement (SKF 6205)  2.1 h    
 FH802  Spindle noise              Loose collet (not bearing)  Collet re-torque                0.5 h    
                                                                                                        

The current 9.2 mm/s reading is higher than the prior bearing-wear event (8.1), and the open work order already names the front bearing as the suspected culprit — consistent with FH801.         

What to do                                                                                                                                                                                        

A response is already staged — work order WO1041 (urgent repair): "Inspected and replace SKF 6205 bearing." Readiness check:                                                                      

 • ✅ Technician: T03 Diana Cruz — mechanical specialty, certified in Bearing & Drive Systems, and currently available (morning shift). She's already assigned; just dispatch to start.           
 • ✅ Part in stock: SKF 6205 Bearing (P201) — 4 units on hand vs. reorder point of 2 (3-day lead time, so no waiting needed).                                                                    
 • ⚠️ Action needed: WO1041 is still scheduled, not in_progress — it hasn't been kicked off yet.                                                                                                  

Recommended next steps:                                                                                                                                                                           

 1 Move WO1041 to in_progress and have Diana Cruz execute the bearing replacement now while she's available and the part is on the shelf.                                                         
 2 On teardown, verify the front bearing is the failure (consistent with FH801); rule out the collet issue seen in FH802.                                                                         
 3 After repair, confirm vibration drops back below the 8.0 mm/s threshold before returning Alpha Mill to running.                                                                                

Want me to check the full alert list for any other machines trending toward a similar fault, or look at Diana's other scheduled work before she starts?   