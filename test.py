import math

"""
Short script to transform data. Transform a file containing commands and timestamps, to a file containing commands and sleep durations.
"""

level_template = []
with open("targets/test.txt", "r") as f:
    for line in f.readlines():
        cmd_hex, delay_str = line.split(maxsplit=2)
        cmd_bytes = bytes.fromhex(cmd_hex)
        delay = float(delay_str) * 1000
        level_template.append((cmd_bytes, delay))


prev = 0
times = []

for cmd, delay in level_template:
    newTime = prev - delay
    if newTime > 10000:
        newTime -= 60000
    times.append(math.fabs(newTime) / 1000)
    prev = delay

times.pop(0)
level_template.pop()


with open("targets/times.txt", "w") as f:
    for i in range(len(level_template)):
        f.write(bytes.hex(level_template[i][0]))
        f.write(" ")
        f.write(str(times[i]))
        f.write("\n")
        prev = delay
