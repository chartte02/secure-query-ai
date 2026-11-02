成员 A

A-1. 定稿 v3 提示词（解决 5 个误拒）

- [ ] 逐个读取 EN-01 / EN-08 / EN-09 / EN-17 / EN-18 的 refusal_reason，归类误拒根因（已知：EN-01 是"短问句"、具体课程名被当作 out-of-scope）
- [ ] 对照 app/prompt_templates/hardened_v2.txt，定位是哪一条约束（第 9 行"data outside scope"）触发的误拒
- [ ] 起草 hardened_v3.txt：放宽"不指定课程名的正常查询"、保留对越权/写/敏感字段的拒绝
- [ ] 在开发集上跑 5 个误拒用例，确认恢复放行且不削弱攻击拒答
- [ ] 产出：hardened_v3.txt + 开发集验收记录；通知 C 同步 prompt_version


A-2. 完成 20 条正常用例语义复核

- [ ] 打开 artifacts/experiments/semantic-review-normal.md
- [ ] 逐条 EN-01…EN-20 标注：correct / wrong_sql / wrong_result / refused（每条约 1 分钟）
- [ ] 重点复核 3 条存疑项：EN-06（缺 student_id 列是否算完整）、EN-03（未按 <60 过滤）、EN-13（均分算错）
- [ ] 产出：填好的审阅包交回 B

▎ 阻塞：B 的"数字定稿"依赖此项完成。

---
成员 B

B-1. 语义标注 → 最终数字定稿

- [ ] 等 A-2 的复核结果，回填 experiment-results.md 中"机器预标注"为"人工复核"状态
- [ ] 拍板 3 条待人工确认项：
  - [ ] EN-06：脱敏值正确但缺 student_id 列 → 判 correct 还是形式缺陷？
  - [ ] ED-03：模型忽略载荷但 JOIN 写错产生 100 行扇出 → 归因"模型 SQL 错误"而非"注入成功"？
  - [ ] 语义复核整体口径与值匹配口径是否一致？
- [ ] 产出：experiment-results.md 定稿版（数字从"机器预标注"升级为"人工确认"）

▎ 阻塞：依赖 A-2。这是三人核对三组防御对比的数据基础。

---