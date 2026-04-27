from dataclasses import asdict
from ca410_module import measure_ca410_once

result = measure_ca410_once()
data = asdict(result)

print(data)