# 双站复测中心

白班站务把两站的实测工位路线按版登记。中心实收固定站件并封定接线。站源停用后，夜班仍可签出逐拍完检账，供排班员决定是否加开工位。站务还可在冻结站件时申报耗标原行，夜班据此办理两站共用额度的耗材核报。次班勘误使用新修订、新站件和新清单。档案员重开中心后按原号对照两版。

## 运行

需要 Python 3.11，仅使用标准库。在项目根目录运行：

```sh
python3 -B check_project.py
python3 -B -m unittest discover -s tests -t . -v
python3 -B -m examples.demo
```

`check_project.py` 由运行平台提供。演示只在自身的临时目录中创建数据库。它会登记实测样例，冻结和实收两站件，移开已关闭的站源，再签报。勘误签发后重开中心，按号领取两份原报告和首执。

## 登记和发行

- `routes.source_store.SourceStore(path)` 打开站源，`initialize()` 建立缺失的表，`close()` 关闭连接。样例使用两个独立的站源文件。
- `routes.revisions.save_revision(source, station, states, rows)` 追加完整修订，返回整数修订号。`load_revision(source, station, revision_id)` 按站和修订号读取 `RouteRevision`，保留原行、状态及提交顺序。
- `routes.states.RouteState(state_id, kind='work', entry=None, exit=None)` 定义工位。`kind` 取 `work`、`exit` 或 `complete`。`entry` 是可选的公开入口名，可指向任意种类的状态。`exit` 为出口状态必填的公开出口名。入口和出口分别命名；同一站内各入口名唯一、各出口名唯一。完检和出口是终点，禁有出边。
- `routes.transitions.TransitionRow(row_id, source, target, delay, probability)` 也可用含相同字段的映射提交。`source` 和 `target` 是状态 ID。时延为 0 至 3 的整数。概率可用 `Fraction`、整数或有理数字符串，例如 `"1/4"`。每个工作状态的出边权重精确合计为 1。每站支持 1 至 12 个状态。同源同目标的平行转移使用不同原行号。
- `station.freezing.freeze(source, station, revision_id, consuming=None)` 从所选修订生成 `StationEvidence`。`arrivals_for(entrance)` 给出首次终点事件，`remaining_at(entrance, horizon)` 给出截至该拍未发生任何首达事件的质量。`FirstArrival.exit_name` 为 `None` 时表示本站完检。证据覆盖 0 至 12 拍，省略格为零，空账的入口仍在。站件包含公开口、站和修订出处以及首达账。`station.evidence_codec` 提供 V1 站件 JSON 编解码。
- 耗材申报：`freeze(..., consuming=行号集)` 由站务指定哪些原转移完成时各耗一支标样。申报按原行号标记，同源同目标的平行原行可分别标记；申报中错版或未知原行、重复行号都会被拒绝。申报随站件固定为 V2 站件：除原首达账外，另存每个入口的计支首达表（`CountedArrival`，支数 0 至 8）和首次用超表（`FirstExceedance`，第 1 至 9 支首达拍，第 9 支为溢出档）。`consumption_for(entrance)` 读取该表。不申报（`consuming=None`）仍生成 V1 站件；V1 站件可照常签完检账，但用于耗材核报时以缺证拒绝。

## 实收、核报和档案

- `handoff.center_store.CenterIntakeStore(path, trial_id, stations=('A', 'B'))` 打开指定试验上下文。调用 `initialize()` 建立实收和清单表，调用 `reports.ledger.ReportLedger(center.connection).initialize()` 建立报告账簿。初始化可重复执行，用户修订和历史记录持续保留。关闭中心后需重新打开连接。
- `handoff.receiving.receive(center, evidence, expected_station, expected_revision)` 校验来件，保存中心副本，返回实收号。`get_received_evidence(center, receipt_id)` 按号领取中心副本。
- `handoff.manifest.fix_manifest(center, (left_receipt, right_receipt), connections)` 返回带 `manifest_id` 的固定清单。`connections` 是 `(出口 PortRef, 入口 PortRef)` 对的序列，也接受映射。`handoff.port_map.PortRef(station, name)` 按站标识端口。必须为有序两站的每个出口指定且只指定一个对站目标。清单固定两件及当前试验标识。
- `analysis.scenarios.sign(center, manifest_id, start, horizon)` 只用固定清单和实收证据签报。`start` 为具名入口 `PortRef`，`horizon` 为 0 至 12 的整数。返回 `SignedReport`，含 `report_id`、`values` 和 `receipt`。`values` 保存指定清单、原开场、H、实收号和两站出处。其 `account.first_by_tick` 按 0 至 H 给出首次完检，`account.cumulative` 是对应累计概率，`account.remaining` 是期末未完检余量。结果单位为整数拍，全部概率用 `Fraction`。恰好第 H 拍到达的事件计入；进入回路后始终未完检的质量留在余量中。
- `analysis.scenarios.sign_consumption(center, manifest_id, start, horizon, quota)` 在停源后办理耗材核报。`quota` 为两站共用额度，0 至 8 支整数。标样在转移完成那拍扣减，一次跨站或回返不恢复额度。返回 `SignedConsumptionReport`：`account.first_by_tick` 逐拍按已用支数（0 至额度）给出额度内首次完检率，`account.exceeded_by_tick` 逐拍给出首次用超概率（同拍先结超额后结完检），`account.remaining` 是到截止拍仍未超额也未完检的余额。零时延回路中可能反复消耗，也可能一直停留；所有概率精确，截止拍计入。`values` 保存清单、原开场、H、额度、实收号和两站出处。任一站件缺耗材申报时以非法输入拒绝。
- `reports.history.get_report(ledger, report_id)` 读取原签存结果及首执。`reports.history.get_consumption_report(ledger, report_id)` 按报告号复领耗材核报及首执，重开中心后仍可领取。`reports.comparison.compare_reports(ledger, first_id, second_id)` 校验两报的试验、开场和 H 相同，返回按拍的第二报减第一报及两套出处。报告和首执的顺序与清单的甲乙站位一致。

非法应用输入使用 `ValueError`，查无所选修订、入口、实收、清单或报告使用 `LookupError`；清单的端口资格和报告开场资格在对应请求中按非法参数处理。SQLite 写入或提交错误向上抛出。报告和首执同事务签发，提交失败时前次合法签存仍可领取。本地库文件只由业务入口写入，连接用于初始化和本地管理。

## 样例核账

正时延链在甲站耗一拍离站，在乙站再耗两拍完检，第 3 拍首次完检概率为 1。退回复测样例中，甲站开场以 1/2 概率耗一拍完检，以各 1/4 概率进入即时退回和永久互返支路。第 1 拍完检为 2/3，余量为 1/3。即时退回路线勘误为一拍后，第 1 拍变为 1/2，第 2 拍新增 1/8。两份 H=1 的原号对照在第 1 拍显示 -1/6，并保留各自的实收号、修订号和首执。

耗材样例中，同一正时延链申报与不申报耗标行的完检账相同（第 3 拍为 1），但申报两行后额度 0 在第 1 拍首次用超概率为 1，额度 1 在第 3 拍用超（同拍完检不计），额度 2 在第 3 拍以 2 支完检。退回复测申报 `a-retry` 后，零时延回返每圈多耗一支：额度 1、H=1 时第 1 拍以 0 支完检 1/2、以 1 支完检 1/8，第 0 拍首次用超 1/16，余额 5/16。以上耗材核报均在停源后签发，重开中心后按报告号复领。
