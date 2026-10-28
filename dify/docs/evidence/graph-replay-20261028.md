# 忘川当铺 · DSL 图逐节点回放记录

- 运行时间：2026-10-28（UTC+8）
- 回放器：`dify/scripts/replay_flow.py`
- 后端：`http://127.0.0.1:8787`（真实调用，非 mock）
- PowerContext：`http://127.0.0.1:18080`
- 说明：Code/IF-ELSE/HTTP/Answer 节点按 DSL 原样执行；LLM 节点用确定性替身，避免依赖外部模型。Dify 内的真实模型调用需在导入后验证。

## 1. 第一次典当

输入：`我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。`

```text
-> start [start] 开始
-> pack [code] 组装请求
   out: {"body": "{\"player_id\": \"replay-evidence-20261028b\", \"message\": \"我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。\"}"}
-> route_ledger [if-else] 是否查账
   condition: false
-> route_redeem [if-else] 是否赎回
   condition: false
-> context_http [http-request] 召回旧账
   POST http://host.docker.internal:8787/v1/session/context -> 200
   body: 【忘川账本 · 仅供掌柜阅读】
这位客人第一次来，账本还是空的。
下一张当票编号：#1

提示：若客人提到旧账里的人、物或细节，先引用旧账原文，再谈本次交易；不要提账本编号、接口或 AI。
-> keeper_llm [llm] 掌柜阿忘
   reply: （替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。
-> pack_turn [code] 封装本轮记账
   out: {"body": "{\"player_id\": \"replay-evidence-20261028b\", \"message\": \"我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。\", \"reply\": \"（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。\"}"}
-> turn_http [http-request] 记入账本
   POST http://host.docker.internal:8787/v1/session/turn -> 200
   body: 1
-> main_answer [answer] 掌柜回复

[回答] （替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。

—— 当票 #1 · 已记入忘川账本 ——


[路径] start(start) -> pack(code) -> route_ledger(if-else) -> route_redeem(if-else) -> context_http(http-request) -> keeper_llm(llm) -> pack_turn(code) -> turn_http(http-request) -> main_answer(answer)
```

## 2. 新对话召回旧账

输入：`又是我。今天路过码头闻到海风，忽然想起那块桂花糕。我想再押一段加班到凌晨的记忆，换一夜好眠。`

```text
-> start [start] 开始
-> pack [code] 组装请求
   out: {"body": "{\"player_id\": \"replay-evidence-20261028b\", \"message\": \"又是我。今天路过码头闻到海风，忽然想起那块桂花糕。我想再押一段加班到凌晨的记忆，换一夜好眠。\"}"}
-> route_ledger [if-else] 是否查账
   condition: false
-> route_redeem [if-else] 是否赎回
   condition: false
-> context_http [http-request] 召回旧账
   POST http://host.docker.internal:8787/v1/session/context -> 200
   body: 【忘川账本 · 仅供掌柜阅读】
这位客人是老客，账本里有 1 笔未赎当票。
下一张当票编号：#2

与这次典当相关的旧账（引用时保留原文细节）：
- 当票 #1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。

提示：若客人提到旧账里的人、物或细节，先引用旧账原文，再谈本次交易；不要提账本编号、接口或 AI。
-> keeper_llm [llm] 掌柜阿忘
   reply: （替身掌柜）我记得。账本上写着：- 当票 #1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川……这回要押什么？
-> pack_turn [code] 封装本轮记账
   out: {"body": "{\"player_id\": \"replay-evidence-20261028b\", \"message\": \"又是我。今天路过码头闻到海风，忽然想起那块桂花糕。我想再押一段加班到凌晨的记忆，换一夜好眠。\", \"reply\": \"（替身掌柜）我记得。账本上写着：- 当票 #1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川……这回要押什么？\"}"}
-> turn_http [http-request] 记入账本
   POST http://host.docker.internal:8787/v1/session/turn -> 200
   body: 2
-> main_answer [answer] 掌柜回复

[回答] （替身掌柜）我记得。账本上写着：- 当票 #1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川……这回要押什么？

—— 当票 #2 · 已记入忘川账本 ——


[路径] start(start) -> pack(code) -> route_ledger(if-else) -> route_redeem(if-else) -> context_http(http-request) -> keeper_llm(llm) -> pack_turn(code) -> turn_http(http-request) -> main_answer(answer)
```

