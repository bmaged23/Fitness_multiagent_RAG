"""Linux process sampling; CPU percent uses one fully occupied core as 100%."""
from __future__ import annotations
import os
from pathlib import Path
import threading
import time
import shutil
import subprocess


def sample_process(pid):
    base=Path('/proc')/str(pid)
    fields=(base/'stat').read_text().rsplit(')',1)[1].split()
    cpu=(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
    status=(base/'status').read_text().splitlines()
    rss=next((int(x.split()[1])/1024 for x in status if x.startswith('VmRSS:')),0)
    return {'cpu_seconds':cpu,'rss_mib':rss}


class ProcessSampler:
    def __init__(self,pid=None,interval=.1):
        self.pid=pid or os.getpid();self.interval=interval
        self.stop=threading.Event();self.samples=[]

    def __enter__(self):
        self.started=time.perf_counter();self.initial=sample_process(self.pid)
        self.samples.append((self.started,self.initial))
        def monitor():
            while not self.stop.wait(self.interval):
                try:self.samples.append((time.perf_counter(),sample_process(self.pid)))
                except (OSError,ValueError):break
        self.thread=threading.Thread(target=monitor,daemon=True);self.thread.start()
        return self

    def __exit__(self,*args):
        self.stop.set();self.thread.join()
        try:self.samples.append((time.perf_counter(),sample_process(self.pid)))
        except (OSError,ValueError):pass
        elapsed=time.perf_counter()-self.started
        final=self.samples[-1][1]
        self.result={'wall_seconds':elapsed,'peak_sampled_rss_mib':max(s['rss_mib'] for _,s in self.samples),
                     'initial_rss_mib':self.initial['rss_mib'],'final_rss_mib':final['rss_mib'],
                     'cpu_seconds':max(0,final['cpu_seconds']-self.initial['cpu_seconds']),
                     'mean_cpu_percent_one_core':100*max(0,final['cpu_seconds']-self.initial['cpu_seconds'])/elapsed,
                     'logical_cpu_count':os.cpu_count(),'samples':len(self.samples),'sampling_interval_seconds':self.interval}


class GpuSampler:
    """Whole-device NVIDIA observations; not attribution to a single process."""
    def __enter__(self):
        self.samples=[];self.stop=threading.Event();self.command=shutil.which('nvidia-smi')
        def monitor():
            while not self.stop.is_set():
                if not self.command:break
                try:
                    result=subprocess.run([self.command,'-i','0','--query-gpu=memory.used,utilization.gpu',
                        '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3)
                    if result.returncode==0:
                        memory,utilization=map(float,result.stdout.strip().split(','))
                        self.samples.append({'memory_used_mib':memory,'gpu_utilization_percent':utilization})
                except (OSError,ValueError,subprocess.TimeoutExpired):pass
                self.stop.wait(.25)
        self.thread=threading.Thread(target=monitor,daemon=True);self.thread.start()
        return self

    def __exit__(self,*args):
        self.stop.set();self.thread.join()
        self.result={'scope':'Whole device, including other applications; startup and query phases combined.',
                     'observations':len(self.samples),
                     'peak_device_memory_used_mib':max((s['memory_used_mib'] for s in self.samples),default=None),
                     'peak_device_gpu_utilization_percent':max((s['gpu_utilization_percent'] for s in self.samples),default=None),
                     'mean_device_gpu_utilization_percent':sum(s['gpu_utilization_percent'] for s in self.samples)/len(self.samples) if self.samples else None}
