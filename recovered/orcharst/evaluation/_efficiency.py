import json, glob, collections

files = glob.glob('evaluation/results/exp_full30_v1/raw/*.json')
by = collections.defaultdict(lambda: {'n':0,'res':0,'cost':0.0,'lat':0.0,'llm':0,'in':0,'out':0,'first':0})
for f in files:
    d = json.load(open(f, encoding='utf-8'))
    s = d['system']; b = by[s]
    b['n'] += 1
    if d.get('end_to_end_resolved'): b['res'] += 1
    b['cost'] += d.get('cost',{}).get('estimated_usd') or 0
    b['lat'] += d.get('execution',{}).get('latency_seconds') or 0
    b['llm'] += d.get('execution',{}).get('llm_calls') or 0
    b['in'] += d.get('execution',{}).get('input_tokens') or 0
    b['out'] += d.get('execution',{}).get('output_tokens') or 0
    if d.get('repair',{}).get('first_attempt_success') is True: b['first'] += 1

hdr = "%-14s %3s %4s %7s %9s %8s %5s %8s %8s" % ("system","N","res","e2e%","cost$","lat_s","llm","in_tok","out_tok")
print(hdr)
for s in sorted(by):
    b = by[s]
    print("%-14s %3d %4d %6.1f%% %9.4f %8.1f %5d %8d %8d" % (
        s, b['n'], b['res'], 100*b['res']/b['n'], b['cost'], b['lat'], b['llm'], b['in'], b['out']))
