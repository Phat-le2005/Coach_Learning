"""Supervise owned worker processes with time, RAM and disk bounds."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil

from ...storage import read_json, write_json
from ...readiness.batch import stop_owned
from ..transcript_batch import now


def sample_tree(processes, usage):
    rss = 0
    root = psutil.Process()
    for child in [root, *root.children(recursive=True)]:
        try:
            rss += child.memory_info().rss
            key = (child.pid, child.create_time())
            cpu = child.cpu_times()
            io = child.io_counters()
            usage[key] = {'cpu_seconds': cpu.user + cpu.system,
                          'read_bytes': io.read_bytes, 'write_bytes': io.write_bytes}
        except psutil.Error:
            pass
    return rss


def execute_chunks(tasks, output, *, workers=2, chunk_timeout=1800, run_timeout=14400,
                   memory_limit_mb=8192, min_free_disk_mb=2048, stop_after_chunks=0, event=None):
    output = Path(output)
    pending = iter(tasks)
    running, finished = {}, []
    started = time.monotonic()
    usage, peak = {}, 0
    reason = None
    exhausted = False
    try:
        while running or not exhausted:
            while not exhausted and len(running) < workers and not reason:
                if stop_after_chunks and len(finished) + len(running) >= stop_after_chunks:
                    exhausted = True
                    break
                task = next(pending, None)
                if task is None:
                    exhausted = True
                    break
                task_path = Path(task['task_path'])
                task_path.parent.mkdir(parents=True, exist_ok=True)
                write_json(task_path, task['payload'])
                log = task_path.with_name('worker.log').open('ab')
                process = subprocess.Popen([sys.executable, '-B', '-u', '-m',
                                            'pdfmeta.paired.transcription_v2.chunk_worker', '--task', str(task_path)],
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                           creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == 'nt' else 0)
                running[process.pid] = {'process': process, 'task': task, 'started': time.monotonic(), 'log': log}
            rss = sample_tree([v['process'] for v in running.values()], usage)
            peak = max(peak, rss)
            if memory_limit_mb and rss > memory_limit_mb * 1024**2:
                reason = 'PROCESS_TREE_MEMORY_LIMIT'
            if run_timeout and time.monotonic() - started > run_timeout:
                reason = 'RUN_TIME_BUDGET_REACHED'
            if shutil.disk_usage(output).free < min_free_disk_mb * 1024**2:
                reason = 'FREE_DISK_FLOOR_REACHED'
            for pid, value in list(running.items()):
                process, task = value['process'], value['task']
                timed_out = chunk_timeout and time.monotonic() - value['started'] > chunk_timeout
                if timed_out or reason:
                    stop_owned(process)
                    process.wait(timeout=10)
                if process.poll() is not None:
                    value['log'].close()
                    result_path = Path(task['task_path']).with_name('result.json')
                    result = read_json(result_path) if result_path.is_file() else {}
                    record = {'chunk_id': task['chunk_id'], 'exit_code': process.returncode,
                              'seconds': round(time.monotonic() - value['started'], 3),
                              'error': 'CHUNK_TIMEOUT' if timed_out else reason, 'result': result}
                    finished.append(record)
                    write_json(Path(task['task_path']).with_name('supervision.json'), record)
                    del running[pid]
                    if event:
                        event(record)
            progress = {'at': now(), 'status': 'STOPPING' if reason else 'RUNNING',
                        'completed': len(list((output / 'checkpoints').glob('*.json'))),
                        'finished_chunks': len(finished), 'total_chunks_this_invocation': len(tasks),
                        'active_chunks': [v['task']['chunk_id'] for v in running.values()],
                        'elapsed_seconds': round(time.monotonic() - started, 2),
                        'rss_bytes': rss, 'peak_rss_bytes': peak, 'stop_reason': reason,
                        'workers': workers, 'ocr_threads_per_worker': 3}
            write_json(output / 'runtime.json', progress)
            if reason:
                exhausted = True
            if running:
                time.sleep(.5)
    finally:
        for value in running.values():
            stop_owned(value['process'])
            value['process'].wait(timeout=10)
            value['log'].close()
    return {'chunks': finished, 'stop_reason': reason,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'peak_process_tree_rss_bytes': peak,
            'sampled_cpu_seconds': round(sum(v['cpu_seconds'] for v in usage.values()), 3),
            'sampled_read_bytes': sum(v['read_bytes'] for v in usage.values()),
            'sampled_write_bytes': sum(v['write_bytes'] for v in usage.values()),
            'resource_sample_interval_seconds': .5}