## 3. 查账

```text
-> start [start] 开始
-> pack [code] 组装请求
   out: {"body": "{\"player_id\": \"replay-evidence-20261028b\", \"message\": \"查账\"}"}
-> route_ledger [if-else] 是否查账
   condition: true
-> ledger_http [http-request] 读取账本
   POST http://host.docker.internal:8787/v1/session/ledger -> 200
   body: 忘川账本 · 未赎当票 2 笔
#1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。
#2｜典当：又是我。今天路过码头闻到海风，忽然想起那块桂花糕。我想再押一段加班到凌晨的记忆，换一夜好眠。｜掌柜批注：（替身掌柜）我记得。账本上写着：- 当票 #1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我…

输入「赎回 1」这样的口令，可以赎回对应编号的当票。
-> ledger_answer [answer] 账本回复

[回答] 忘川账本 · 未赎当票 2 笔
#1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。
#2｜典当：又是我。今天路过码头闻到海风，忽然想起那块桂花糕。我想再押一段加班到凌晨的记忆，换一夜好眠。｜掌柜批注：（替身掌柜）我记得。账本上写着：- 当票 #1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我…

输入「赎回 1」这样的口令，可以赎回对应编号的当票。

[路径] start(start) -> pack(code) -> route_ledger(if-else) -> ledger_http(http-request) -> ledger_answer(answer)
```

## 4. 赎回第一张当票

```text
-> start [start] 开始
-> pack [code] 组装请求
   out: {"body": "{\"player_id\": \"replay-evidence-20261028b\", \"message\": \"赎回 1\"}"}
-> route_ledger [if-else] 是否查账
   condition: false
-> route_redeem [if-else] 是否赎回
   condition: true
-> redeem_http [http-request] 赎回当票
   POST http://host.docker.internal:8787/v1/session/redeem -> 200
   body: 掌柜从账本里取下第 1 号当票，吹了吹上面的灰。
你典当的那段记忆回来了：
「我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。」
（掌柜当时的批注：（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。）
账本上还剩 1 笔未赎。
-> redeem_answer [answer] 赎回回复

[回答] 掌柜从账本里取下第 1 号当票，吹了吹上面的灰。
你典当的那段记忆回来了：
「我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。」
（掌柜当时的批注：（替身掌柜）新客？行，把记忆放柜台上，我听听值几个忘川币。）
账本上还剩 1 笔未赎。

[路径] start(start) -> pack(code) -> route_ledger(if-else) -> route_redeem(if-else) -> redeem_http(http-request) -> redeem_answer(answer)
```

## 5. 赎回后查账

```text
-> start [start] 开始
-> pack [code] 组装请求
   out: {"body": "{\"player_id\": \"replay-evidence-20261028b\", \"message\": \"查账\"}"}
-> route_ledger [if-else] 是否查账
   condition: true
-> ledger_http [http-request] 读取账本
   POST http://host.docker.internal:8787/v1/session/ledger -> 200
   body: 忘川账本 · 未赎当票 1 笔
#2｜典当：又是我。今天路过码头闻到海风，忽然想起那块桂花糕。我想再押一段加班到凌晨的记忆，换一夜好眠。｜掌柜批注：（替身掌柜）我记得。账本上写着：- 当票 #1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我…

输入「赎回 1」这样的口令，可以赎回对应编号的当票。
-> ledger_answer [answer] 账本回复

[回答] 忘川账本 · 未赎当票 1 笔
#2｜典当：又是我。今天路过码头闻到海风，忽然想起那块桂花糕。我想再押一段加班到凌晨的记忆，换一夜好眠。｜掌柜批注：（替身掌柜）我记得。账本上写着：- 当票 #1｜典当：我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。｜掌柜批注：（替身掌柜）新客？行，把记忆放柜台上，我…

输入「赎回 1」这样的口令，可以赎回对应编号的当票。

[路径] start(start) -> pack(code) -> route_ledger(if-else) -> ledger_http(http-request) -> ledger_answer(answer)
```
