#!/usr/bin/env python3
"""External MUDILab reference validator. Does not modify professor's files.
Requires pyagrum. Counterfactuals intentionally excluded.
"""
import argparse, csv, json, math, sys
from pathlib import Path
try:
    import pyagrum as gum
    import pyagrum.causal as csl
except ImportError:
    sys.exit('ERRORE: pyAgrum non installato. Usa l’ambiente Python del notebook e installa: python -m pip install pyagrum pandas')

DEFAULT = [
{"task_id":"CP1","task_type":"cond_prob","query":"Given that the driving quality is normal, how likely is it that the age of the driver is senior?","target_variable":"Age","target_state":"Senior","evidence":{"DrivQuality":"Normal"},"mapping_status":"probable","notes":"Mapping diretto."},
{"task_id":"CP2","task_type":"cond_prob","query":"Given that the damage to a car is classified as Mild, how likely is that the driving quality is excellent?","target_variable":"DrivQuality","target_state":"Excellent","evidence":{"ThisCarDam":"Mild"},"mapping_status":"review","notes":"Interpreta damage to a car come ThisCarDam, non Accident; verificare la traduzione dell’agente."},
{"task_id":"CP3","task_type":"cond_prob","query":"Given that the neighbourhood is Suburb, how likely is the miles count TwentyThou?","target_variable":"Mileage","target_state":"TwentyThou","evidence":{"HomeBase":"Suburb"},"mapping_status":"probable","notes":"Mapping diretto."},
{"task_id":"IN1","task_type":"inter","query":"Probability of severe car damage if mileage is changed to twenty thousand?","target_variable":"ThisCarDam","target_state":"Severe","intervention":{"Mileage":"TwentyThou"},"mapping_status":"review","notes":"ThisCarDam=Severe; la rete contiene anche Accident=Severe. Confermare."},
{"task_id":"IN2","task_type":"inter","query":"Probability of excellent driving skill if age is changed to senior?","target_variable":"DrivQuality","target_state":"Excellent","intervention":{"Age":"Senior"},"mapping_status":"review","notes":"DrivingSkill non ha stato Excellent (ha Expert); mappato su DrivQuality=Excellent. Confermare."},
{"task_id":"IN3","task_type":"inter","query":"Probability of older vehicleyear if socio-economic status is Prole?","target_variable":"VehicleYear","target_state":"Older","intervention":{"SocioEcon":"Prole"},"mapping_status":"probable","notes":"Mapping diretto."},
{"task_id":"CO1","task_type":"coherence","query":"Is a mild severity accident involving a car valued at twenty thousand dollars compatible with cautious risk aversion?","target_variable":"Accident","target_state":"Mild","evidence":{"CarValue":"TwentyThou","RiskAversion":"Cautious"},"threshold":0.60,"mapping_status":"review","notes":"Interpretato come Accident=Mild; verificare se si intendeva ThisCarDam=Mild."},
{"task_id":"CO2","task_type":"coherence","query":"Is drive quality Normal compatible with proposed cost HundredThousand?","target_variable":"DrivQuality","target_state":"Normal","evidence":{"PropCost":"HundredThou"},"threshold":0.60,"mapping_status":"review","notes":"Verificare direzione target/evidenza e alias HundredThousand."},
{"task_id":"CO3","task_type":"coherence","query":"Is socio-economic status Wealthy compatible with a Fair cushioning system?","target_variable":"Cushioning","target_state":"Fair","evidence":{"SocioEcon":"Wealthy"},"threshold":0.60,"mapping_status":"review","notes":"Interpretato come P(Cushioning=Fair | SocioEcon=Wealthy); verificare direzione."}
]

def validate_state(bn, var, state):
    if var not in bn.names(): raise ValueError(f'Variabile assente: {var}')
    labels=list(bn.variable(var).labels())
    if state not in labels: raise ValueError(f'Stato {var}={state} non valido; ammessi: {labels}')

def cond_prob(bn, target, state, evidence):
    validate_state(bn,target,state)
    for v,s in evidence.items(): validate_state(bn,v,s)
    ie=gum.LazyPropagation(bn); ie.setEvidence(evidence); ie.makeInference()
    return float(ie.posterior(target)[list(bn.variable(target).labels()).index(state)])

def flatten(x):
    if hasattr(x,'tolist'): x=x.tolist()
    if isinstance(x,(int,float)): return [float(x)]
    if isinstance(x,(list,tuple)):
        return [n for y in x for n in flatten(y)]
    return []

def intervention_prob(bn,target,state,doing):
    validate_state(bn,target,state)
    for v,s in doing.items(): validate_state(bn,v,s)
    cm=csl.CausalModel(gum.BayesNet(bn)); vars=list(doing)
    if len(vars)==1: formula,impact,explanation=csl.causalImpact(cm,on=target,doing=vars[0],values=doing)
    elif len(vars)==2: formula,impact,explanation=csl.causalImpact(cm,on=target,doing=vars,values=doing)
    else: raise ValueError('Interventi su una o due variabili supportati.')
    if formula is None: raise RuntimeError(f'Intervento non identificabile: {explanation}')
    labels=list(bn.variable(target).labels())
    for key in ({target:state}, state):
        try: return float(impact[key])
        except Exception: pass
    vals=flatten(impact)
    if len(vals)!=len(labels): raise RuntimeError(f'Formato impact pyAgrum non riconosciuto: {type(impact).__name__}; valori={vals}')
    return vals[labels.index(state)]

