# Gate P4.4 load-versus-control

- modello: `hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest`
- DT_NOM congelato = 2.930748 s (pilota P2.9, requisito 5)
- order_seed dichiarato = gate-seed-20261107 (requisito 3)
- geometria (12,32) (requisito 4)
- 12 blocchi / 6 coppie, un blocco per invocazione

## Risultato

gate: fail; controlli utilizzabili = 4/6 coppie, quorum = 4; chain_status = ''

- bias_w = 0.479571 W contro soglia mediana_c(budget_base_w) = 0.262324 W

## Blocchi di controllo

- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-1__b01: usable=False, unstable=True, pre_range_w=0.587964, dP=-1.192353, E_net=-2.560977 J, dt_W=2.931052 s, budget_base_j=1.948329, budget_base_w=0.66472 W, window=exact-counter, block_pass=None — |dP|=1.19235 W > 1 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-2__b01: usable=False, unstable=True, pre_range_w=0.057506, dP=1.085987, E_net=0.404447 J, dt_W=2.931258 s, budget_base_j=1.593883, budget_base_w=0.543754 W, window=exact-counter, block_pass=None — |dP|=1.08599 W > 1 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-3__b01: usable=True, unstable=False, pre_range_w=0.137864, dP=0.588228, E_net=2.63879 J, dt_W=2.931129 s, budget_base_j=0.885447, budget_base_w=0.302084 W, window=exact-counter, block_pass=False — pre_range_w=0.137864 W <= 1 W e |dP|=0.588228 W <= 1 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-4__b01: usable=True, unstable=False, pre_range_w=0.328218, dP=-0.106925, E_net=0.313109 J, dt_W=2.960884 s, budget_base_j=0.511043, budget_base_w=0.172598 W, window=exact-counter, block_pass=True — pre_range_w=0.328218 W <= 1 W e |dP|=0.106925 W <= 1 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-5__b01: usable=True, unstable=False, pre_range_w=0.611478, dP=0.899231, E_net=2.895655 J, dt_W=2.931281 s, budget_base_j=1.593793, budget_base_w=0.543719 W, window=exact-counter, block_pass=False — pre_range_w=0.611478 W <= 1 W e |dP|=0.899231 W <= 1 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-6__b01: usable=True, unstable=False, pre_range_w=0.173247, dP=-0.410028, E_net=-0.210546 J, dt_W=2.93097 s, budget_base_j=0.652325, budget_base_w=0.222563 W, window=exact-counter, block_pass=True — pre_range_w=0.173247 W <= 1 W e |dP|=0.410028 W <= 1 W

## Propagazione cooldown (scelta operativa)

- controllo-1: P_pre_ref=7.425244, cooldown_timeout='false'
- controllo-2: P_pre_ref=5.864781, cooldown_timeout='true'
- controllo-3: P_pre_ref=5.674992, cooldown_timeout='false'
- controllo-4: P_pre_ref=6.469378, cooldown_timeout='true'
- controllo-5: P_pre_ref=5.818223, cooldown_timeout='false'
- controllo-6: P_pre_ref=4.534135, cooldown_timeout='true'

## Rapporto J/token (F.12, grandezza riportata)

- bias = 2.877–5.275 % di J/token (scala ancorata 1 W ~ 6–11%)

## Ragioni

- |bias_w|=0.479571 W > mediana_c(budget_base_w,c)=0.262324 W

## Artefatti

- results CSV: C:\Users\Massimo\Documents\CasualWatt\CWProject\cwEnergyModular\results\p44_gate_20261107\casualwatt_v4_results_p44.csv
- block summary CSV: C:\Users\Massimo\Documents\CasualWatt\CWProject\cwEnergyModular\results\p44_gate_20261107\casualwatt_v4_block_summary_p44.csv
- riepiloghi controllo (JSON, forma --blocks): C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\p44_gate_20261107\blocks_controllo.json
- run ids: 91639d6fb11147dcad6c512a8fd1179f, c930e29802284aeb912b4e5868137ce3, 04f9e98081af474ea2271ba8bd31d7dc, 923b4bd8627546e6b2222762a0315597, 33f84ca003204bf1aaccf5d7989d556d, 48a32c3b48f94af68861b955705740ce, f2f726dd6b794f00ad90cf6c6e3e2e27, bc6c61d5f2084b4baf6af9974c679ec8, 9a67dd35e3f3499c9ec84f3e1ab49a7b, f27dac3cc91d4fada7a73959092322fd, 8df9f342bae44f39badf6ed5da763960, 94c8a9a1138b4c33bbfb188ed72b7c96
- git head: c326d4646932cb36426edf7c4c3a084909aa9900
- runner sha256: a8a35078fe74a98a69d5b57192aec42fe2b3e5f8f45e9508b656918353e1fe4d
