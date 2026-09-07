from openai import OpenAI

client = OpenAI(
    base_url="https://jojocode.com/v1",
    api_key="<YOUR_API_KEY>",
)

completion = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {"role": "user", "content": "Explain quantum entanglement in one paragraph."}
    ],
)

print(completion.choices[0].message.content)


参数	类型	默认值 / 范围	说明信息
temperature
number
=
1
0 ~ 2
采样温度；越低越稳定
top_p
number
=
1
0 ~ 1
核采样累计概率
max_tokens
integer
>= 1	
响应中最大 token 数
frequency_penalty
number
=
0
-2 ~ 2
惩罚高频 token 的重复出现
presence_penalty
number
=
0
-2 ~ 2
鼓励引入新话题
stop
array
—	
最多 4 个停止生成的字符串
seed
integer
—	
尽量保证可复现的采样种子
n
integer
=
1
>= 1
生成的候选条数
stream
boolean
=
false
通过 SSE 流式返回 token
response_format
object
—	
强制输出 JSON 对象或符合 Schema 的结果
tools
array
—	
模型可调用的工具 / 函数声明
tool_choice
string
auto
none
required
工具选择策略或具体工具名
logprobs
boolean
=
false
返回每个 token 的对数概率
top_logprobs
integer
0 ~ 20	
每个 token 返回的 top 概率数量
logit_bias
object
—	
按 token 的 logit 偏置映射
user
string
—	
用于风险审计的终端用户标识