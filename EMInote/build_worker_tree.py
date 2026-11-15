def build_worker_tree(
    process_table: Dict[int, psutil.Process], 
    root_names: tuple, 
    runner_names: tuple
) -> List[WorkerProc]:
    """Costruisce l'albero dei processi associati a Ollama in modo efficiente.
    
    Risolve il problema dei processi zombie di Windows e cattura i runner orfani
    (stray) che si sganciano dal demone principale ma continuano ad allocare VRAM/CPU.
    """
    from .worker_tree import WorkerProc  # adatta l'import al tuo modulo
    
    # 1. Indicizzazione bidirezionale per ridurre la complessità computazionale
    parent_to_children = {}
    for pid, proc in process_table.items():
        try:
            # Evita di bloccare l'albero se un processo muore durante l'indicizzazione
            ppid = proc.ppid()
            parent_to_children.setdefault(ppid, []).append(pid)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue

    ollama_worker_procs: List[WorkerProc] = []
    visited_pids = set()

    # 2. Funzione interna di scansione ricorsiva (DFS)
    def dfs_populate(pid: int):
        if pid in visited_pids:
            return
        visited_pids.add(pid)
        
        proc = process_table.get(pid)
        if not proc:
            return
            
        try:
            with proc.oneshot():
                w_proc = WorkerProc(
                    pid=pid,
                    name=proc.name(),
                    create_time=proc.create_time()
                )
                ollama_worker_procs.append(w_proc)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return

        # Scansione dei figli tramite la tabella pre-calcolata
        for child_pid in parent_to_children.get(pid, []):
            dfs_populate(child_pid)

    # 3. Identificazione delle radici dell'albero (es. ollama.exe / ollama serve)
    for pid, proc in process_table.items():
        try:
            if proc.name().lower() in [n.lower() for n in root_names]:
                dfs_populate(pid)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue

    # 4. Aggancio dei RUNNER ORFANI (Stray Runners)
    # Su Windows, se il demone Ollama viene riavviato bruscamente, i moduli llama-server
    # possono rimanere attivi in background come processi orfani privi di padre tracciabile.
    for pid, proc in process_table.items():
        if pid not in visited_pids:
            try:
                if proc.name().lower() in [n.lower() for n in runner_names]:
                    # Verifica che non sia uno zombie prima di aggiungerlo
                    dfs_populate(pid)
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue

    return ollama_worker_procs
