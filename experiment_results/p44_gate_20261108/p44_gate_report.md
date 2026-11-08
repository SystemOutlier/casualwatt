# Gate P4.4 load-versus-control

- modello: `hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest`
- DT_NOM congelato = 2.930748 s (pilota P2.9, requisito 5)
- order_seed dichiarato = gate-seed-20261107 (requisito 3)
- geometria (12,32) (requisito 4)
- 12 blocchi / 6 coppie, un blocco per invocazione

## Risultato

gate: fail; controlli utilizzabili = 6/6 coppie, quorum = 4; chain_status = ''
- utilizzabili con block_pass=False: 4/6 (il criterio per blocco e' riportato, non decide lo status del gate)

- bias_w = 0.125171 W contro soglia mediana_c(budget_base_w) = 0.117995 W

## Blocchi di controllo

- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-1__b01: usable=True, unstable=False, pre_range_w=0.694745, dP=-0.109395, E_net=1.657777 J, dt_W=2.931408 s, E_net/dt_W=0.565522 W, budget_base_j=1.030838, budget_base_w=0.351653 W, window=exact-counter, block_pass=False — pre_range_w=0.694745 W <= 1 W e |dP|=0.109395 W <= 1 W
  baseline: P_pre_ref propagata dal carico=4.529809 W, propria del blocco=3.710856 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-2__b01: usable=True, unstable=False, pre_range_w=0.52469, dP=0.102105, E_net=0.367103 J, dt_W=2.931368 s, E_net/dt_W=0.125233 W, budget_base_j=0.783455, budget_base_w=0.267266 W, window=exact-counter, block_pass=True — pre_range_w=0.52469 W <= 1 W e |dP|=0.102105 W <= 1 W
  baseline: P_pre_ref propagata dal carico=3.628981 W, propria del blocco=3.82036 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-3__b01: usable=True, unstable=False, pre_range_w=0.044423, dP=0.017923, E_net=-0.07369 J, dt_W=2.931679 s, E_net/dt_W=-0.025136 W, budget_base_j=0.070217, budget_base_w=0.023951 W, window=exact-counter, block_pass=False — pre_range_w=0.044423 W <= 1 W e |dP|=0.017923 W <= 1 W
  baseline: P_pre_ref propagata dal carico=4.22374 W, propria del blocco=3.780604 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-4__b01: usable=True, unstable=False, pre_range_w=0.397957, dP=-0.078493, E_net=-0.175905 J, dt_W=2.931941 s, E_net/dt_W=-0.059996 W, budget_base_j=0.594633, budget_base_w=0.202812 W, window=exact-counter, block_pass=True — pre_range_w=0.397957 W <= 1 W e |dP|=0.078493 W <= 1 W
  baseline: P_pre_ref propagata dal carico=3.742275 W, propria del blocco=3.741051 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-5__b01: usable=True, unstable=False, pre_range_w=0.059282, dP=-0.02981, E_net=0.26957 J, dt_W=2.931507 s, E_net/dt_W=0.091956 W, budget_base_j=0.097262, budget_base_w=0.033178 W, window=exact-counter, block_pass=False — pre_range_w=0.059282 W <= 1 W e |dP|=0.02981 W <= 1 W
  baseline: P_pre_ref propagata dal carico=3.66947 W, propria del blocco=3.718599 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-6__b01: usable=True, unstable=False, pre_range_w=0.032977, dP=-0.03802, E_net=0.156772 J, dt_W=2.931015 s, E_net/dt_W=0.053487 W, budget_base_j=0.073756, budget_base_w=0.025164 W, window=exact-counter, block_pass=False — pre_range_w=0.032977 W <= 1 W e |dP|=0.03802 W <= 1 W
  baseline: P_pre_ref propagata dal carico=3.755477 W, propria del blocco=3.722311 W

## Grandezze riportate, non criterio

E_net/dt_W per TUTTI i controlli (anche non utilizzabili) e statistiche descrittive fra blocchi: media, sd campionaria (ddof=1), SE, CI95 t di Student. Non decidono l'esito del gate, che resta F.12; non entrano nello schema CSV. background_load prima/dopo dal riepilogo del runner (P1.4).

| blocco | utilizzabile | E_net/dt_W (W) | background_load prima | dopo |
|---|---|---|---|---|
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-1__b01 | True | 0.565522 | False | False |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-2__b01 | True | 0.125233 | False | False |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-3__b01 | True | -0.025136 | False | False |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-4__b01 | True | -0.059996 | False | False |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-5__b01 | True | 0.091956 | False | False |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-6__b01 | True | 0.053487 | False | False |

### Statistiche su tutti i controlli

- n=6, media=0.125178 W, sd=0.226729 W, SE=0.092562 W, CI95=[-0.112760, 0.363115] W (t=2.5706, provenienza: scipy)

### Statistiche su soli utilizzabili

- n=6, media=0.125178 W, sd=0.226729 W, SE=0.092562 W, CI95=[-0.112760, 0.363115] W (t=2.5706, provenienza: scipy)

## Propagazione cooldown (scelta operativa)

- controllo-1: P_pre_ref=4.529809, baseline propria del blocco=3.710856, cooldown_timeout='true'
- controllo-2: P_pre_ref=3.628981, baseline propria del blocco=3.82036, cooldown_timeout='false'
- controllo-3: P_pre_ref=4.22374, baseline propria del blocco=3.780604, cooldown_timeout='false'
- controllo-4: P_pre_ref=3.742275, baseline propria del blocco=3.741051, cooldown_timeout='false'
- controllo-5: P_pre_ref=3.66947, baseline propria del blocco=3.718599, cooldown_timeout='false'
- controllo-6: P_pre_ref=3.755477, baseline propria del blocco=3.722311, cooldown_timeout='false'

## Precondizione di quiete

Prima di OGNI blocco (load e control): 3 letture consecutive con background_load=False; una lettura rumorosa azzera il conteggio; al tetto (600 s) il run si ferma. Precondizione di esecuzione lato tool (P1.4): non entra nel criterio F.12.

- carico-1 (load): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (3.1%), Taskmgr.exe pid=3224 (3.1%),  pid=288 (0.0%), Registry pid=328 (0.0%), smss.exe pid=1032 (0.0%)
- controllo-1 (control): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (3.1%), llama-server.exe pid=14568 (3.1%), WMIADAP.exe pid=13020 (1.6%),  pid=288 (0.0%), Registry pid=328 (0.0%)
- carico-2 (load): attesa=9.0 s, letture=3, top-5 alla partenza: svchost.exe pid=2064 (1.6%), python.exe pid=16744 (1.6%), System pid=4 (0.0%),  pid=288 (0.0%), Registry pid=328 (0.0%)
- controllo-2 (control): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (1.6%), svchost.exe pid=4852 (1.6%), python.exe pid=16744 (1.6%),  pid=288 (0.0%), Registry pid=328 (0.0%)
- carico-3 (load): attesa=9.0 s, letture=3, top-5 alla partenza: svchost.exe pid=3780 (1.6%), python.exe pid=16744 (1.6%), System pid=4 (0.0%),  pid=288 (0.0%), Registry pid=328 (0.0%)
- controllo-3 (control): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (3.1%),  pid=288 (0.0%), Registry pid=328 (0.0%), smss.exe pid=1032 (0.0%), svchost.exe pid=1296 (0.0%)
- carico-4 (load): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (3.1%), vmware-usbarbitrator64.exe pid=6092 (1.6%),  pid=288 (0.0%), Registry pid=328 (0.0%), smss.exe pid=1032 (0.0%)
- controllo-4 (control): attesa=9.0 s, letture=3, top-5 alla partenza: csrss.exe pid=1724 (1.6%), python.exe pid=16744 (1.6%), System pid=4 (0.0%),  pid=288 (0.0%), Registry pid=328 (0.0%)
- carico-5 (load): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (1.6%),  pid=288 (0.0%), Registry pid=328 (0.0%), smss.exe pid=1032 (0.0%), svchost.exe pid=1296 (0.0%)
- controllo-5 (control): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (3.1%), vmware-usbarbitrator64.exe pid=6092 (1.6%), python.exe pid=16744 (1.6%),  pid=288 (0.0%), Registry pid=328 (0.0%)
- carico-6 (load): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (0.0%),  pid=288 (0.0%), Registry pid=328 (0.0%), smss.exe pid=1032 (0.0%), svchost.exe pid=1296 (0.0%)
- controllo-6 (control): attesa=9.0 s, letture=3, top-5 alla partenza: System pid=4 (3.1%), dwm.exe pid=2252 (1.6%),  pid=288 (0.0%), Registry pid=328 (0.0%), smss.exe pid=1032 (0.0%)

## Rapporto J/token (F.12, grandezza riportata)

- bias = 0.751–1.377 % di J/token (scala ancorata 1 W ~ 6–11%)

## Ragioni

- |bias_w|=0.125171 W > mediana_c(budget_base_w,c)=0.117995 W

## Serie di potenza grezza (diagnostica)

Campioni del sampler nella finestra passiva [t0, t1] del contatore; potenza = delta del contatore cumulativo / delta t fra campioni consecutivi. Diagnostica per distinguere deriva e picchi: non entra nel criterio F.12.

- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-1__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-2__b01: 6 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-3__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-4__b01: 6 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-5__b01: 6 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-6__b01: 6 campioni

## Artefatti

- results CSV: C:\Users\Massimo\Documents\CasualWatt\CWProject\cwEnergyModular\results\p44_gate_20261108\casualwatt_v4_results_p44.csv
- block summary CSV: C:\Users\Massimo\Documents\CasualWatt\CWProject\cwEnergyModular\results\p44_gate_20261108\casualwatt_v4_block_summary_p44.csv
- riepiloghi controllo (JSON, forma --blocks): C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\p44_gate_20261108\blocks_controllo.json
- serie di potenza grezza dei controlli (JSON): C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\p44_gate_20261108\control_power_series.json
- run ids: 9be9e693300249a59384d9679eeb547b, 32678edc962c4f79be7124a6b9b122e8, 3af05ce0d9624c81bcb7cd36ed940a4f, 33fa107cc73d4b0381ad82fc051ae906, ebca05cc591244fab9f8abe1dab69d85, c09b26e8f622434eaff04fa36664a016, ae75d433cdda40598e3cd57ca089d4ee, 4677b0f7c1ae4e17bcda90ccb81c8e11, 6ca224d025604e1890d5fccd54144624, a745da9c18884210bbcc62f127c6b568, 4a156fd7e75e4f53918cad67345b160e, 97631587a7ba4f78acbdd73f4adfcbef
- git head: 39a34a9abd31b6774b7f2bda265f8320d929eaa1
- runner sha256: 99846365de073fa112a1594b5659d73d393a86ddf6cca3e196467a25f7881ee0
