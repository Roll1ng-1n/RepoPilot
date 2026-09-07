# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-luna | baseline | capability:approval | 0/3 (9 unavailable) | 0.583 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | capability:budget | 0/12 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | capability:exploration | 10/12 (0 unavailable) | 0.667 | unsupported | 7.400 | 17012.200 | 0.300 | unsupported |
| gpt-5.6-luna | baseline | capability:planning | 14/36 (0 unavailable) | 0.444 | unsupported | 16.000 | 41500.714 | 0.571 | unsupported |
| gpt-5.6-luna | baseline | capability:recovery | 1/12 (0 unavailable) | 0.833 | 0.250 | 53.000 | 100793.000 | 11.000 | unsupported |
| gpt-5.6-luna | baseline | capability:replan | 4/12 (0 unavailable) | 0.667 | unsupported | 20.000 | 50825.000 | 0.250 | unsupported |
| gpt-5.6-luna | baseline | capability:state | 10/24 (0 unavailable) | 0.333 | unsupported | 14.400 | 37771.000 | 0.700 | unsupported |
| gpt-5.6-luna | baseline | capability:termination | 0/12 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | category:cross-file | 10/12 (0 unavailable) | 0.667 | unsupported | 7.400 | 17012.200 | 0.300 | unsupported |
| gpt-5.6-luna | baseline | category:hitl | 0/3 (9 unavailable) | 0.583 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | category:long-horizon | 0/12 (0 unavailable) | 0.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | category:recovery | 1/12 (0 unavailable) | 0.833 | 0.250 | 53.000 | 100793.000 | 11.000 | unsupported |
| gpt-5.6-luna | baseline | category:replan | 4/12 (0 unavailable) | 0.667 | unsupported | 20.000 | 50825.000 | 0.250 | unsupported |
| gpt-5.6-luna | baseline | category:simple | 12/12 (0 unavailable) | 0.750 | unsupported | 5.667 | 11455.583 | 0.417 | unsupported |
| gpt-5.6-luna | baseline | overall:all | 27/63 (9 unavailable) | 0.583 | 0.250 | 15.296 | 35563.370 | 1.037 | unsupported |
| gpt-5.6-luna | repopilot | capability:approval | 0/7 (5 unavailable) | 0.250 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | capability:budget | 0/11 (1 unavailable) | 0.083 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | capability:exploration | 6/12 (0 unavailable) | 0.417 | unsupported | 17.333 | 42746.167 | 7.000 | unsupported |
| gpt-5.6-luna | repopilot | capability:planning | 7/35 (1 unavailable) | 0.250 | unsupported | 42.857 | 133160.000 | unsupported | unsupported |
| gpt-5.6-luna | repopilot | capability:recovery | 5/12 (0 unavailable) | 0.250 | 0.500 | 18.000 | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | capability:replan | 1/12 (0 unavailable) | 0.250 | unsupported | 105.000 | 283030.000 | 23.000 | unsupported |
| gpt-5.6-luna | repopilot | capability:state | 6/23 (1 unavailable) | 0.250 | unsupported | 32.500 | 108181.667 | unsupported | unsupported |
| gpt-5.6-luna | repopilot | capability:termination | 0/11 (1 unavailable) | 0.083 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | category:cross-file | 6/12 (0 unavailable) | 0.417 | unsupported | 17.333 | 42746.167 | 7.000 | unsupported |
| gpt-5.6-luna | repopilot | category:hitl | 0/7 (5 unavailable) | 0.250 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | category:long-horizon | 0/11 (1 unavailable) | 0.083 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | category:recovery | 5/12 (0 unavailable) | 0.250 | 0.500 | 18.000 | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | category:replan | 1/12 (0 unavailable) | 0.250 | unsupported | 105.000 | 283030.000 | 23.000 | unsupported |
| gpt-5.6-luna | repopilot | category:simple | 9/12 (0 unavailable) | 0.583 | unsupported | 12.333 | 25154.222 | 3.222 | unsupported |
| gpt-5.6-luna | repopilot | overall:all | 21/66 (6 unavailable) | 0.306 | 0.500 | 27.952 | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | capability:approval | 0/2 (10 unavailable) | 0.750 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | capability:budget | 0/9 (3 unavailable) | 0.250 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | capability:exploration | 9/12 (0 unavailable) | 0.667 | unsupported | 11.556 | 37741.333 | 1.000 | unsupported |
| gpt-5.6-sol | baseline | capability:planning | 17/33 (3 unavailable) | 0.639 | unsupported | 18.588 | 61987.647 | 1.529 | unsupported |
| gpt-5.6-sol | baseline | capability:recovery | 4/12 (0 unavailable) | 1.000 | 0.667 | 18.750 | 37326.750 | 3.000 | unsupported |
| gpt-5.6-sol | baseline | capability:replan | 8/12 (0 unavailable) | 1.000 | unsupported | 14.875 | 45889.000 | 1.500 | unsupported |
| gpt-5.6-sol | baseline | capability:state | 9/21 (3 unavailable) | 0.458 | unsupported | 21.889 | 76297.556 | 1.556 | unsupported |
| gpt-5.6-sol | baseline | capability:termination | 0/9 (3 unavailable) | 0.250 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | category:cross-file | 9/12 (0 unavailable) | 0.667 | unsupported | 11.556 | 37741.333 | 1.000 | unsupported |
| gpt-5.6-sol | baseline | category:hitl | 0/2 (10 unavailable) | 0.750 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | category:long-horizon | 0/9 (3 unavailable) | 0.250 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | category:recovery | 4/12 (0 unavailable) | 1.000 | 0.667 | 18.750 | 37326.750 | 3.000 | unsupported |
| gpt-5.6-sol | baseline | category:replan | 8/12 (0 unavailable) | 1.000 | unsupported | 14.875 | 45889.000 | 1.500 | unsupported |
| gpt-5.6-sol | baseline | category:simple | 12/12 (0 unavailable) | 1.000 | unsupported | 7.167 | 17513.333 | 0.583 | unsupported |
| gpt-5.6-sol | baseline | overall:all | 33/59 (13 unavailable) | 0.778 | 0.667 | 17.030 | 49652.606 | 1.545 | unsupported |
| gpt-5.6-sol | repopilot | capability:approval | 0/2 (10 unavailable) | 0.583 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | capability:budget | 0/10 (2 unavailable) | 0.167 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | capability:exploration | 7/12 (0 unavailable) | 0.583 | unsupported | 16.571 | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | capability:planning | 16/34 (2 unavailable) | 0.583 | unsupported | 29.375 | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | capability:recovery | 12/12 (0 unavailable) | 1.000 | 1.000 | 11.750 | 33118.167 | 2.417 | unsupported |
| gpt-5.6-sol | repopilot | capability:replan | 9/12 (0 unavailable) | 1.000 | unsupported | 22.222 | 80852.778 | 2.667 | unsupported |
| gpt-5.6-sol | repopilot | capability:state | 7/22 (2 unavailable) | 0.375 | unsupported | 38.571 | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | capability:termination | 0/10 (2 unavailable) | 0.167 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | category:cross-file | 7/12 (0 unavailable) | 0.583 | unsupported | 16.571 | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | category:hitl | 0/2 (10 unavailable) | 0.583 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | category:long-horizon | 0/10 (2 unavailable) | 0.167 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | category:recovery | 12/12 (0 unavailable) | 1.000 | 1.000 | 11.750 | 33118.167 | 2.417 | unsupported |
| gpt-5.6-sol | repopilot | category:replan | 9/12 (0 unavailable) | 1.000 | unsupported | 22.222 | 80852.778 | 2.667 | unsupported |
| gpt-5.6-sol | repopilot | category:simple | 12/12 (0 unavailable) | 1.000 | unsupported | 10.333 | 26800.917 | 2.667 | unsupported |
| gpt-5.6-sol | repopilot | overall:all | 40/60 (12 unavailable) | 0.722 | 1.000 | 21.375 | unsupported | unsupported | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-luna | all | baseline | repopilot | 14 | 13 | 7 | 28 | 10 |
| gpt-5.6-luna | cross-file | baseline | repopilot | 5 | 5 | 1 | 1 | 0 |
| gpt-5.6-luna | hitl | baseline | repopilot | 0 | 0 | 0 | 3 | 9 |
| gpt-5.6-luna | long-horizon | baseline | repopilot | 0 | 0 | 0 | 11 | 1 |
| gpt-5.6-luna | recovery | baseline | repopilot | 0 | 1 | 5 | 6 | 0 |
| gpt-5.6-luna | replan | baseline | repopilot | 0 | 4 | 1 | 7 | 0 |
| gpt-5.6-luna | simple | baseline | repopilot | 9 | 3 | 0 | 0 | 0 |
| gpt-5.6-sol | all | baseline | repopilot | 28 | 5 | 12 | 13 | 14 |
| gpt-5.6-sol | cross-file | baseline | repopilot | 5 | 4 | 2 | 1 | 0 |
| gpt-5.6-sol | hitl | baseline | repopilot | 0 | 0 | 0 | 1 | 11 |
| gpt-5.6-sol | long-horizon | baseline | repopilot | 0 | 0 | 0 | 9 | 3 |
| gpt-5.6-sol | recovery | baseline | repopilot | 4 | 0 | 8 | 0 | 0 |
| gpt-5.6-sol | replan | baseline | repopilot | 7 | 1 | 2 | 2 | 0 |
| gpt-5.6-sol | simple | baseline | repopilot | 12 | 0 | 0 | 0 | 0 |
