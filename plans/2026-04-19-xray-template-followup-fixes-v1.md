# xray 报告模板跟进修复 v1

## 背景

用户检查 `outputs/tsk_20260418_161240_1d9d91a5/report.docx` 后指出当前 xray 报告仍有几处版式与字段问题：

- 第一页顶部不希望展示主机 / IP / 自动总结信息
- 公司名称下方需要展示具体年月日
- 人工校验相关表格内容已从模板中删除，后续应按删除后的结构生成
- 节点负载状态应调整为更明确的 CPU 使用率 / 内存使用率字段
- 当前报告没有生成系统运行历史趋势图和未来预测图，需要明确是数据不足还是图片生成链路未接入

## 本轮范围

1. 更新 xray DOCX 模板占位：
   - 移除/清空第一页顶部主机、IP、总结类占位
   - 将公司名称下方字段改为中文日期占位
   - 删除人工校验表格行
   - 将管理节点 / 引擎节点负载行改为 CPU 使用率、内存使用率
2. 更新 xray report payload：
   - 增加中文格式巡检日期字段
3. 更新模板相关测试：
   - 校验新日期占位存在
   - 校验人工校验占位已移除
   - 校验负载行标签已调整
4. 重新用现有 xray 任务生成报告并核对关键文本
5. 明确趋势图未生成原因和后续实现边界

## 非目标

- 不改 xray 上传主流程
- 不改 analyzer 解析规则
- 不伪造历史趋势图或未来预测图
- 不把 WAF trend enhancement 子链强行并入 xray 主链
- 不引入新的图片渲染依赖

## 验证

计划执行：

```bash
.venv/bin/pytest tests/test_report_payload_mapper.py tests/test_report_template_selector.py tests/test_report_rendering_service.py -q
.venv/bin/pytest tests -q
cd log-analyzer-service && ../.venv/bin/pytest tests -q
```

并使用现有 `tsk_20260418_161240_1d9d91a5` 重新渲染 DOCX，检查：

- 不再出现第一页顶部主机 / IP / 总体情况摘要
- 公司名称下方出现中文日期
- 不再出现人工校验表格行
- 负载行展示为 CPU 使用率 / 内存使用率
