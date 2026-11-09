"""Per-job timing/resource logs. No document text, credentials or cloud calls."""
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid

from .storage import write_json


class PerformanceLog:
    def __init__(self, output, runtime, *, name='ocr', port=8790, gpu=False, sample=True):
        self.output, self.runtime = Path(output), Path(runtime)
        self.name, self.port, self.gpu, self.sample = name, port, gpu, sample
        self.run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        self.started = time.perf_counter()
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.stages = {}
        self.request_totals = dict(model_requests=0, model_request_seconds=0.0,
            input_tokens=0, output_tokens=0, requests_with_token_usage=0)
        self.resource_samples, self.resource_peaks = 0, {}
        self.cpu_times = {}
        self.last_sample = self.started
        self.nvidia = shutil.which('nvidia-smi') if gpu else None
        self.output.mkdir(parents=True, exist_ok=True)

    def event(self, event, **fields):
        row = dict(run_id=self.run_id, at=datetime.now(timezone.utc).isoformat(),
                   elapsed_seconds=round(time.perf_counter()-self.started, 3), event=event, **fields)
        with self.lock:
            with (self.output / f'{self.name}-performance.events.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False)+'\n')

    def __enter__(self):
        self.event('run_start', resource_scope='OCR/layout process tree plus verified local model server; GPU device-wide')
        if self.sample:
            self.thread = threading.Thread(target=self._monitor, daemon=True, name='pdf-job-metrics')
            self.thread.start()
        return self

    def _monitor(self):
        while not self.stop.is_set():
            try:
                self._sample_resources()
            except Exception as error:
                self.event('resource_sample_unavailable', error_type=type(error).__name__)
            self.stop.wait(2)

    def _sample_resources(self):
        import psutil  # Declared in requirements-native.txt; metrics never installs it.
        root = psutil.Process()
        processes = {root.pid: root}
        for p in root.children(recursive=True):
            processes[p.pid] = p
        stem = 'local-qwen-server' if self.port == 8790 else f'local-qwen-server-{self.port}'
        try:
            server = psutil.Process(int((self.runtime/(stem+'.pid')).read_text().strip()))
            # A stale PID must not sample an unrelated process.
            if Path(server.exe()).stem.lower() == 'llama-server':
                processes[server.pid] = server
        except (OSError, ValueError, psutil.Error):
            pass
        ram, cpu, baseline_known = 0, 0, False
        for pid, p in processes.items():
            try:
                ram += p.memory_info().rss
                usage = sum(p.cpu_times()[:2])
                baseline_known |= pid in self.cpu_times
                cpu += max(0, usage-self.cpu_times.get(pid, usage))
                self.cpu_times[pid] = usage
            except psutil.Error:
                continue
        now = time.perf_counter()
        core = 100*cpu/max(now-self.last_sample, .001) if baseline_known else None
        self.last_sample = now
        row = dict(ram_mb=round(ram/1024**2, 2), cpu_core_percent=round(core, 2) if core is not None else None,
                   cpu_machine_capacity_percent=round(core/(os.cpu_count() or 1), 2) if core is not None else None, gpu=[])
        if self.nvidia:
            try:
                result = subprocess.run([self.nvidia, '--query-gpu=index,utilization.gpu,memory.used,memory.total,power.draw',
                    '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        values = [v.strip() for v in line.split(',')]
                        def number(i):
                            try:return float(values[i])
                            except (ValueError, IndexError):return None
                        row['gpu'].append(dict(index=values[0], utilization_percent=number(1),
                            vram_used_mb=number(2), vram_total_mb=number(3), power_watts=number(4)))
            except (OSError, subprocess.TimeoutExpired):
                pass
        with self.lock:
            self.resource_samples += 1
            for key, value in row.items():
                if key != 'gpu' and value is not None:
                    self.resource_peaks[key] = max(value,self.resource_peaks.get(key,value))
            for g in row['gpu']:
                for key in ['utilization_percent','vram_used_mb']:
                    if g[key] is not None:
                        self.resource_peaks['gpu_'+key] = max(g[key],self.resource_peaks.get('gpu_'+key,g[key]))
        self.event('resource_sample', **row)

    @contextmanager
    def stage(self, name, **fields):
        self.event('stage_start', stage=name, **fields)
        tick = time.perf_counter()
        status = 'OK'
        try:
            yield
        except BaseException:
            status = 'FAILED'
            raise
        finally:
            seconds = time.perf_counter()-tick
            self.stages[name] = self.stages.get(name, 0)+seconds
            self.event('stage_end', stage=name, seconds=round(seconds, 3), status=status, **fields)
            print(f'[perf] {name}: {seconds:.2f}s status={status}', flush=True)

    def request(self, kind, generate, *args):
        tick = time.perf_counter()
        response = {}
        try:
            response = generate(*args)
            return response
        finally:
            seconds = time.perf_counter()-tick
            usage = response.get('usage', {})
            row = dict(kind=kind, seconds=round(seconds, 3), status=response.get('status', 'REQUEST_ERROR'),
                       input_tokens=usage.get('promptTokenCount'), output_tokens=usage.get('candidatesTokenCount'))
            row['output_tokens_per_request_second'] = round(row['output_tokens']/seconds, 3) if isinstance(row['output_tokens'], int) and seconds else None
            self.request_totals['model_requests'] += 1
            self.request_totals['model_request_seconds'] += row['seconds']
            self.request_totals['input_tokens'] += row['input_tokens'] or 0
            self.request_totals['output_tokens'] += row['output_tokens'] or 0
            self.request_totals['requests_with_token_usage'] += row['output_tokens'] is not None
            self.event('model_request', **row)
            print(f'[perf] request {kind}: {seconds:.2f}s input_tokens={row["input_tokens"]} '
                  f'output_tokens={row["output_tokens"]} output_tokens/request-second={row["output_tokens_per_request_second"]}', flush=True)

    def snapshot(self, counts=None, *, status='RUNNING'):
        counts = counts or {}
        elapsed = time.perf_counter()-self.started
        totals = dict(self.request_totals)
        with self.lock:
            peaks, samples = dict(self.resource_peaks), self.resource_samples
        request_seconds, output_tokens = totals['model_request_seconds'], totals['output_tokens']
        return dict(version='pdf-performance/v1', run_id=self.run_id, status=status,
            elapsed_seconds=round(elapsed, 3), stages_seconds={k:round(v,3) for k,v in self.stages.items()},
            execution_mode='INFERENCE' if totals['model_requests'] else 'CACHE_OR_NO_INFERENCE',
            counts=counts, model_requests=totals['model_requests'],
            model_request_seconds=round(request_seconds,3),
            input_tokens=totals['input_tokens'], output_tokens=output_tokens,
            requests_with_token_usage=totals['requests_with_token_usage'],
            output_tokens_per_request_second=round(output_tokens/request_seconds,3) if request_seconds and totals['requests_with_token_usage'] else None,
            seconds_per_page=round(elapsed/counts['processed_pages'],3) if counts.get('processed_pages') else None,
            pages_per_minute=round(60*counts.get('processed_pages',0)/elapsed,3) if elapsed else None,
            questions_per_minute=round(60*counts.get('questions',0)/elapsed,3) if elapsed else None,
            resources=dict(sample_interval_seconds=2, samples=samples, ram_peak_mb=peaks.get('ram_mb'),
                cpu_core_peak_percent=peaks.get('cpu_core_percent'),
                cpu_machine_capacity_peak_percent=peaks.get('cpu_machine_capacity_percent'),
                gpu_peak_utilization_percent=peaks.get('gpu_utilization_percent'), gpu_peak_vram_mb=peaks.get('gpu_vram_used_mb'),
                scope='Process-tree RSS plus local model; CPU may exceed one core. GPU device-wide, may include other apps. Sampled peaks, not hardware maxima.'),
            rate_definition='Output tokens / full request seconds, including prompt/image processing; not decoder-only tokens/s.')

    def finish(self, status='OK', counts=None):
        self.stop.set()
        if self.thread:
            self.thread.join(4)
        report = self.snapshot(counts, status=status)
        self.event('run_end', report=report)
        write_json(self.output/f'{self.name}-performance.json', report)
        write_json(self.output/f'performance-runs/{self.run_id}-{self.name}.json', report)
        print(f'[perf] {self.name} total={report["elapsed_seconds"]:.2f}s pages/min={report["pages_per_minute"]} '
              f'RAM_peak_MB={report["resources"]["ram_peak_mb"]} GPU_peak_percent={report["resources"]["gpu_peak_utilization_percent"]} '
              f'VRAM_peak_MB={report["resources"]["gpu_peak_vram_mb"]}', flush=True)
        return report

    def __exit__(self, kind, value, traceback):
        if kind:
            self.finish('FAILED')


def measured_ocr(function):
    @wraps(function)
    def wrapped(pdf, runtime, output, **kwargs):
        target = Path(output).resolve()
        if target in {Path(pdf).resolve(), Path(runtime).resolve()}:
            raise ValueError('SEPARATE_OUTPUT_REQUIRED')
        with PerformanceLog(target, runtime, port=kwargs.get('port',8790), gpu=kwargs.get('device','cpu').lower()=='gpu') as metrics:
            result = function(pdf, runtime, output, _performance=metrics, **kwargs)
            counts = {k:result[k] for k in ['processed_pages','questions','inference_calls_this_run','cache_hits_this_run']}
            result['performance'] = metrics.finish(result['status'], counts)
            write_json(target/'summary.json', result)
            return result
    return wrapped
