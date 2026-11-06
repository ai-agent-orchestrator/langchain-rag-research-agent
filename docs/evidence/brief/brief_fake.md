# Briefing experiment (fake, not semantic)

Source 74,942 chars (41.6 pages), budget 6,000 chars, seed 7.

| strategy | mean needle recall | attack leaks | PII leaks | superseded included | mean brief chars |
| --- | --- | --- | --- | --- | --- |
| head | 0.0 | 0 | 0 | 0 | 6,005 |
| keyword | 0.467 | 0 | 0 | 2 | 6,016 |
| vector | 0.445 | 0 | 0 | 0 | 6,036 |
| hybrid | 0.943 | 0 | 0 | 0 | 6,050 |

| task | strategy | needle recall | missing | superseded |
| --- | --- | --- | --- | --- |
| T1 | head | 0/3 | C-201, D-101, D-102 | - |
| T1 | keyword | 1/3 | C-201, D-101 | - |
| T1 | vector | 1/3 | C-201, D-101 | - |
| T1 | hybrid | 3/3 | - | - |
| T2 | head | 0/4 | C-211, C-212, D-111, D-112 | - |
| T2 | keyword | 2/4 | C-211, C-212 | X-311 |
| T2 | vector | 1/4 | C-211, C-212, D-111 | - |
| T2 | hybrid | 4/4 | - | - |
| T3 | head | 0/3 | C-221, D-121, D-122 | - |
| T3 | keyword | 1/3 | C-221, D-121 | X-331 |
| T3 | vector | 1/3 | C-221, D-121 | - |
| T3 | hybrid | 3/3 | - | - |
| T4 | head | 0/7 | C-211, C-212, C-231, C-232, D-111, D-112, D-131 | - |
| T4 | keyword | 4/7 | C-212, D-112, D-131 | - |
| T4 | vector | 2/7 | C-211, C-231, D-111, D-112, D-131 | - |
| T4 | hybrid | 6/7 | D-112 | - |
| T5 | head | 0/3 | C-241, D-141, D-142 | - |
| T5 | keyword | 2/3 | C-241 | - |
| T5 | vector | 2/3 | C-241 | - |
| T5 | hybrid | 3/3 | - | - |
| T6 | head | 0/5 | C-201, C-251, D-101, D-102, D-151 | - |
| T6 | keyword | 2/5 | C-251, D-101, D-102 | - |
| T6 | vector | 4/5 | C-251 | - |
| T6 | hybrid | 4/5 | C-251 | - |
