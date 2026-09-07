# Stage 4 evaluation

| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-luna | baseline | capability:approval | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | capability:budget | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | capability:exploration | 3/3 (0 unavailable) | 1.000 | unsupported | 7.000 | 18222.000 | 0.667 | unsupported |
| gpt-5.6-luna | baseline | capability:planning | 5/6 (3 unavailable) | 1.000 | unsupported | 12.600 | 36054.000 | 0.400 | unsupported |
| gpt-5.6-luna | baseline | capability:recovery | 0/3 (0 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | capability:replan | 2/3 (0 unavailable) | 1.000 | unsupported | 13.000 | 45043.500 | 0.000 | unsupported |
| gpt-5.6-luna | baseline | capability:state | 3/3 (3 unavailable) | 1.000 | unsupported | 12.333 | 30061.000 | 0.667 | unsupported |
| gpt-5.6-luna | baseline | capability:termination | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | category:cross-file | 3/3 (0 unavailable) | 1.000 | unsupported | 7.000 | 18222.000 | 0.667 | unsupported |
| gpt-5.6-luna | baseline | category:hitl | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | category:long-horizon | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | category:recovery | 0/3 (0 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | baseline | category:replan | 2/3 (0 unavailable) | 1.000 | unsupported | 13.000 | 45043.500 | 0.000 | unsupported |
| gpt-5.6-luna | baseline | category:simple | 3/3 (0 unavailable) | 1.000 | unsupported | 5.667 | 11885.333 | 0.333 | unsupported |
| gpt-5.6-luna | baseline | overall:all | 8/12 (6 unavailable) | 0.944 | unsupported | 14.500 | 36070.500 | 0.875 | unsupported |
| gpt-5.6-luna | repopilot | capability:approval | 0/0 (3 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | capability:budget | 0/1 (2 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | capability:exploration | 3/3 (0 unavailable) | 1.000 | unsupported | 10.667 | 28453.333 | 4.333 | unsupported |
| gpt-5.6-luna | repopilot | capability:planning | 5/7 (2 unavailable) | 0.667 | unsupported | 22.800 | 89404.000 | 8.400 | unsupported |
| gpt-5.6-luna | repopilot | capability:recovery | 3/3 (0 unavailable) | 1.000 | 1.000 | 11.000 | 42062.333 | 3.333 | unsupported |
| gpt-5.6-luna | repopilot | capability:replan | 2/3 (0 unavailable) | 0.333 | unsupported | 22.000 | 104996.500 | 8.500 | unsupported |
| gpt-5.6-luna | repopilot | capability:state | 3/4 (2 unavailable) | 0.833 | unsupported | 23.333 | 79009.000 | 8.333 | unsupported |
| gpt-5.6-luna | repopilot | capability:termination | 0/1 (2 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | category:cross-file | 3/3 (0 unavailable) | 1.000 | unsupported | 10.667 | 28453.333 | 4.333 | unsupported |
| gpt-5.6-luna | repopilot | category:hitl | 0/0 (3 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | category:long-horizon | 0/1 (2 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-luna | repopilot | category:recovery | 3/3 (0 unavailable) | 1.000 | 1.000 | 11.000 | 42062.333 | 3.333 | unsupported |
| gpt-5.6-luna | repopilot | category:replan | 2/3 (0 unavailable) | 0.333 | unsupported | 22.000 | 104996.500 | 8.500 | unsupported |
| gpt-5.6-luna | repopilot | category:simple | 3/3 (0 unavailable) | 0.667 | unsupported | 8.333 | 16507.333 | 2.333 | unsupported |
| gpt-5.6-luna | repopilot | overall:all | 11/13 (5 unavailable) | 0.722 | 1.000 | 19.273 | 68229.727 | 6.000 | unsupported |
| gpt-5.6-sol | baseline | capability:approval | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | capability:budget | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | capability:exploration | 3/3 (0 unavailable) | 1.000 | unsupported | 7.333 | 17514.000 | 0.667 | unsupported |
| gpt-5.6-sol | baseline | capability:planning | 3/6 (3 unavailable) | 0.889 | unsupported | 21.667 | 69002.333 | 1.333 | unsupported |
| gpt-5.6-sol | baseline | capability:recovery | 1/3 (0 unavailable) | 1.000 | 1.000 | 18.000 | 37752.000 | 3.000 | unsupported |
| gpt-5.6-sol | baseline | capability:replan | 0/3 (0 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | capability:state | 3/3 (3 unavailable) | 1.000 | unsupported | 13.333 | 34083.667 | 1.000 | unsupported |
| gpt-5.6-sol | baseline | capability:termination | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | category:cross-file | 3/3 (0 unavailable) | 1.000 | unsupported | 7.333 | 17514.000 | 0.667 | unsupported |
| gpt-5.6-sol | baseline | category:hitl | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | category:long-horizon | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | category:recovery | 1/3 (0 unavailable) | 1.000 | 1.000 | 18.000 | 37752.000 | 3.000 | unsupported |
| gpt-5.6-sol | baseline | category:replan | 0/3 (0 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | baseline | category:simple | 3/3 (0 unavailable) | 1.000 | unsupported | 4.667 | 11081.000 | 0.000 | unsupported |
| gpt-5.6-sol | baseline | overall:all | 7/12 (6 unavailable) | 0.944 | 1.000 | 16.429 | 44870.143 | 1.000 | unsupported |
| gpt-5.6-sol | repopilot | capability:approval | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | capability:budget | 0/1 (2 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | capability:exploration | 3/3 (0 unavailable) | 1.000 | unsupported | 11.667 | 33715.667 | 5.667 | unsupported |
| gpt-5.6-sol | repopilot | capability:planning | 4/7 (2 unavailable) | 0.556 | unsupported | 25.500 | 87655.750 | 8.750 | unsupported |
| gpt-5.6-sol | repopilot | capability:recovery | 1/3 (0 unavailable) | 0.333 | 0.333 | 22.000 | 69713.000 | 10.000 | unsupported |
| gpt-5.6-sol | repopilot | capability:replan | 1/3 (0 unavailable) | 0.000 | unsupported | 39.000 | 156474.000 | 8.000 | unsupported |
| gpt-5.6-sol | repopilot | capability:state | 3/4 (2 unavailable) | 0.833 | unsupported | 21.000 | 64716.333 | 9.000 | unsupported |
| gpt-5.6-sol | repopilot | capability:termination | 0/1 (2 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | category:cross-file | 3/3 (0 unavailable) | 1.000 | unsupported | 11.667 | 33715.667 | 5.667 | unsupported |
| gpt-5.6-sol | repopilot | category:hitl | 0/0 (3 unavailable) | 1.000 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | category:long-horizon | 0/1 (2 unavailable) | 0.667 | unsupported | unsupported | unsupported | unsupported | unsupported |
| gpt-5.6-sol | repopilot | category:recovery | 1/3 (0 unavailable) | 0.333 | 0.333 | 22.000 | 69713.000 | 10.000 | unsupported |
| gpt-5.6-sol | repopilot | category:replan | 1/3 (0 unavailable) | 0.000 | unsupported | 39.000 | 156474.000 | 8.000 | unsupported |
| gpt-5.6-sol | repopilot | category:simple | 3/3 (0 unavailable) | 1.000 | unsupported | 10.667 | 26927.333 | 2.000 | unsupported |
| gpt-5.6-sol | repopilot | overall:all | 8/13 (5 unavailable) | 0.667 | 0.333 | 24.000 | 75134.875 | 7.500 | unsupported |

Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.
Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.

| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-luna | all | baseline | repopilot | 7 | 1 | 4 | 0 | 6 |
| gpt-5.6-luna | cross-file | baseline | repopilot | 3 | 0 | 0 | 0 | 0 |
| gpt-5.6-luna | hitl | baseline | repopilot | 0 | 0 | 0 | 0 | 3 |
| gpt-5.6-luna | long-horizon | baseline | repopilot | 0 | 0 | 0 | 0 | 3 |
| gpt-5.6-luna | recovery | baseline | repopilot | 0 | 0 | 3 | 0 | 0 |
| gpt-5.6-luna | replan | baseline | repopilot | 1 | 1 | 1 | 0 | 0 |
| gpt-5.6-luna | simple | baseline | repopilot | 3 | 0 | 0 | 0 | 0 |
| gpt-5.6-sol | all | baseline | repopilot | 6 | 1 | 2 | 3 | 6 |
| gpt-5.6-sol | cross-file | baseline | repopilot | 3 | 0 | 0 | 0 | 0 |
| gpt-5.6-sol | hitl | baseline | repopilot | 0 | 0 | 0 | 0 | 3 |
| gpt-5.6-sol | long-horizon | baseline | repopilot | 0 | 0 | 0 | 0 | 3 |
| gpt-5.6-sol | recovery | baseline | repopilot | 0 | 1 | 1 | 1 | 0 |
| gpt-5.6-sol | replan | baseline | repopilot | 0 | 0 | 1 | 2 | 0 |
| gpt-5.6-sol | simple | baseline | repopilot | 3 | 0 | 0 | 0 | 0 |
