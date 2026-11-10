import datetime
import json
import subprocess
import time
from pathlib import Path

cmd = ['powershell.exe', '-NoProfile', '-Command', "$s=[Diagnostics.Stopwatch]::StartNew(); while(($line=[Console]::ReadLine()) -ne $null){ if($line -eq 'end'){break}; [Console]::WriteLine($line+' '+$s.Elapsed.TotalSeconds.ToString([Globalization.CultureInfo]::InvariantCulture)+' '+[DateTime]::UtcNow.ToString('o')); [Console]::Out.Flush() }"]
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
samples=[]
for n in range(5):
    if n: time.sleep(10)
    before = {'monotonic': time.monotonic(), 'raw': time.clock_gettime(time.CLOCK_MONOTONIC_RAW), 'realtime': time.time()}
    p.stdin.write(str(n)+'\n'); p.stdin.flush()
    line = p.stdout.readline().strip()
    after = {'monotonic': time.monotonic(), 'raw': time.clock_gettime(time.CLOCK_MONOTONIC_RAW), 'realtime': time.time()}
    samples.append({'request': n, 'before':before, 'windows_reply':line, 'after':after})
p.stdin.write('end\n'); p.stdin.flush()
out, err = p.communicate(timeout=15)
result={'started_utc':started,'command':cmd,'samples':samples,'exit_code':p.returncode,'timeout':False,'trailing_stdout':out,'stderr':err,'method':'Each Windows stopwatch observation occurred between the Linux before and after timestamps; variable interop latency is bounded by these intervals.'}
Path('clock-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