def reference(bif, queries):
    bn=gum.loadBN(str(bif)); rows=[]
    for q in queries:
        r={"task_id":q["task_id"],"task_type":q["task_type"],"query":q["query"],"target_variable":q["target_variable"],"target_state":q["target_state"],"evidence_json":json.dumps(q.get("evidence",{}),ensure_ascii=False),"intervention_json":json.dumps(q.get("intervention",{}),ensure_ascii=False),"threshold":q.get("threshold",""),"mapping_status":q.get("mapping_status","review"),"notes":q.get("notes",""),"expected_probability":"","expected_label":"","reference_status":"OK","error":""}
        try:
            if q['task_type'] in ('cond_prob','coherence'): p=cond_prob(bn,q['target_variable'],q['target_state'],q.get('evidence',{}))
            elif q['task_type']=='inter': p=intervention_prob(bn,q['target_variable'],q['target_state'],q.get('intervention',{}))
            else: raise ValueError('Task non supportato; i controfattuali sono esclusi.')
            r['expected_probability']=f'{p:.10f}'
            if q.get('threshold') is not None: r['expected_label']='compatible' if p>=float(q['threshold']) else 'not_strongly_compatible'
        except Exception as e: r['reference_status']='ERROR'; r['error']=f'{type(e).__name__}: {e}'
        rows.append(r)
    return rows

def write_csv(path,rows):
    if not rows: raise ValueError('Nessun risultato da scrivere')
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def fnum(x):
    try:
        y=float(x); return y if math.isfinite(y) else None
    except (TypeError,ValueError): return None

def compare(ref_path,agent_path,out_path,tol):
    with open(ref_path,encoding='utf-8-sig',newline='') as f: refs={r['task_id']:r for r in csv.DictReader(f)}
    with open(agent_path,encoding='utf-8-sig',newline='') as f: agents=list(csv.DictReader(f))
    if not agents: raise ValueError('CSV delle risposte agente vuoto')
    missing={'task_id','run','agent_probability'}-set(agents[0])
    if missing: raise ValueError(f'Colonne mancanti: {sorted(missing)}')
    out=[]
    norm={'yes':'compatible','true':'compatible','compatible':'compatible','no':'not_strongly_compatible','incompatible':'not_strongly_compatible','not strongly compatible':'not_strongly_compatible','not_strongly_compatible':'not_strongly_compatible'}
    for a in agents:
        r=refs.get(a['task_id'],{}); expected=fnum(r.get('expected_probability')); actual=fnum(a.get('agent_probability'))
        err=abs(actual-expected) if actual is not None and expected is not None else None
        el=r.get('expected_label',''); al=norm.get((a.get('agent_label') or '').strip().lower(),(a.get('agent_label') or '').strip().lower())
        out.append({'task_id':a['task_id'],'run':a['run'],'agent_probability':a.get('agent_probability',''),'expected_probability':r.get('expected_probability',''),'absolute_error':f'{err:.10f}' if err is not None else '', 'numeric_pass':'PASS' if err is not None and err<=tol else ('FAIL' if err is not None else 'NOT_COMPARABLE'),'agent_label':a.get('agent_label',''),'expected_label':el,'label_pass':('PASS' if al==el else 'FAIL') if el else '', 'mapping_status':r.get('mapping_status',''),'reference_status':r.get('reference_status','MISSING'),'agent_text':a.get('agent_text','')})
    write_csv(out_path,out)
    errs=[fnum(r['absolute_error']) for r in out if r['absolute_error']]
    print(f'Risposte: {len(out)} | valori numerici confrontabili: {len(errs)}')
    if errs: print(f'MAE={sum(errs)/len(errs):.6f}; PASS numerici={sum(r["numeric_pass"]=="PASS" for r in out)}/{len(errs)} (tolleranza {tol})')
    print('Report:',out_path)

def main():
    p=argparse.ArgumentParser(description='Validatore indipendente per MUDILab')
    p.add_argument('--bif',type=Path,default=Path('insurance_grafo.bif')); p.add_argument('--queries',type=Path,default=Path('queries.json'))
    p.add_argument('--generate-reference',action='store_true'); p.add_argument('--reference-out',type=Path,default=Path('ground_truth.csv'))
    p.add_argument('--agent-results',type=Path); p.add_argument('--compare',action='store_true'); p.add_argument('--comparison-out',type=Path,default=Path('comparison_report.csv')); p.add_argument('--tolerance',type=float,default=0.02)
    a=p.parse_args()
    if not a.bif.exists(): p.error(f'File BIF non trovato: {a.bif}')
    queries=json.loads(a.queries.read_text(encoding='utf-8')) if a.queries.exists() else DEFAULT
    if a.generate_reference:
        rows=reference(a.bif,queries); write_csv(a.reference_out,rows); print('Riferimenti:',a.reference_out)
        for r in rows: print(f"{r['task_id']}: {r['reference_status']} p={r['expected_probability'] or 'N/D'} mapping={r['mapping_status']} {r['error']}")
        if any(r['reference_status']=='ERROR' for r in rows): print('ATTENZIONE: risolvere gli ERROR prima di usare il ground truth.')
    if a.compare:
        if not a.agent_results: p.error('--compare richiede --agent-results agent_outputs.csv')
        if not a.reference_out.exists(): p.error('Esegui prima --generate-reference')
        compare(a.reference_out,a.agent_results,a.comparison_out,a.tolerance)
    if not a.generate_reference and not a.compare: p.print_help()
if __name__=='__main__': main()
